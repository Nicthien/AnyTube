"""Administrator-selected outgoing route; Direct remains the migration default."""
import asyncio
import ipaddress
import json
import os
import secrets
import time
import uuid
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.accounts import require_admin
from app.store import connect, current_user, owner

router = APIRouter()


class NetworkSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['direct', 'proxy', 'vpn'] = 'direct'
    proxy_url: str = Field(default='', max_length=2000)
    tls_name: str = Field(default='', max_length=253)
    username: str = Field(default='', max_length=500, exclude=True)
    password: str = Field(default='', max_length=4000, exclude=True)
    clear_credentials: bool = Field(default=False, exclude=True)
    vpn_protocol: Literal['wireguard', 'openvpn'] = 'wireguard'

    @model_validator(mode='after')
    def valid(self):
        if self.mode != 'direct':
            p = urlsplit(self.proxy_url)
            if p.scheme not in ('http', 'https') or p.username or p.password or p.path not in ('', '/') or p.query or p.fragment:
                raise ValueError('Adresse de proxy HTTP(S), sans identifiants dans l’URL, requise.')
            try:
                ipaddress.ip_address(p.hostname)
                if p.port is not None and not 1 <= p.port <= 65535:
                    raise ValueError()
            except ValueError:
                raise ValueError('Utilisez l’adresse IP du proxy pour éviter une résolution DNS hors du trajet choisi.')
        if any(c in self.username + self.password + self.tls_name for c in '\r\n\x00') or ':' in self.username:
            raise ValueError('Identifiants de proxy invalides.')
        return self


def settings():
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key='outgoing-network'").fetchone()
    return json.loads(row[0]) if row else {**NetworkSettings().model_dump(), 'revision': 'direct'}


def credentials(value=None):
    from app.vault import encrypt, reveal
    token = current_user.set('__network_services__')
    try:
        if value is not None:
            with connect() as db:
                db.execute('INSERT OR REPLACE INTO credentials VALUES (?,?,?,?,?,?,?,?)',
                    (owner(), 'outgoing-proxy', 'Outgoing proxy', 'api_key', encrypt('outgoing-proxy', value), uuid.uuid4().hex, time.time(), 1))
            return value
        try:
            return reveal('outgoing-proxy')
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            return {}
    finally:
        current_user.reset(token)


@router.get('/api/network/settings')
def get_settings():
    require_admin()
    return {**settings(), 'has_credentials': bool(credentials())}


@router.put('/api/network/settings')
async def put_settings(body: NetworkSettings):
    require_admin()
    if body.mode != 'direct' and not os.environ.get('ANYTUBE_ROUTE_CONTROL'):
        raise HTTPException(503, 'Le superviseur réseau Docker est requis pour ce mode.')
    if body.clear_credentials:
        credentials({})
    elif body.username or body.password:
        credentials({'username': body.username, 'password': body.password})
    value = {**body.model_dump(), 'revision': uuid.uuid4().hex}
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES ('outgoing-network',?)", (json.dumps(value),))
    from app.playback import sessions
    sessions.clear()
    from app.main import home_cache
    home_cache.clear()
    from app.browser_sessions import call
    try:
        await call('/interactive', 'DELETE')
    except HTTPException:
        pass  # Gateways invalidate the old route independently; state stays stale.
    return get_settings()


@router.get('/_internal/network')
def control(request: Request):
    token = os.environ.get('ANYTUBE_SERVICE_TOKEN', '')
    if not token or request.client.host not in ('127.0.0.1', '::1') or not secrets.compare_digest(
            request.headers.get('authorization', ''), 'Bearer ' + token):
        raise HTTPException(403, 'Accès refusé.')
    value = settings()
    from app.source_assistant import settings as assistant_settings
    configured = assistant_settings()
    hosts = [urlsplit(service.url).hostname for service in (configured.search, configured.ai, configured.browser) if service.url]
    if os.environ.get('ANYTUBE_INTERACTIVE_URL'):
        hosts.append(urlsplit(os.environ['ANYTUBE_INTERACTIVE_URL']).hostname)
    def internal(host):
        try:
            return not ipaddress.ip_address(host).is_global
        except ValueError:
            return '.' not in host or host.endswith('.local')
    return {**value, **(credentials() if value['mode'] != 'direct' else {}), 'internal_hosts': [h for h in hosts if h and internal(h)]}


@router.post('/api/network/test')
async def test_network():
    require_admin()
    from app.source_assistant import http
    started = time.monotonic()
    try:
        response = await http('https://1.1.1.1/cdn-cgi/trace', timeout=30)
        ip = next((line[3:] for line in response['text'].splitlines() if line.startswith('ip=')), '')
        ipaddress.ip_address(ip)
        return {'ok': True, 'mode': settings()['mode'], 'public_ip': ip, 'duration': round(time.monotonic()-started, 3),
                'message': 'Trajet testé. Ce test seul ne certifie pas l’absence de fuite sur tous les flux.'}
    except Exception:
        return {'ok': False, 'mode': settings()['mode'], 'duration': round(time.monotonic()-started, 3),
                'message': 'Trajet indisponible. Aucun basculement automatique vers Direct.'}
