"""Authenticated user-facing browser bridge. Service credentials never leave the server."""
import asyncio
import contextlib
import json
import os
import socket
import http.client
import ssl
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from app import browser_state
from app.store import connect, owner, current_user

router = APIRouter(prefix='/api/browser-sessions')


def endpoint():
    value = os.environ.get('ANYTUBE_INTERACTIVE_URL', '').rstrip('/')
    token = os.environ.get('ANYTUBE_INTERACTIVE_TOKEN', '')
    parts = urlsplit(value)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or not token:
        raise HTTPException(503, 'Le service Chromium intégré n’est pas configuré sur le serveur.')
    return value, token


async def call(path, method='GET', body=None, binary=None):
    base, token = endpoint()
    parts = urlsplit(base)
    active = {}
    def request():
        connection = http.client.HTTPConnection(parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80), timeout=45)
        connection.sock = service_socket(parts.hostname, connection.port)
        if parts.scheme == 'https':
            connection.sock = ssl.create_default_context().wrap_socket(connection.sock, server_hostname=parts.hostname)
        connection.sock.settimeout(45)
        active['connection'] = connection
        try:
            payload = bytes(binary) if binary is not None else json.dumps(body).encode() if body is not None else None
            connection.request(method, parts.path.rstrip('/') + path, body=payload,
                headers={'Authorization':'Bearer ' + token,
                         'Content-Type':'application/octet-stream' if binary is not None else 'application/json'})
            response = connection.getresponse()
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError('Réponse trop volumineuse.')
            value = json.loads(raw)
            if response.status >= 300:
                detail = value.get('detail')
                raise HTTPException(response.status if response.status in (409,410,413,422) else 503,
                                    detail[:300] if isinstance(detail,str) else 'Opération refusée par Chromium.')
            return value
        finally:
            connection.close()
    try:
        return await asyncio.wait_for(asyncio.to_thread(request), 50)
    except (OSError, ValueError, http.client.HTTPException, TimeoutError):
        raise HTTPException(503, 'Connexion au service Chromium interrompue ou réponse invalide.')
    finally:
        connection = active.get('connection')
        if connection and connection.sock:
            with contextlib.suppress(OSError):
                connection.sock.shutdown(socket.SHUT_RDWR)
            connection.close()


