"""Optional Chromium observer. All browser HTTP is fulfilled by guarded workers."""
import asyncio
import base64
import json
import os
import secrets
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from app.connectors import public_url

app = FastAPI(docs_url=None, redoc_url=None)
slots = asyncio.Semaphore(2)


class Observation(BaseModel):
    url: str = Field(max_length=2000)
    query: str = Field(min_length=1,max_length=100)
    submit_search: bool = True


def authorize(request):
    token = os.environ.get('ANYTUBE_BROWSER_TOKEN','')
    if not token or not secrets.compare_digest(request.headers.get('authorization',''), 'Bearer '+token):
        raise HTTPException(403,'Accès refusé.')


@app.get('/health')
async def health(request: Request):
    authorize(request)
    from playwright.async_api import async_playwright
    try:
        async with asyncio.timeout(40), async_playwright() as p:
            browser = await open_browser(p)
            try:
                context = await browser.new_context(**context_options())
                await context.close()
            finally:
                await browser.close()
        return {'ok':True,'protocol':'anytube-observer-v1','engine':'browserless' if os.environ.get('ANYTUBE_BROWSER_CDP_URL') else 'chromium'}
    except Exception:
        raise HTTPException(503,'Connexion Chromium impossible. Vérifiez le service et son jeton.')


def context_options():
    # Explicit context proxy also applies to remote incognito Browserless contexts.
    return dict(service_workers='block', accept_downloads=False,
                proxy={'server':'http://127.0.0.1:9','bypass':'<-loopback>'})


async def open_browser(playwright):
    endpoint = os.environ.get('ANYTUBE_BROWSER_CDP_URL','')
    if endpoint:
        parts = urlsplit(endpoint)
        if parts.scheme not in ('ws','wss') or not parts.hostname or parts.username or parts.password:
            raise ValueError('Invalid administrator CDP endpoint')
        pairs = parse_qsl(parts.query)
        token = os.environ.get('ANYTUBE_BROWSER_CDP_TOKEN','')
        if token:
            pairs = [(k,v) for k,v in pairs if k!='token'] + [('token',token)]
        endpoint = urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(pairs),''))
        return await playwright.chromium.connect_over_cdp(endpoint,timeout=30000)
    return await playwright.chromium.launch(chromium_sandbox=True,
        proxy=context_options()['proxy'],
        args=['--disable-background-networking','--disable-quic','--force-webrtc-ip-handling-policy=disable_non_proxied_udp'])


def search_priority(attributes):
    label=' '.join(str(attributes.get(key,'') or '') for key in ('placeholder','aria-label','name')).casefold()
    if re.search(r'\b(salle|ville|postal|zipcode|location|newsletter|email)\b',label):
        return -1
    return (10 if re.search(r'\b(film|films|série|séries|vidéo|vidéos|video|videos)\b',label) else 0) + (2 if attributes.get('type')=='search' else 0)


def search_template(url, query):
    parts=urlsplit(url)
    pairs=parse_qsl(parts.query)
    if any(k.lower() in ('token','key','api_key','access_token','signature') for k,_ in pairs):
        return None
    if not any(v==query for _,v in pairs):
        return None
    return urlunsplit((parts.scheme,parts.netloc,parts.path,
        urlencode([(k,'{query}' if v==query else v) for k,v in pairs]).replace('%7Bquery%7D','{query}'),''))


async def guarded_fetch(url, method, body, headers):
    public_url(url)
    process=await asyncio.create_subprocess_exec(sys.executable,'-m','app.assistant_http',
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
    try:
        raw,_=await asyncio.wait_for(process.communicate(json.dumps({'url':url,'method':method,'body':body,
            'headers':{k:v for k,v in headers.items() if k.lower() in ('accept','content-type')},'binary':True}).encode()),18)
        value=json.loads(raw)
        if value.get('error'):
            raise ValueError()
        return value
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def observe(body):
    from playwright.async_api import async_playwright
    samples=[]
    requests=0
    json_responses=0
    search_submitted=False
    network=asyncio.Semaphore(4)
    async with slots,async_playwright() as p:
        browser=await open_browser(p)
        try:
            context=await browser.new_context(**context_options())
            await context.route_web_socket('**/*',lambda ws:ws.close())
            async def route_request(route):
                nonlocal requests,json_responses
                request=route.request
                requests+=1
                if requests>80 or request.resource_type in ('media','image','font') or request.method not in ('GET','POST'):
                    return await route.abort()
                try:
                    async with network:
                        response=await guarded_fetch(request.url,request.method,request.post_data,request.headers)
                    endpoint=search_template(request.url,body.query)
                    if 'json' in response['content_type']:
                        json_responses+=1
                    if endpoint and request.method=='GET' and len(samples)<4:
                        try:
                            data=json.loads(response['text'])
                            if len(response['text'])<100000:
                                samples.append({'search_url':endpoint,'data':data})
                        except ValueError:
                            pass
                    await route.fulfill(status=200,content_type=response['content_type'],headers=response.get('headers',{}),body=base64.b64decode(response['base64']))
                except Exception:
                    await route.abort()
            await context.route('**/*',route_request)
            page=await context.new_page()
            await page.goto(body.url,wait_until='domcontentloaded',timeout=25000)
            search=page.locator('input[type="search"],input[name="q"],input[name="search"],input[name="query"]')
            fields=[]
            for index in range(min(await search.count(),20)):
                field=search.nth(index)
                if await field.is_visible():
                    attributes={key:await field.get_attribute(key) for key in ('placeholder','aria-label','name','type')}
                    priority=search_priority(attributes)
                    if priority>=0:
                        fields.append((priority,index))
            for _,index in (sorted(fields,reverse=True)[:2] if body.submit_search else []):
                field=search.nth(index)
                try:
                    await field.fill(body.query,timeout=3000)
                    await field.press('Enter',timeout=10000,no_wait_after=True)
                    search_submitted=True
                    await page.wait_for_timeout(5000)
                    break
                except Exception:
                    continue
            if not body.submit_search:
                await page.wait_for_timeout(1500)
            rendered = await page.content()
            if len(rendered.encode('utf-8'))>2*1024*1024:
                raise ValueError('Document rendu trop volumineux.')
            public_url(page.url)
            return {'samples':samples,'requests':requests,'json_responses':json_responses,
                    'search_submitted':search_submitted,'html':rendered,'url':page.url}
        finally:
            await browser.close()


@app.post('/observe')
async def observation(body: Observation,request: Request):
    authorize(request)
    try:
        public_url(body.url)
    except ValueError:
        raise HTTPException(422,'URL publique requise.')
    task=asyncio.create_task(observe(body))
    try:
        async with asyncio.timeout(85):
            while not task.done():
                if await request.is_disconnected():
                    raise asyncio.CancelledError()
                await asyncio.sleep(.25)
            return await task
    except (TimeoutError,Exception):
        raise HTTPException(422,'Observation indisponible ou non concluante.')
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task,return_exceptions=True)
