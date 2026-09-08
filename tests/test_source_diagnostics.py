import asyncio
import json
import unittest
from unittest.mock import patch,AsyncMock
from app import source_assistant as sa
from app.source_diagnostics import Attempts,ControlError,sink,scope
from app.connectors import Connector
from app.store import current_user
import test_source_assistant as existing
from test_html_search import config,fetch,ROOT


class DiagnosticUnits(unittest.TestCase):
    def test_get_form_preserves_relative_action_and_fixed_fields(self):
        page=sa.Page('https://example.org/catalog/')
        page.feed('<form action="../search?type=video"><input type="search" name="q"><input type="hidden" name="lang" value="fr"><input type="hidden" name="csrf_token" value="secret"></form>')
        self.assertEqual(page.forms,['https://example.org/search?type=video&lang=fr&q={query}'])
        page.feed('<form method="POST" action="/search"><input name="q"></form>')
        self.assertEqual(page.unsupported_forms,1)
        self.assertEqual(len(page.forms),1)

    def test_reserve_browser_slot_and_deduplicate_corrections(self):
        attempts=Attempts(True)
        first=config();second={**first,'home_query':'second'};third={**first,'home_query':'third'}
        self.assertTrue(attempts.claim(first))
        self.assertFalse(attempts.claim(first,correction=True))
        self.assertTrue(attempts.claim(second))
        self.assertFalse(attempts.claim(third))
        self.assertTrue(attempts.claim(third,browser=True))
        self.assertFalse(attempts.claim({**first,'home_query':'fourth'},browser=True))

    def test_diagnostics_redact_urls_and_bound_examples(self):
        from app.source_diagnostics import emit
        rows=[];token=sink.set(rows.append)
        try:
            emit(requested_url='https://user:PASS@example.org/?token=TOKEN&password=PASS',examples=[{'title':'Example','url':'https://example.org/?secret=SECRET'}]*10)
        finally:sink.reset(token)
        output=json.dumps(rows)
        for secret in ('PASS','TOKEN','SECRET'):self.assertNotIn(secret,output)
        self.assertEqual(len(rows[0]['examples']),3)


class ControlUnits(unittest.IsolatedAsyncioTestCase):
    async def test_empty_identical_and_witness_are_distinct(self):
        c=existing.config()
        for outputs,code in [([[],[],[]],'empty_results'),(['same','same',[]],'same_results'),(['one','two','one'],'witness_repeated')]:
            result=[{'items':[] if not q else [{'title':q,'url':'https://example.org/watch/'+q}]} for q in outputs]
            with patch('app.main.run_worker',new=AsyncMock(side_effect=result)):
                with self.assertRaises(ControlError) as raised:await sa.verify(c,['science','music'])
                self.assertEqual(raised.exception.code,code)


