"""Acceptance against the disposable named local validation container, never production."""
import json
from pathlib import Path
import re
import subprocess
import time
import httpx

BASE='http://127.0.0.1:18089'
CONTAINER='anytube-sources-validation'
NAME='AnyTube source QA'
PASSWORD='AnyTube-local-QA-2026!!'


def main():
    result={'environment':'docker-validation','base':BASE,'checks':{}}
    with httpx.Client(base_url=BASE,headers={'X-AnyTube':'1'},timeout=130) as client:
        def api(method,path,**kwargs):
            response=client.request(method,path,**kwargs)
            response.raise_for_status()
            return response
        health=api('GET','/api/health').json()
        if api('GET','/api/account/me').json()['setup_required']:
            logs=subprocess.run(['docker','logs',CONTAINER],capture_output=True,text=True,encoding='utf-8').stderr
            token=re.findall(r'usage unique (\S+)',logs)[-1]
            api('POST','/api/account/setup',json={'token':token,'name':NAME,'password':PASSWORD})
        else:
            api('POST','/api/account/login',json={'name':NAME,'password':PASSWORD})
        result['health']=health
        result['checks']['vault_ready']=api('GET','/api/credentials').json()['ready']
        first=api('POST','/api/search',json={'query':'nature','sources':['Dailymotion'],'limit':2}).json()
        second=api('POST','/api/search',json={'query':'nature','sources':['Dailymotion'],'limit':2,'cursors':first['next_cursors']}).json()
        result['checks']['dailymotion_pages']=[len(first['items']),len(second['items'])]
        result['checks']['dailymotion_distinct']=not ({i['url'] for i in first['items']}&{i['url'] for i in second['items']})
        url='https://www.youtube.com/watch?v=aqz-KE-bpKQ'
        for operation in ('resolve','stream','video','audio'):
            try:
                if operation=='resolve':
                    resolved=api('POST','/api/media/resolve',json={'url':url,'source_id':'Youtube'}).json()
                    result['checks']['resolved_formats']=len(resolved['formats'])
                elif operation=='stream':
                    stream=api('POST','/api/playback',json={'url':url,'source_id':'Youtube'}).json()
                    resource=api('GET',stream['choices'][0]['url'],headers={'Range':'bytes=0-1023'})
                    result['checks']['stream']={'status':resource.status_code,'bytes':len(resource.content),'mime':resource.headers.get('content-type')}
                    api('DELETE','/api/playback/'+stream['id'])
                else:
                    job=api('POST','/api/media',json={'url':url,'source_id':'Youtube','destination':'library','media_kind':operation}).json()
                    deadline=time.monotonic()+620
                    while job['status']=='preparing' and time.monotonic()<deadline:
                        time.sleep(2)
                        job=api('GET','/api/media/'+job['id']).json()
                    result['checks'][operation]={'status':job['status'],'id':job['id'],'size':job.get('size'),'error':job.get('error')}
                    if job['status']=='ready':
                        ranged=api('GET','/api/media/'+job['id']+'/file',headers={'Range':'bytes=0-99'})
                        assert ranged.status_code==206 and len(ranged.content)==100
                        result['checks'][operation]['range']=206
            except Exception as exc:
                result['checks'][operation]={'status':'failed','detail':str(exc).split('\n')[0]}
            print(operation, json.dumps(result['checks'].get(operation, result['checks'].get('resolved_formats'))),flush=True)
    output=Path('docs/sources-docker-validation.json')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(output,flush=True)


if __name__=='__main__':
    main()
