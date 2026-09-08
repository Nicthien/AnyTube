import asyncio
import io
import json
import time
import unittest
import zipfile
from unittest.mock import AsyncMock, patch
from app import source_assistant as sa, source_pages as pages
from app.store import connect, current_user, saved_sources
from app.pagination import signature
import test_source_assistant as existing
from test_source_assistant import config


def proof(candidate):
    return {'search':'verified','pagination':'first_page_only','engine':sa.engine_version(),'date':time.time(),
            'configuration_signature':signature(candidate),'checks':[{'query':'science','count':2},{'query':'music','count':2}],
            'pages':[{'url':'https://example.org/watch/'+str(i),'terms':[i%2],'status':state,'reason':'Observation de test.'}
                     for i,state in enumerate(('recognized','recognized','unrecognized_player','unchecked'))]}


class PageTests(unittest.IsolatedAsyncioTestCase):
    async def test_continue_and_cache_across_candidates(self):
        c=config();c['pagination']['mode']='single'
        async def worker(payload,**kwargs):
            if payload['query'].startswith('anytube-no-result-'):return {'items':[]}
            return {'items':[{'title':'Film','url':f'https://example.org/watch/{payload["query"]}-{i}'} for i in range(3)]}
        async def fetch(url,**kwargs):
            return {'text':'<video></video>' if url.endswith('-0') else '<video src="/fixture.mp4"></video>'}
        token=pages.cache.set({})
        try:
            with patch('app.main.run_worker',side_effect=worker),patch.object(sa,'http',side_effect=fetch) as network,patch.object(sa,'settings',return_value=sa.Settings()):
                for _ in range(2):
                    with self.assertRaises(sa.VideoEvidenceMissing) as error:await sa.verify(c,['science','music'])
                    summary=error.exception.evidence['page_summary']
                    self.assertEqual(summary['counts']['recognized'],4)
                    self.assertTrue(summary['eligible_partial'])
                self.assertEqual(network.await_count,6)
                self.assertEqual(len(error.exception.evidence['pages']),6)
        finally:pages.cache.reset(token)

    async def test_per_method_cache_and_connector_reinterpretation(self):
        token=pages.cache.set({})
        try:
            with patch.object(sa,'settings',return_value=sa.Settings(browser=sa.Service(url='http://browser:8010'))),patch.object(sa,'service_headers',return_value={}),patch.object(sa,'http',AsyncMock(side_effect=[{'text':'<video></video>'},{'text':json.dumps({'url':'https://example.org/watch/1','html':'<video src="/film.mp4"></video>'})}])) as network:
                first=await pages.observe('https://example.org/watch/1',config())
                self.assertEqual(first['status'],'recognized')
                second=await pages.observe('https://example.org/watch/1',{**config(),'search_url':'https://example.org/watch/1?q={query}'})
                self.assertEqual(second['status'],'non_video')
                self.assertEqual(network.await_count,2)
        finally:pages.cache.reset(token)

    async def test_statuses_and_no_positive_proof(self):
        for status,expected in [(404,'deleted'),(403,'access_required'),(503,'network_error')]:
            with patch.object(sa,'http',AsyncMock(return_value={'status':status,'text':'Unavailable'})),patch.object(sa,'settings',return_value=sa.Settings()):
                self.assertEqual((await pages.observe('https://example.org/watch/1',config()))['status'],expected)
        data=proof(config())
        for page in data['pages']:page['status']='unrecognized_player'
        self.assertFalse(pages.summarize(data)['eligible_partial'])
        data=proof(config());data['pages'][-1]['status']='non_video'
        self.assertFalse(pages.summarize(data)['eligible_partial'])
        observation=pages.inspect({'text':'<meta property="og:type" content="article"><h1>Article</h1>','status':200},'https://example.org/story/1','http')
        self.assertEqual(observation['status'],'non_video')

    async def test_cancellation_preserves_pending_pages(self):
        saved=[];token=pages.progress.set(lambda c,e:saved.append(json.loads(json.dumps(e))))
        async def observation(url,candidate):
            if url.endswith('2'):raise asyncio.CancelledError()
            return {'status':'recognized','method':'http','reason':'metadata','final_url':url}
        data={'search':'verified','pagination':'first_page_only'}
        try:
            with patch.object(pages,'observe',side_effect=observation):
                with self.assertRaises(asyncio.CancelledError):await pages.validate(config(),data,[{'https://example.org/1'},{'https://example.org/2'}])
            self.assertEqual(saved[-1]['page_summary']['counts']['unchecked'],1)
            self.assertEqual(saved[-1]['page_summary']['counts']['recognized'],1)
        finally:pages.progress.reset(token)


