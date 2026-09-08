"""Internal interactive Chromium protocol. Only the AnyTube backend may connect."""
import asyncio
import base64
import contextlib
import json
import time
import html
from urllib.parse import urljoin

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from app.connectors import public_url

router = APIRouter()
live = {}
lock = asyncio.Lock()
IDLE = 15 * 60


class Open(BaseModel):
    model_config = ConfigDict(extra='forbid')
    owner: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=2000)
    revision: str = Field(default='direct', max_length=100)
    state: dict = Field(default_factory=lambda: {'cookies': [], 'origins': []})


async def close(identifier):
    session = live.pop(identifier, None)
    if session:
        for task in session['tasks']:
            if task is not asyncio.current_task():
                task.cancel()
        await session['context'].close()
        await session['browser'].close()
        await session['playwright'].stop()


def touch(identifier):
    session = live.get(identifier)
    if not session or time.monotonic() - session['activity'] >= IDLE:
        raise HTTPException(410, 'Session interactive fermée ou expirée.')
    session['activity'] = time.monotonic()
    return session


async def expire(identifier):
    while identifier in live:
        await asyncio.sleep(10)
        if identifier in live and time.monotonic() - live[identifier]['activity'] >= IDLE:
            await close(identifier)


@router.post('/interactive/{identifier}')
async def open_session(identifier: str, body: Open, request: Request):
    from app.assistant_browser import authorize, context_options, open_browser, guarded_fetch
    authorize(request)
    public_url(body.url)
    if len(json.dumps(body.state).encode()) > 1024 * 1024:
        raise HTTPException(413, 'État trop volumineux.')
    async with lock:
        if identifier in live:
            if live[identifier]['owner'] != body.owner:
                raise HTTPException(403, 'Accès refusé.')
            return {'active': True}
        for old in list(live):
            if time.monotonic() - live[old]['activity'] >= IDLE:
                await close(old)
        if len(live) >= 2 or any(s['owner'] == body.owner for s in live.values()):
            raise HTTPException(409, 'Une session par utilisateur et deux sur le serveur au maximum.')
        from playwright.async_api import async_playwright
        playwright = await async_playwright().start()
        browser = None
        try:
            browser = await open_browser(playwright)
            context = await browser.new_context(**context_options(), storage_state=body.state,
                                                viewport={'width': 1280, 'height': 800})
            await context.clear_permissions()
            await context.route_web_socket('**/*', lambda ws: ws.close())
            network = asyncio.Semaphore(4)
            count = 0

            async def route_request(route):
                nonlocal count
                count += 1
                req = route.request
                # Browser receives no direct networking capability, including uploads.
                if count > 2000 or req.method not in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
                    return await route.abort()
                try:
                    async with network:
                        response = await guarded_fetch(req.url, req.method, req.post_data_buffer,
                                                       await req.all_headers(), interactive=True)
                    headers = response.get('headers', {})
                    if response.get('location'):
                        destination = urljoin(req.url, response['location'])
                        public_url(destination)
                        # Playwright route handlers do not intercept a native
                        # redirect chain. Start a fresh, intercepted navigation;
                        # never let the dead-proxy fallback perform a redirect.
                        if req.is_navigation_request() and (req.method in ('GET', 'HEAD') or response['status'] in (301, 302, 303)):
                            if response.get('set_cookies'):
                                headers['set-cookie'] = '\n'.join(response['set_cookies'])
                            await route.fulfill(status=200, headers=headers, content_type='text/html',
                                body='<meta http-equiv="refresh" content="0;url=' + html.escape(destination, quote=True) + '">')
                            return
                        # Replaying a POST/upload or changing the origin of a
                        # fetched resource without browser validation is unsafe.
                        await route.abort()
                        return
                    if response.get('set_cookies'):
                        headers['set-cookie'] = '\n'.join(response['set_cookies'])
                    await route.fulfill(status=response['status'], headers=headers,
                                        content_type=response.get('content_type', ''),
                                        body=base64.b64decode(response['base64']))
                except Exception as error:
                    if identifier in live:
                        live[identifier]['network_error'] = type(error).__name__
                    await route.abort()

            await context.route('**/*', route_request)
            page = await context.new_page()
            # No implicit dialog acceptance or automatic age/consent interaction.
            page.on('dialog', lambda dialog: dialog.dismiss())
            page.on('popup', lambda popup: popup.close())
            page.on('download', lambda download: download.cancel())
            cdp = await context.new_cdp_session(page)
            live[identifier] = {'owner': body.owner, 'playwright': playwright, 'browser': browser,
                                'revision': body.revision,
                                'context': context, 'page': page, 'cdp': cdp, 'activity': time.monotonic(),
                                'tasks': [], 'connected': False, 'chooser': None}
            page.on('filechooser', lambda chooser: live.get(identifier, {}).update(chooser=chooser))
            live[identifier]['tasks'].append(asyncio.create_task(expire(identifier)))
            try:
                await page.goto(body.url, wait_until='domcontentloaded', timeout=30000)
            except Exception:
                pass  # The visible browser and explicit navigation error remain available.
            return {'active': True}
        except Exception:
            if identifier in live:
                await close(identifier)
            else:
                if browser:
                    await browser.close()
                await playwright.stop()
            raise HTTPException(503, 'Chromium interactif indisponible.')


@router.get('/interactive/{identifier}/state')
async def state(identifier: str, request: Request):
    from app.assistant_browser import authorize
    authorize(request)
    session = touch(identifier)
    return {'state': await session['context'].storage_state(indexed_db=True), 'url': session['page'].url,
            'revision': session['revision']}


