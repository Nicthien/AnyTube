"""Neutral local fixture: real CDP screen/input, cookies, storage and manual upload."""
import asyncio
import base64
import json
import os
import socket
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
sys.stdout.reconfigure(encoding='utf-8')
import uvicorn
from playwright.async_api import async_playwright
from support import TestClient
from app.main import app
from app import assistant_browser as observer
from app.interactive_browser import live, close


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


async def fixture(url, method, body, headers, **kwargs):
    authorized = 'access=validated' in headers.get('cookie', '')
    response = {'status': 200, 'url': url, 'content_type': 'text/html; charset=utf-8', 'headers': {}}
    if url.endswith('/confirm'):
        response.update(status=303, location='https://example.org/', set_cookies=['access=validated; Path=/; Secure; HttpOnly; SameSite=Lax'])
        text = ''
    elif not authorized:
        text = '<html><body><main><h1>Accès au site de test</h1><form action="/confirm" method="post"><button style="width:300px;height:100px">Continuer sur le site de test</button></form></main></body></html>'
    else:
        text = '<html><body><h1>Session de test validée</h1><input type="file" accept="application/pdf"><script>localStorage.setItem("test-auth","local-storage-value")</script></body></html>'
    response.update(text=text, base64=base64.b64encode(text.encode()).decode())
    return response


