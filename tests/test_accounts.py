import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app, jobs
from app.store import connect, current_user
from app.library import persist, job_folder, restore_jobs

HEADERS={'X-AnyTube':'1'}
PASSWORD='A long private test password'


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.env=patch.dict('os.environ',{'ANYTUBE_DATA':self.folder.name,'ANYTUBE_PUBLIC_URL':''})
        self.env.start()
        self.log=patch('app.accounts.logging.getLogger');self.log.start()
        self.admin=TestClient(app);self.admin.__enter__()
        self.token=app.state.setup_token
        result=self.admin.post('/api/account/setup',json={'name':'Parent','password':PASSWORD,'token':self.token},headers=HEADERS)
        self.assertEqual(result.status_code,200,result.text)
        self.admin_id=self.admin.get('/api/account/me').json()['user']['id']
        self.member=TestClient(app)
        invite=self.admin.post('/api/admin/invitations',headers=HEADERS).json()['token']
        result=self.member.post('/api/account/join',json={'name':'Membre','password':PASSWORD,'token':invite},headers=HEADERS)
        self.assertEqual(result.status_code,200,result.text)
        self.member_id=self.member.get('/api/account/me').json()['user']['id']
        self.used_invite=invite

    def tearDown(self):
        self.member.close();self.admin.__exit__(None,None,None);self.log.stop();self.env.stop();self.folder.cleanup()

    def test_sources_preferences_personal_and_files_are_private(self):
        self.assertEqual(self.member.get('/api/sources').json()['items'],[])
        self.assertEqual(self.member.patch('/api/sources/Youtube',json={'enabled':False},headers=HEADERS).status_code,404)
        self.assertEqual(self.member.post('/api/sources',json={'id':'Youtube'},headers=HEADERS).status_code,201)
        self.member.patch('/api/sources/Youtube',json={'name':'Mon YouTube'},headers=HEADERS)
        self.assertEqual(next(x for x in self.admin.get('/api/sources').json()['items'] if x['id']=='Youtube')['name'],'YouTube')
        self.member.put('/api/account/preferences',json={'theme':'light'},headers=HEADERS)
        self.assertEqual(self.admin.get('/api/account/me').json()['preferences'],{})
        self.member.put('/api/personal',json={'url':'https://example.org/video','title':'Privé','favorite':True,'position':42},headers=HEADERS)
        self.assertEqual(self.admin.get('/api/personal').json()['items'],[])
        job={'id':'a'*32,'owner':self.admin_id,'status':'ready','created':time.time(),'url':'https://example.org/video','destination':'library','size':10}
        path=job_folder(job);path.mkdir(parents=True);(path/'video.mp4').write_bytes(b'0123456789');jobs[job['id']]=job;persist(job)
        for suffix in ('','/file'):
            self.assertEqual(self.member.get('/api/media/'+job['id']+suffix).status_code,404)
        self.assertEqual(self.member.delete('/api/media/'+job['id'],headers=HEADERS).status_code,404)
        self.assertEqual(self.member.post('/api/media/'+job['id']+'/keep',headers=HEADERS).status_code,404)
        self.assertEqual(self.member.get('/api/media').json()['items'],[])
        self.assertEqual(self.admin.get('/api/media/'+job['id']+'/file',headers={'Range':'bytes=2-4'}).content,b'234')
        restored=restore_jobs();self.assertEqual(restored[job['id']]['status'],'ready');self.assertTrue((path/'video.mp4').exists())

    def test_https_canonical_login_and_local_redirect(self):
        with patch.dict('os.environ', {'ANYTUBE_PUBLIC_URL': 'https://anytube.example'}):
            local = TestClient(app, base_url='http://192.168.0.5:18088')
            response = local.get('/?view=library', follow_redirects=False)
            self.assertEqual(response.status_code, 307)
            self.assertEqual(response.headers['location'], 'https://anytube.example/?view=library')
            self.assertEqual(local.get('/api/health').status_code, 200)
            self.assertEqual(local.post('/api/account/login', json={'name':'Parent','password':PASSWORD}, headers=HEADERS).status_code, 400)
            secure = TestClient(app, base_url='https://anytube.example')
            response = secure.post('/api/account/login', json={'name':'Parent','password':PASSWORD}, headers={**HEADERS,'Origin':'https://anytube.example'})
            self.assertEqual(response.status_code, 200)
            self.assertIn('Secure', response.headers['set-cookie'])
            self.assertEqual(secure.get('/api/account/me').json()['user']['id'], self.admin_id)
            # TLS terminates at Zoraxy: upstream HTTP with the public Host must not loop.
            upstream = TestClient(app, base_url='http://anytube.example')
            self.assertEqual(upstream.get('/', follow_redirects=False).status_code, 200)
            local.close();secure.close();upstream.close()

    def test_tokens_sessions_and_admin_boundaries(self):
        anonymous=TestClient(app)
        self.assertEqual(anonymous.get('/api/sources').status_code,401)
        self.assertEqual(self.member.post('/api/admin/invitations',headers=HEADERS).status_code,403)
        self.assertEqual(anonymous.post('/api/account/setup',json={'name':'Other','password':PASSWORD,'token':self.token},headers=HEADERS).status_code,400)
        self.assertEqual(anonymous.post('/api/account/join',json={'name':'Other','password':PASSWORD,'token':self.used_invite},headers=HEADERS).status_code,400)
        invite=self.admin.post('/api/admin/invitations',headers=HEADERS).json()['token']
        with connect() as db:db.execute('UPDATE invitations SET expires=0')
        self.assertEqual(anonymous.post('/api/account/join',json={'name':'Other','password':PASSWORD,'token':invite},headers=HEADERS).status_code,400)
        self.assertEqual(self.member.put('/api/account/preferences',json={},headers={'Origin':'https://evil.example','X-AnyTube':'1'}).status_code,403)
        self.assertEqual(self.member.put('/api/account/preferences',json={}).status_code,403)
        self.member.delete('/api/account/sessions',headers=HEADERS)
        self.assertEqual(self.member.get('/api/sources').status_code,401)
        anonymous.close()

    def test_password_change_revokes_other_sessions_and_disabled_account(self):
        other=TestClient(app)
        self.assertEqual(other.post('/api/account/login',json={'name':'Membre','password':PASSWORD},headers=HEADERS).status_code,200)
        response=self.member.post('/api/account/password',json={'current_password':PASSWORD,'new_password':PASSWORD+' changed'},headers=HEADERS)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(other.get('/api/sources').status_code,401)
        self.assertEqual(self.member.get('/api/sources').status_code,200)
        self.admin.patch('/api/admin/users/'+self.member_id,json={'disabled':True,'quota':1024**3},headers=HEADERS)
        self.assertEqual(self.member.get('/api/sources').status_code,401)
        other.close()

    def test_quota_keep_and_interrupted_jobs(self):
        job={'id':'b'*32,'owner':self.member_id,'status':'ready','created':time.time(),'url':'https://example.org/video','destination':'cache','size':10}
        path=job_folder(job);path.mkdir(parents=True);(path/'video.mp4').write_bytes(b'0123456789');jobs[job['id']]=job;persist(job)
        with connect() as db:db.execute('UPDATE users SET quota=5 WHERE id=?',(self.member_id,))
        self.assertEqual(self.member.post('/api/media/'+job['id']+'/keep',headers=HEADERS).status_code,409)
        self.assertTrue((path/'video.mp4').exists())
        with connect() as db:db.execute('UPDATE users SET quota=100 WHERE id=?',(self.member_id,))
        self.assertEqual(self.member.post('/api/media/'+job['id']+'/keep',headers=HEADERS).status_code,200)
        self.assertFalse(path.exists());self.assertTrue((job_folder(jobs[job['id']])/'video.mp4').exists())
        running={**job,'id':'c'*32,'status':'preparing'};persist(running)
        self.assertEqual(restore_jobs()[running['id']]['status'],'error')