class Create(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str = Field(max_length=2000)
    source: str = Field(default='', max_length=150)


@router.get('')
def listing():
    with connect() as db:
        rows = db.execute('SELECT * FROM browser_sessions WHERE owner=? ORDER BY created DESC', (owner(),)).fetchall()
    return {'items': [browser_state.metadata(dict(row)) for row in rows],
            'available': bool(os.environ.get('ANYTUBE_INTERACTIVE_URL'))}


@router.post('')
def create(body: Create):
    endpoint()
    return browser_state.create(body.url, body.source)


@router.get('/{identifier}')
def get(identifier: str):
    return browser_state.metadata(browser_state.get(identifier))


@router.post('/{identifier}/open')
async def open_session(identifier: str):
    from app.network_settings import settings
    row = browser_state.get(identifier)
    state = browser_state.read(identifier, revision=row['revision'])
    await call('/interactive/' + identifier, 'POST', {'owner': owner(), 'url': row['site'], 'state': state,
                                                    'revision': settings()['revision']})
    return {'active': True, **browser_state.metadata(row)}


@router.post('/{identifier}/validate')
async def validate(identifier: str):
    browser_state.get(identifier)
    value = await call('/interactive/' + identifier + '/state')
    from app.network_settings import settings
    revision = settings()['revision']
    if value.get('revision') != revision:
        raise HTTPException(409, 'Le trajet réseau a changé. Rouvrez la session avant de la valider.')
    result = browser_state.save(identifier, value['state'], explicitly_validated=True, revision=revision)
    await call('/interactive/' + identifier, 'DELETE')
    return result


@router.post('/{identifier}/close')
async def close(identifier: str):
    browser_state.get(identifier)
    try:
        value = await call('/interactive/' + identifier + '/state')
        browser_state.save(identifier, value['state'])
    finally:
        await call('/interactive/' + identifier, 'DELETE')
    return {'closed': True}


@router.delete('/{identifier}')
async def delete(identifier: str):
    browser_state.get(identifier)
    # Delete persistent state even when the remote service is temporarily unavailable.
    browser_state.delete(identifier)
    with contextlib.suppress(HTTPException):
        await call('/interactive/' + identifier, 'DELETE')
    return {'deleted': True}


@router.post('/{identifier}/file')
async def upload(identifier: str, request: Request):
    from app.interactive_browser import file_type
    browser_state.get(identifier)
    data = bytearray()
    try:
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 20 * 1024 * 1024:
                raise HTTPException(413, 'Fichier limité à 20 Mo.')
        file_type(data)
        return await call('/interactive/' + identifier + '/file', 'POST', binary=data)
    finally:
        data[:] = b'\x00' * len(data)
        data.clear()


def service_socket(host, port):
    """Authenticated internal CONNECT, without granting the app arbitrary LAN egress."""
    proxy = os.environ.get('ANYTUBE_SERVICE_PROXY')
    if not proxy:
        return socket.create_connection((host, port), timeout=15)
    parts = urlsplit(proxy)
    connection = socket.create_connection((parts.hostname, parts.port), timeout=15)
    try:
        target = f'[{host}]:{port}' if ':' in host else f'{host}:{port}'
        token = os.environ['ANYTUBE_SERVICE_TOKEN']
        connection.sendall(f'CONNECT {target} HTTP/1.1\r\nHost: {target}\r\nProxy-Authorization: Bearer {token}\r\n\r\n'.encode())
        header = bytearray()
        while not header.endswith(b'\r\n\r\n') and len(header) <= 16384:
            chunk = connection.recv(1)
            if not chunk:
                raise OSError('Internal proxy closed')
            header.extend(chunk)
        if header.split(b'\r\n', 1)[0] != b'HTTP/1.1 200 Connection established':
            raise OSError('Internal proxy refused')
        return connection
    except Exception:
        connection.close()
        raise


@router.websocket('/{identifier}/screen')
async def screen(identifier: str, ws: WebSocket):
    from app.accounts import authenticate
    from websockets.asyncio.client import connect as websocket_connect
    user = authenticate(ws)
    canonical = os.environ.get('ANYTUBE_PUBLIC_URL', '').rstrip('/')
    origin = ws.headers.get('origin', '')
    expected = canonical or ('https' if ws.url.scheme == 'wss' else 'http') + '://' + ws.url.netloc
    if not user or origin != expected:
        await ws.close(code=1008)
        return
    context = current_user.set(user['id'])
    try:
        browser_state.get(identifier)
        base, token = endpoint()
        parts = urlsplit(base)
        sock = await asyncio.to_thread(service_socket, parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80))
        url = ('wss' if parts.scheme == 'https' else 'ws') + base[base.index('://'):] + '/interactive/' + identifier + '/screen'
        async with websocket_connect(url, sock=sock, proxy=None, additional_headers={'Authorization': 'Bearer ' + token},
                                     max_size=2 * 1024 * 1024, open_timeout=20) as upstream:
            await ws.accept()

            async def inbound():
                while True:
                    value = await ws.receive_text()
                    if len(value) > 16384:
                        raise ValueError('Commande trop longue')
                    await upstream.send(value)

            async def outbound():
                async for value in upstream:
                    await ws.send_text(value)

            async def still_authorized():
                # A logout, disabled account, deletion or expiry revokes an open
                # bridge too, without waiting for a new WebSocket handshake.
                while True:
                    await asyncio.sleep(2)
                    fresh = authenticate(ws)
                    row = browser_state.get(identifier)
                    import time
                    if not fresh or fresh['id'] != user['id'] or row['expires'] <= time.time():
                        return

            tasks = [asyncio.create_task(inbound()), asyncio.create_task(outbound()),
                     asyncio.create_task(still_authorized())]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except (HTTPException, WebSocketDisconnect, OSError, ValueError):
        with contextlib.suppress(Exception):
            await ws.close(code=1011)
    finally:
        with contextlib.suppress(Exception):
            await ws.close()
        current_user.reset(context)
