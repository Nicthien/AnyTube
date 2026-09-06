from fastapi.testclient import TestClient as BaseClient
from app.store import current_user


class TestClient(BaseClient):
    def __enter__(self):
        super().__enter__()
        headers = {'X-AnyTube':'1'}
        if self.app.state.setup_token:
            response = self.post('/api/account/setup',json={'token':self.app.state.setup_token,'name':'Test Admin','password':'Long test password 123'},headers=headers)
        else:
            response = self.post('/api/account/login',json={'name':'Test Admin','password':'Long test password 123'},headers=headers)
        assert response.status_code == 200, response.text
        self.context = current_user.set(self.get('/api/account/me').json()['user']['id'])
        return self

    def __exit__(self,*args):
        try:
            return super().__exit__(*args)
        finally:
            current_user.reset(self.context)
