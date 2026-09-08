"""Public-site fixtures at example.org; all page requests stay in memory."""
import base64
import io
import json
from urllib.parse import urlsplit,parse_qs

counts={'http':0,'browser':0}

def response(url):
    parts=urlsplit(url);scenario=parts.path.strip('/').split('/')[0]
    query=parse_qs(parts.query).get('q',[''])[0]
    rows=[] if query.startswith('anytube-no-result-') else [{'title':query+' '+str(i),'url':f'https://example.org/{scenario}/watch/{query}-{i}'} for i in range(4)]
    home=f'<form action="/{scenario}/search"><input name="q" type="search"><input type="hidden" name="kind" value="video"></form>'
    kind='text/html'
    if '/api/v1/config' in parts.path:text='{}';kind='application/json'
    elif '/watch/' in parts.path:text='<video></video>' if scenario=='mixed' and parts.path.endswith('-0') else '<video src="https://example.org/fixture.mp4"></video>'
    elif scenario=='rotating' and parts.path.endswith('/search'):
        text='<h1>Page not found</h1>'+''.join(f'<article><a href="https://example.org/watch/{counts["http"]}-{i}">Film {i}</a></article>' for i in range(4))
    elif scenario=='broken':text=home
    elif parts.path.endswith('/search'):
        if scenario=='json':text=json.dumps({'items':rows});kind='application/json'
        else:
            cards=''.join(f'<article class="video"><a href="{r["url"]}"><img></a><h3><a href="{r["url"]}">{r["title"]}</a></h3></article>' for r in rows)
            if scenario=='rendered-error':cards='<h1>Page not found</h1>'+cards
            text='<main>'+cards+'</main>' if not scenario.startswith('rendered') else '<main id="results"></main><script>document.getElementById("results").innerHTML='+json.dumps(cards)+'</script>'
    else:text=home
    return {'url':url,'status':200,'text':text,'content_type':kind,'base64':base64.b64encode(text.encode()).decode()}

async def guarded(url,*args,**kwargs):
    counts['http']+=1
    return response(url)

async def fetch(url,**kwargs):
    if url.endswith('/observe'):
        from app.assistant_browser import Observation,observe
        counts['browser']+=1
        return {'text':json.dumps(await observe(Observation(**kwargs['body'])))}
    return await guarded(url)

class Opener:
    def open(self,request,**kwargs):
        counts['http']+=1
        value=response(request.full_url)
        result=io.BytesIO(value['text'].encode())
        result.status=200;result.url=request.full_url;result.headers={'Content-Type':value['content_type']}
        return result

async def json_worker(payload,*args,**kwargs):
    if payload.get('connector',{}).get('kind')=='html':
        from app.html_search import search
        return await search(payload)
    if payload.get('connector',{}).get('kind')!='json':
        return {'items':[],'has_more':False}
    from app.worker import run
    return run(payload)