class PartialAPIs(unittest.TestCase):
    setUp=existing.AssistantAPITests.setUp
    tearDown=existing.AssistantAPITests.tearDown
    start=existing.AssistantAPITests.start

    def ready(self,**kwargs):
        job=self.start(**kwargs);candidate=config();data=proof(candidate)
        sa.update(job['id'],'needs_input',candidate=candidate,evidence=data)
        return job,candidate,data

    def accept(self,job):return self.client.post('/api/source-assistant/jobs/'+job['id']+'/accept-partial',headers=self.headers)

    def test_accept_duplicate_and_persistent_qualification(self):
        job,c,_=self.ready();first=self.accept(job)
        self.assertEqual(first.status_code,200,first.text)
        self.assertTrue(first.json()['partial_accepted'])
        self.assertEqual(self.accept(job).json()['added_source'],first.json()['added_source'])
        second,_,_=self.ready();self.assertEqual(self.accept(second).json()['added_source'],first.json()['added_source'])
        with connect() as db:db.execute('DELETE FROM source_assistant_jobs')
        source=next(s for s in saved_sources() if s['id']==first.json()['added_source'])
        self.assertEqual(source['validation']['level'],'partial')

    def test_stale_engine_changed_config_and_nonvideo_rejected(self):
        for change in ('date','engine','configuration_signature','non_video'):
            job,c,data=self.ready()
            if change=='date':data['date']=time.time()-86401
            elif change=='non_video':data['pages'][-1]['status']='non_video'
            else:data[change]='changed'
            sa.update(job['id'],evidence=data)
            self.assertEqual(self.accept(job).status_code,409)

    def test_update_backup_and_concurrent_change(self):
        job,c,_=self.ready();source=self.accept(job).json()['added_source']
        update,_,_=self.ready(source_id=source)
        self.assertEqual(self.accept(update).status_code,200)
        with connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM source_assistant_backups').fetchone()[0],1)
        other,_,_=self.ready(source_id=source)
        with connect() as db:db.execute('UPDATE sources SET connector=? WHERE id=?',(json.dumps({**c,'home_query':'changed'}),source))
        self.assertEqual(self.accept(other).status_code,409)

    def test_timeout_partial_snapshot_and_resume_reloads_observations(self):
        job=self.start()
        async def discovery(identifier,settings):
            data=proof(config())
            await pages.validate(config(),data,[{'https://example.org/watch/1'},{'https://example.org/watch/2'}])
        async def fetch(url,**kwargs):
            if url.endswith('/2'):raise asyncio.CancelledError()
            return {'text':'<video src="/film.mp4"></video>'}
        with patch.object(sa,'discover',side_effect=discovery),patch.object(sa,'http',side_effect=fetch) as network:
            for attempt in range(2):
                with self.assertRaises(asyncio.CancelledError):asyncio.run(sa.execute(job['id']))
                saved=sa.load(job['id'])
                self.assertEqual(saved['evidence']['page_summary']['counts']['recognized'],1)
                self.assertEqual(saved['evidence']['page_summary']['counts']['unchecked'],1)
                if attempt==0:
                    with patch.object(sa,'launch'):
                        resumed=self.client.post('/api/source-assistant/jobs/'+job['id']+'/resume',headers=self.headers,json={})
                    self.assertEqual(resumed.status_code,201,resumed.text)
                    self.assertEqual(resumed.json()['parent_job'],job['id'])
                    job=resumed.json()
            self.assertEqual(network.await_count,4)

    def test_export_old_active_terminal_and_secret_allowlist(self):
        job,c,data=self.ready()
        c.update(credential_id='CREDENTIAL_SENTINEL',body={'key':'BODY_SENTINEL'})
        for state in ('queued','running','needs_input','interrupted','timeout'):
            sa.update(job['id'],state,candidate=c,evidence=data,headers={'key':'HEADER_SENTINEL'},diagnostics=[{'message':'token="TOKEN_SENTINEL"','cookie':'COOKIE_SENTINEL'}])
            response=self.client.get('/api/source-assistant/jobs/'+job['id']+'/export')
            self.assertEqual(response.status_code,200)
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                self.assertEqual(set(archive.namelist()),{'resume.txt','diagnostic.json'})
                body=archive.read('diagnostic.json').decode();report=json.loads(body)
                self.assertEqual(report['active'],state in sa.ACTIVE)
                self.assertIn(job['id'],archive.read('resume.txt').decode())
                for secret in ('CREDENTIAL_SENTINEL','BODY_SENTINEL','HEADER_SENTINEL','TOKEN_SENTINEL','COOKIE_SENTINEL'):self.assertNotIn(secret,body)
        token=current_user.set('different-owner')
        try:
            from fastapi import HTTPException
            with self.assertRaises(HTTPException):sa.export_results(job['id'])
            with self.assertRaises(HTTPException):sa.accept_partial(job['id'])
        finally:current_user.reset(token)
