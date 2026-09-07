"""Optional Chromium observer. All browser HTTP is fulfilled by guarded workers."""
import asyncio
import base64
import json
import os
import secrets
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


def authorize(request):
    token = os.environ.get('ANYTUBE_BROWSER_TOKEN','')
    if not token or not secrets.compare_digest(request.headers.get('authorization',''), 'Bearer '+token):
        raise HTTPException(403,'Accès refusé.')


@app.get('/health')
def health(request: Request):
    authorize(request)
    return {'ok':True}


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
    network=asyncio.Semaphore(4)
    async with slots,async_playwright() as p:
        browser=await p.chromium.launch(chromium_sandbox=True,
            proxy={'server':'http://127.0.0.1:9','bypass':'<-loopback>'},
            args=['--disable-background-networking','--disable-quic','--force-webrtc-ip-handling-policy=disable_non_proxied_udp'])
        try:
            context=await browser.new_context(service_workers='block',accept_downloads=False)
            await context.route_web_socket('**/*',lambda ws:ws.close())
            async def route_request(route):
                nonlocal requests
                request=route.request
                requests+=1
                if requests>80 or request.resource_type in ('media','image','font') or request.method not in ('GET','POST'):
                    return await route.abort()
                try:
                    async with network:
                        response=await guarded_fetch(request.url,request.method,request.post_data,request.headers)
                    endpoint=search_template(request.url,body.query)
                    if endpoint and request.method=='GET' and len(samples)<4:
                        try:
                            data=json.loads(response['text'])
                            if len(response['text'])<100000:
                                samples.append({'search_url':endpoint,'data':data})
                        except ValueError:
                            pass
                    await route.fulfill(status=200,content_type=response['content_type'],body=base64.b64decode(response['base64']))
                except Exception:
                    await route.abort()
            await context.route('**/*',route_request)
            page=await context.new_page()
            await page.goto(body.url,wait_until='domcontentloaded',timeout=25000)
            search=page.locator('input[type="search"],input[name="q"],input[name="search"],input[name="query"]')
            for index in range(min(await search.count(),5)):
                field=search.nth(index)
                if await field.is_visible():
                    await field.fill(body.query,timeout=3000)
                    await field.press('Enter',timeout=3000)
                    await page.wait_for_timeout(5000)
                    break
            return {'samples':samples,'requests':requests}
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
        async with asyncio.timeout(55):
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