class DiagnosticAPIs(unittest.TestCase):
    setUp=existing.AssistantAPITests.setUp
    tearDown=existing.AssistantAPITests.tearDown
    start=existing.AssistantAPITests.start

    def test_html_pipeline_persists_controls_and_normal_search(self):
        job=self.start()
        with patch.object(sa,'http',side_effect=fetch):
            asyncio.run(sa.execute(job['id']))
            result=self.client.get('/api/source-assistant/jobs/'+job['id']).json()
            self.assertEqual(result['status'],'added',result)
            self.assertTrue(any(d.get('outcome')=='confirmed' for d in result['diagnostics']))
            self.assertTrue(any(d.get('provenance')=='form' for d in result['diagnostics']))
            response=self.client.post('/api/search',headers=self.headers,json={'query':'science','sources':[result['added_source']],'limit':3})
            self.assertEqual(len(response.json()['items']),3,response.text)
            reopened=self.client.get('/api/source-assistant/jobs/'+job['id']).json()
            self.assertEqual(result['diagnostics'],reopened['diagnostics'])

    def test_homepage_as_search_with_and_without_redirect(self):
        home='<form action="/fake"><input name="q"></form>'
        for redirect in (False,True):
            job=self.start()
            async def fake(url,**kwargs):
                if url.endswith('/api/v1/config'):return {'text':'{}'}
                return {'url':ROOT if redirect else url,'status':200,'content_type':'text/html','text':home}
            with patch.object(sa,'http',side_effect=fake):asyncio.run(sa.execute(job['id']))
            result=sa.load(job['id'])
            self.assertNotIn('added_source',result)
            self.assertIn('accueil',result['message'])
            self.assertTrue(any(d.get('code')=='endpoint_unconfirmed' for d in result['diagnostics']))

    def test_resume_reloads_and_keeps_previous_diagnostics(self):
        job=self.start()
        with patch.object(sa,'http',side_effect=fetch):asyncio.run(sa.execute(job['id']))
        previous=sa.load(job['id'])
        with patch.object(sa,'launch'):
            retry=self.client.post('/api/source-assistant/jobs/'+job['id']+'/resume',headers=self.headers,json={}).json()
        with patch.object(sa,'http',side_effect=fetch) as fresh:asyncio.run(sa.execute(retry['id']))
        self.assertGreater(fresh.await_count,0)
        self.assertEqual(sa.load(job['id'])['diagnostics'],previous['diagnostics'])
        self.assertEqual(sa.load(retry['id'])['added_source'],previous['added_source'])

    def test_cancel_and_deadline_preserve_partial_diagnostics(self):
        from app.source_diagnostics import emit
        for failure in (TimeoutError,asyncio.CancelledError):
            job=self.start()
            async def partial(*args):
                emit(phase='search',outcome='started',query='science')
                raise failure()
            with patch.object(sa,'discover',side_effect=partial):
                try:asyncio.run(sa.execute(job['id']))
                except asyncio.CancelledError:pass
            result=sa.load(job['id'])
            self.assertEqual(result['diagnostics'][0]['query'],'science')
            self.assertEqual(result['diagnostics'][-1]['outcome'],'interrupted')

    def test_old_jobs_and_owner_isolation(self):
        job=self.start()
        from app.store import connect
        with connect() as db:
            payload=json.loads(db.execute('SELECT payload FROM source_assistant_jobs WHERE id=?',(job['id'],)).fetchone()[0])
            payload.pop('diagnostics');payload.pop('diagnostics_version')
            db.execute('UPDATE source_assistant_jobs SET payload=? WHERE id=?',(json.dumps(payload),job['id']))
        self.assertEqual(sa.load(job['id'])['diagnostics'],[])
        self.assertEqual(sa.load(job['id'])['diagnostics_version'],0)
        token=current_user.set('other-user')
        try:
            with self.assertRaises(Exception):sa.load(job['id'])
        finally:current_user.reset(token)

    def test_resume_accepts_new_control_terms(self):
        job=self.start();sa.update(job['id'],'unresolved')
        with patch.object(sa,'launch'):
            response=self.client.post('/api/source-assistant/jobs/'+job['id']+'/resume',headers=self.headers,json={'queries':['history','nature']})
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(response.json()['queries'],['history','nature'])
        self.assertEqual(sa.load(job['id'])['queries'],['science','music'])

    def test_browser_candidate_keeps_reserved_slot(self):
        job=self.start()
        normal=config();normal['pagination']['mode']='single';normal['html']['next_selector']=''
        first=json.loads(json.dumps(normal));first['html']['items']='article.missing'
        second=json.loads(json.dumps(normal));second['html']['items']='article.other'
        rendered=json.loads(json.dumps(normal));rendered['html']['rendering']='chromium'
        def infer(*args):return [rendered] if len(args)>4 and args[4]=='chromium' else [first,second,normal]
        with patch.object(sa,'http',side_effect=fetch),patch('app.html_search.infer',side_effect=infer),patch.object(sa,'settings',return_value=sa.Settings(browser=sa.Service(url='http://observer'))):
            asyncio.run(sa.execute(job['id']))
        result=sa.load(job['id'])
        self.assertEqual(result['status'],'added',result)
        self.assertEqual(result['candidate']['html']['rendering'],'chromium')
        initial=[d for d in result['diagnostics'] if d.get('phase')=='candidate' and d.get('outcome')=='started']
        self.assertEqual(len(initial),3)

    def test_same_ai_correction_does_not_repeat_worker_calls(self):
        c=config();job=self.start()
        calls=[]
        async def fake_verify(candidate,queries):
            from app.source_diagnostics import confirmation
            calls.append(json.dumps(candidate,sort_keys=True))
            confirmation.get()['confirmed']=True
            raise ControlError('pagination_repeated','Page répétée.',True)
        with patch.object(sa,'http',side_effect=fetch),patch.object(sa,'verify',side_effect=fake_verify),patch.object(sa,'settings',return_value=sa.Settings(ai=sa.Service(kind='ollama'))),patch.object(sa,'ai_proposal',new=AsyncMock(side_effect=lambda settings,material: {'connector':material['candidate']})):
            asyncio.run(sa.execute(job['id']))
        self.assertEqual(len(calls),len(set(calls)))
        self.assertTrue(any(d.get('code')=='duplicate' for d in sa.load(job['id'])['diagnostics']))
