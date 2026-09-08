"""Local complete discovery -> saved source -> normal search fixtures.

Install optional playwright==1.62.0 and its Chromium for --browser.
Content is always simulated. --configured-browser explicitly uses the configured CDP service.
"""
import argparse,asyncio,json,os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from support import TestClient
from app.main import app
from app import source_assistant as sa
from app import assistant_browser as browser
from discovery_fixtures import fetch,guarded,Opener,json_worker,counts

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser',action='store_true');parser.add_argument('--configured-browser',action='store_true');args=parser.parse_args()
    if args.configured_browser: args.browser=True
    cases=['html','json','broken']+(['rendered'] if args.browser else [])
    output=[]
    with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'ANYTUBE_DATA':directory,'ANYTUBE_BROWSER_CDP_URL':os.environ.get('ANYTUBE_BROWSER_CDP_URL','') if args.configured_browser else ''}),TestClient(app) as client,patch.object(sa,'http',side_effect=fetch),patch.object(browser,'guarded_fetch',side_effect=guarded),patch('app.main._run_worker',side_effect=json_worker),patch('app.connectors.build_opener',return_value=Opener()):
        for case in cases:
            counts.update(http=0,browser=0);start=time.monotonic()
            settings=sa.Settings(browser=sa.Service(url='http://fixture-observer' if case=='rendered' else ''))
            with patch.object(sa,'settings',return_value=settings),patch.object(sa,'launch'):
                job=client.post('/api/source-assistant/jobs',headers={'X-AnyTube':'1'},json={'target':'https://example.org/'+case+'/'}).json()
                asyncio.run(sa.execute(job['id']))
                saved=client.get('/api/source-assistant/jobs/'+job['id']).json()
                assert saved['diagnostics'],saved
                if case=='broken':
                    assert saved['status']=='unresolved' and 'accueil' in saved['message'],saved
                else:
                    assert saved['status']=='added',saved
                    result=client.post('/api/search',headers={'X-AnyTube':'1'},json={'query':'science','sources':[saved['added_source']],'limit':3}).json()
                    assert len(result['items'])==3 and not result['errors'],result
                assert client.get('/api/source-assistant/jobs/'+job['id']).json()['diagnostics']==saved['diagnostics']
                output.append({'case':case,'status':saved['status'],'seconds':round(time.monotonic()-start,3),'requests':dict(counts),'diagnostics':len(saved['diagnostics']),'skipped':sum(d.get('code')=='duplicate' for d in saved['diagnostics']),'manual_connector_edits':0})
    print(json.dumps(output,indent=2),flush=True)

if __name__=='__main__':main()