@router.delete('/interactive/{identifier}')
async def remove(identifier: str, request: Request):
    from app.assistant_browser import authorize
    authorize(request)
    await close(identifier)
    return {'closed': True}


@router.delete('/interactive')
async def close_all(request: Request):
    from app.assistant_browser import authorize
    authorize(request)
    for identifier in list(live):
        await close(identifier)
    return {'closed': True}


@router.post('/interactive/{identifier}/file')
async def upload(identifier: str, request: Request):
    from app.assistant_browser import authorize
    authorize(request)
    session = touch(identifier)
    chooser = session.pop('chooser', None)
    if chooser is None:
        raise HTTPException(409, 'Choisissez d’abord le champ de fichier dans le site.')
    raw = bytearray()
    try:
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 20 * 1024 * 1024:
                raise HTTPException(413, 'Fichier limité à 20 Mo.')
        mime, name = file_type(raw)
        await chooser.set_files({'name': name, 'mimeType': mime, 'buffer': bytes(raw)}, timeout=15000)
        # Chromium retains the selected input until submission or context closure;
        # the service keeps no second copy and writes nothing to disk.
        return {'transferred': True}
    finally:
        raw[:] = b'\x00' * len(raw)
        raw.clear()
        session['chooser'] = None


def file_type(raw):
    if raw.startswith(b'%PDF-'):
        return 'application/pdf', 'document.pdf'
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png', 'image.png'
    if raw.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg', 'image.jpg'
    raise HTTPException(422, 'Choisissez un fichier PDF, JPEG ou PNG.')


@router.websocket('/interactive/{identifier}/screen')
async def screen(identifier: str, ws: WebSocket):
    from app.assistant_browser import authorize
    authorize(ws)
    session = touch(identifier)
    if session['connected']:
        await ws.close(code=1008)
        return
    await ws.accept()
    session['connected'] = True
    session['tasks'].append(asyncio.current_task())
    cdp, page = session['cdp'], session['page']
    frames = asyncio.Queue(maxsize=1)

    async def frame(event):
        await cdp.send('Page.screencastFrameAck', {'sessionId': event['sessionId']})
        if frames.full():
            frames.get_nowait()
        frames.put_nowait(event)

    async def send_frames():
        while True:
            try:
                event = await asyncio.wait_for(frames.get(), 1)
            except TimeoutError:
                await ws.send_json({'type': 'status', 'url': page.url, 'file_requested': session.get('chooser') is not None})
                continue
            await ws.send_json({'type': 'frame', 'image': event['data'], 'url': page.url,
                                'file_requested': session.get('chooser') is not None})

    cdp.on('Page.screencastFrame', frame)
    sender = asyncio.create_task(send_frames())
    try:
        await cdp.send('Page.startScreencast', {'format': 'jpeg', 'quality': 70, 'maxWidth': 1280, 'maxHeight': 800})
        while True:
            raw = await asyncio.wait_for(ws.receive_text(), IDLE)
            if len(raw) > 16384:
                raise ValueError('Commande trop longue.')
            data = json.loads(raw)
            touch(identifier)
            kind = data.get('type')
            if kind == 'resize':
                width, height = int(data.get('width',1280)), int(data.get('height',800))
                if 320 <= width <= 1280 and 400 <= height <= 800:
                    await page.set_viewport_size({'width':width,'height':height})
            elif kind == 'mouse':
                x, y = float(data['x']), float(data['y'])
                if not (0 <= x <= 1280 and 0 <= y <= 800):
                    continue
                event = data.get('event')
                if event not in ('mousePressed', 'mouseReleased', 'mouseMoved', 'mouseWheel'):
                    continue
                params = {'type': event, 'x': x, 'y': y, 'button': 'left', 'clickCount': 1}
                if event == 'mouseWheel':
                    params.update(deltaX=max(-2000, min(2000, float(data.get('dx', 0)))),
                                  deltaY=max(-2000, min(2000, float(data.get('dy', 0)))))
                await cdp.send('Input.dispatchMouseEvent', params)
            elif kind == 'text':
                await cdp.send('Input.insertText', {'text': str(data.get('text', ''))[:4000]})
            elif kind == 'key' and data.get('key') in ('Enter', 'Tab', 'Backspace', 'Delete', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'):
                key = data['key']
                codes = {'Enter': 13, 'Tab': 9, 'Backspace': 8, 'Delete': 46, 'Escape': 27,
                         'ArrowUp': 38, 'ArrowDown': 40, 'ArrowLeft': 37, 'ArrowRight': 39,
                         'Home': 36, 'End': 35, 'PageUp': 33, 'PageDown': 34}
                await cdp.send('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': key,
                               'windowsVirtualKeyCode': codes[key], 'modifiers': 8 if data.get('shift') else 0})
                await cdp.send('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': key, 'windowsVirtualKeyCode': codes[key]})
            elif kind == 'navigate':
                url = str(data.get('url', ''))[:2000]
                public_url(url)
                await page.goto(url, wait_until='domcontentloaded', timeout=25000)
    except (WebSocketDisconnect, TimeoutError, ValueError, asyncio.CancelledError):
        pass
    finally:
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
        cdp.remove_listener('Page.screencastFrame', frame)
        with contextlib.suppress(Exception):
            await cdp.send('Page.stopScreencast')
        session['connected'] = False
        with contextlib.suppress(ValueError):
            session['tasks'].remove(asyncio.current_task())
        with contextlib.suppress(Exception):
            await ws.close(code=1000)