async def main():
    with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
        key = Path(directory) / 'vault.key'; key.write_bytes(os.urandom(32))
        app_port, service_port = port(), port()
        stack.enter_context(patch.dict(os.environ, {'ANYTUBE_DATA': directory, 'ANYTUBE_VAULT_KEY_FILE': str(key),
            'ANYTUBE_PUBLIC_URL': '', 'ANYTUBE_BROWSER_CDP_URL': '', 'ANYTUBE_BROWSER_TOKEN': 'fixture-only-service-token',
            'ANYTUBE_INTERACTIVE_URL': f'http://127.0.0.1:{service_port}', 'ANYTUBE_INTERACTIVE_TOKEN': 'fixture-only-service-token'}))
        stack.enter_context(TestClient(app))
        from app.store import connect
        with connect() as db:
            db.execute('DELETE FROM sources')
        stack.enter_context(patch.object(observer, 'guarded_fetch', side_effect=fixture))
        servers = [uvicorn.Server(uvicorn.Config(application, host='127.0.0.1', port=p, lifespan='off', log_level='error', timeout_graceful_shutdown=3))
                   for application, p in ((app, app_port), (observer.app, service_port))]
        tasks = [asyncio.create_task(server.serve()) for server in servers]
        try:
            while not all(server.started for server in servers):
                await asyncio.sleep(.05)
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                page = await browser.new_page(viewport={'width': 1400, 'height': 1000})
                errors = []; page.on('pageerror', lambda error: errors.append(str(error)))
                base = f'http://127.0.0.1:{app_port}'
                response = await page.request.post(base + '/api/account/login', headers={'X-AnyTube':'1'},
                    data={'name':'Test Admin','password':'Long test password 123'})
                assert response.ok
                await page.goto(base)
                await page.evaluate("() => { openBrowserSession('https://example.org/'); }")
                try:
                    await page.get_by_text('Session ouverte.', exact=False).wait_for(timeout=60000)
                except Exception:
                    print('OPEN_FAILURE', await page.locator('body').inner_text(), 'LIVE', list(live), flush=True)
                    await browser.close()
                    raise
                canvas = page.locator('.browser-session-screen')
                # Only this neutral fixture is clicked; production gates stay human-operated.
                box = await canvas.bounding_box()
                await page.mouse.click(box['x'] + 150 * box['width']/1280, box['y'] + 125 * box['height']/800)
                await asyncio.sleep(1)
                session_id = next(iter(live))
                remote = live[session_id]['page']
                try:
                    await remote.get_by_text('Session de test validée', exact=True).wait_for(timeout=20000)
                except Exception:
                    print('FIXTURE_FAILURE', remote.url, live[session_id].get('network_error'), (await remote.content())[:1000], flush=True)
                    raise
                assert await remote.evaluate('localStorage.getItem("test-auth")') == 'local-storage-value'
                # Trigger the site's file chooser through the public screen protocol.
                bounds = await remote.locator('input[type=file]').bounding_box()
                box = await canvas.bounding_box()
                await page.mouse.click(box['x']+(bounds['x']+10)*box['width']/1280,
                                       box['y']+(bounds['y']+10)*box['height']/800)
                await asyncio.sleep(.5)
                selected = page.locator('.browser-session-dialog input[type=file]')
                # The no-DOM-change chooser can require a fresh frame.
                await live[session_id]['cdp'].send('Page.stopScreencast')
                await live[session_id]['cdp'].send('Page.startScreencast', {'format':'jpeg'})
                await asyncio.sleep(.5)
                await selected.set_input_files({'name':'test.pdf','mimeType':'application/pdf','buffer':b'%PDF-1.7\nneutral fixture'})
                try:
                    await page.get_by_text('Fichier transmis au champ du site.', exact=True).wait_for(timeout=20000)
                except Exception:
                    print('UPLOAD_FAILURE', await page.locator('.browser-session-dialog').inner_text(), flush=True)
                    raise
                assert await remote.locator('input[type=file]').evaluate('(input)=>input.files[0].size') == 24
                for width in (1400, 390):
                    await page.set_viewport_size({'width':width,'height':900})
                    for theme in ('light','dark'):
                        await page.evaluate('(theme)=>document.documentElement.dataset.theme=theme', theme)
                        assert await page.locator('.browser-session-dialog').evaluate('(d)=>d.scrollWidth<=d.clientWidth+1')
                        if os.environ.get('ANYTUBE_FIXTURE_SCREENSHOTS') == '1':
                            Path('.local').mkdir(exist_ok=True)
                            await page.screenshot(path=f'.local/interactive-{width}-{theme}.png')
                await page.get_by_role('button', name='Enregistrer la session et reprendre').click()
                await page.locator('.browser-session-dialog').wait_for(state='detached', timeout=20000)
                listing = await page.request.get(base + '/api/browser-sessions')
                saved = (await listing.json())['items'][0]
                assert saved['state'] == 'saved' and not live
                await page.evaluate('(id)=>{openBrowserSession("https://example.org/","",id)}', saved['id'])
                try:
                    await page.get_by_text('Session ouverte.', exact=False).wait_for(timeout=60000)
                except Exception:
                    print('REOPEN_FAILURE', await page.locator('.browser-session-dialog').inner_text(),
                          {k:{'connected':s['connected'],'url':s['page'].url} for k,s in live.items()}, flush=True)
                    await browser.close()
                    raise
                assert await live[saved['id']]['page'].locator('h1').inner_text() == 'Session de test validée'
                await page.request.delete(base + '/api/browser-sessions/' + saved['id'], headers={'X-AnyTube':'1'})
                assert not live
                await page.locator('.browser-session-dialog').evaluate('(d)=>d.close()')
                await page.evaluate('()=>openNetworkSettings()')
                for width in (1400,390):
                    await page.set_viewport_size({'width':width,'height':1000})
                    for theme in ('light','dark'):
                        await page.evaluate('(theme)=>document.documentElement.dataset.theme=theme',theme)
                        assert await page.locator('dialog[open]').evaluate('(d)=>d.scrollWidth<=d.clientWidth+1')
                await page.get_by_role('button',name='Appliquer le trajet',exact=True).click()
                await page.get_by_text('Trajet enregistré.',exact=False).wait_for()
                await page.keyboard.press('Escape')
                assert await page.locator('dialog[open]').count()==0
                assert not errors, errors
                await browser.close()
                print('INTERACTIVE_FIXTURE_OK: CDP, manual fixture action, cookie/storage restore, upload, delete, mobile/themes')
        finally:
            for identifier in list(live):
                await close(identifier)
            for server in servers:
                server.should_exit = True
            await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == '__main__':
    asyncio.run(main())
