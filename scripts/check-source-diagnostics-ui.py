"""Local browser acceptance against in-memory public-site fixtures."""
import asyncio,json,os,socket,sys,tempfile,threading,time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import uvicorn
from playwright.sync_api import sync_playwright,expect
from support import TestClient
from app.main import app
from app import source_assistant as sa,assistant_browser as observer
from discovery_fixtures import fetch,guarded,Opener,json_worker

async def slow_fetch(url,**kwargs):
    if '/slow/' in url:await asyncio.sleep(10)
    return await fetch(url,**kwargs)

def fill_target(page,value):
    try:page.get_by_label('Adresse du site ou nom de la plateforme').fill(value)
    except Exception:
        page.screenshot(path='.local/source-diagnostics-ui-failure.png')
        Path('.local/source-diagnostics-ui-failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
        raise

def main():
    artifacts=Path('.local');artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ,{'ANYTUBE_DATA':directory,'ANYTUBE_PUBLIC_URL':'','ANYTUBE_BROWSER_CDP_URL':''}))
        stack.enter_context(TestClient(app))
        from app.store import connect
        with connect() as db:db.execute('DELETE FROM sources')
        stack.enter_context(patch.object(sa,'http',side_effect=slow_fetch))
        stack.enter_context(patch.object(observer,'guarded_fetch',side_effect=guarded))
        stack.enter_context(patch.object(sa,'settings',return_value=sa.Settings(browser=sa.Service(url='http://fixture-observer'))))
        stack.enter_context(patch('app.main._run_worker',side_effect=json_worker))
        stack.enter_context(patch('app.connectors.build_opener',return_value=Opener()))
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,lifespan='off',log_level='error'))
        thread=threading.Thread(target=lambda:asyncio.run(server.serve()),daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            with sync_playwright() as p:
                browser=p.chromium.launch();page=browser.new_page(viewport={'width':1400,'height':1000})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                base=f'http://127.0.0.1:{port}'
                login=page.request.post(base+'/api/account/login',headers={'X-AnyTube':'1'},data={'name':'Test Admin','password':'Long test password 123'})
                assert login.ok,login.text()
                page.goto(base)
                page.get_by_role('button',name='Mes sources',exact=True).click()
                for case in ('html','json','rendered'):
                    print('UI_CASE',case,flush=True)
                    page.get_by_role('button',name='Découvrir une source',exact=True).click()
                    fill_target(page,'https://example.org/'+case+'/')
                    page.get_by_role('button',name='Découvrir la source',exact=True).click()
                    expect(page.get_by_text('Source ajoutée. Recherche contrôlée ; lecture non vérifiée.',exact=True)).to_be_visible(timeout=90000)
                    page.get_by_role('button',name='Fermer',exact=True).click()
                    page.get_by_role('button',name='Découvrir une source',exact=True).click()
                    page.get_by_role('button',name='https://example.org/'+case+'/ — Source ajoutée',exact=True).click()
                    summary=page.locator('.assistant-diagnostics > summary');summary.focus();page.keyboard.press('Enter')
                    expect(page.locator('.assistant-diagnostic').first).to_be_visible()
                    page.get_by_role('button',name='Fermer',exact=True).click()
                page.get_by_role('button',name='Découvrir une source',exact=True).click()
                page.get_by_label('Adresse du site ou nom de la plateforme').fill('https://example.org/broken/')
                page.get_by_role('button',name='Découvrir la source',exact=True).click()
                expect(page.get_by_text('Les deux recherches renvoient l’accueil ; endpoint non confirmé.',exact=True)).to_be_visible(timeout=90000)
                for width in (1400,390):
                    page.set_viewport_size({'width':width,'height':900})
                    for theme in ('light','dark'):
                        page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
                        if page.locator('.assistant-diagnostics').get_attribute('open') is None:
                            page.locator('.assistant-diagnostics > summary').click()
                        assert page.locator('dialog[open]').evaluate('(d)=>d.scrollWidth<=d.clientWidth+1')
                        page.screenshot(path=str(artifacts/f'source-diagnostics-{width}-{theme}.png'))
                page.get_by_role('button',name='Fermer',exact=True).click()
                page.get_by_role('button',name='Découvrir une source',exact=True).click()
                page.get_by_label('Adresse du site ou nom de la plateforme').fill('https://example.org/slow/')
                page.get_by_role('button',name='Découvrir la source',exact=True).click()
                page.get_by_role('button',name='Arrêter',exact=True).click()
                expect(page.get_by_text('Arrêtée — https://example.org/slow/',exact=True)).to_be_visible(timeout=10000)
                page.get_by_role('button',name='Fermer',exact=True).click()
                page.get_by_role('button',name='Explorer',exact=True).click()
                page.get_by_role('textbox',name='Rechercher des vidéos').fill('science')
                page.locator('#search-button').click()
                expect(page.get_by_role('heading',name='Résultats pour « science »')).to_be_visible(timeout=30000)
                expect(page.locator('#results > *').first).to_be_visible(timeout=30000)
                assert not errors,errors
                browser.close()
                print(json.dumps({'ui':'passed','scenarios':['html','json','rendered','broken','cancel'],'viewports':[1400,390],'themes':['light','dark'],'keyboard':True,'reopen':True}),flush=True)
        except Exception:
            try:
                page.screenshot(path=str(artifacts/'source-diagnostics-ui-failure.png'))
                (artifacts/'source-diagnostics-ui-failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
            except Exception:pass
            raise
        finally:
            server.should_exit=True;thread.join(timeout=10)

if __name__=='__main__':main()
