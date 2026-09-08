"""Bounded HTTP subprocess protocol. Public discovery cannot access private DNS."""
import json
import base64
import os
import sys
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.request import HTTPCookieProcessor
from urllib.error import HTTPError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirection du service configuré refusée.')


class SingleHop(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch(payload):
    from app.connectors import public_url, PublicRedirect
    proxy = os.environ.get('ANYTUBE_PROXY', '')
    if not payload.get('trusted'):
        from app.worker import protect_network
        protect_network()
        public_url(payload['url'])
    elif os.environ.get('ANYTUBE_SERVICE_PROXY'):
        proxy = os.environ['ANYTUBE_SERVICE_PROXY']
    body = payload.get('body')
    raw = body.encode() if isinstance(body, str) else json.dumps(body).encode() if body is not None else None
    if payload.get('body_base64') is not None:
        raw = base64.b64decode(payload['body_base64'], validate=True)
        if len(raw) > 21 * 1024 * 1024:
            raise ValueError('Corps de requête trop volumineux.')
    headers = {'User-Agent': 'AnyTube-Source-Assistant/1', **payload.get('headers', {})}
    if not payload.get('trusted') and os.environ.get('ANYTUBE_PUBLIC_PROXY_TOKEN'):
        headers['Proxy-Authorization'] = 'Bearer ' + os.environ['ANYTUBE_PUBLIC_PROXY_TOKEN']
    if payload.get('trusted') and os.environ.get('ANYTUBE_SERVICE_PROXY'):
        headers['Proxy-Authorization'] = 'Bearer ' + os.environ['ANYTUBE_SERVICE_TOKEN']
    if raw is not None:
        headers.setdefault('Content-Type', 'application/json')
    cookie_handlers = []
    jar = None
    if payload.get('browser_state') and not payload.get('trusted'):
        from app.browser_state import cookie_jar
        jar = cookie_jar(payload['browser_state'])
        cookie_handlers.append(HTTPCookieProcessor(jar))
    opener = build_opener(ProxyHandler({'http': proxy, 'https': proxy} if proxy else {}),
                          *cookie_handlers,
                          SingleHop() if payload.get('single_hop') else NoRedirect() if payload.get('trusted') else PublicRedirect())
    request = Request(payload['url'], data=raw, headers=headers, method=payload.get('method', 'GET'))
    try:
        response = opener.open(request, timeout=max(1,min(float(payload.get('timeout',15)),120)))
    except HTTPError as exc:
        if not payload.get('single_hop'):
            raise
        response = exc
    with response as response:
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('Réponse supérieure à 2 Mo.')
        from email.message import Message
        content = Message()
        content['content-type'] = response.headers.get('Content-Type','')
        return {'url': response.url, 'status':response.status, 'text': data.decode(content.get_content_charset() or 'utf-8', errors='replace'),
                **({'_session_cookies': [{'name': c.name, 'value': c.value, 'domain': c.domain,
                       'path': c.path, 'secure': c.secure, 'expires': c.expires if c.expires is not None else -1,
                       'httpOnly': c.has_nonstandard_attr('HttpOnly'), 'sameSite': 'Lax'} for c in jar]} if jar is not None else {}),
                **({'set_cookies': response.headers.get_all('Set-Cookie', []),
                    'location': response.headers.get('Location', '')} if payload.get('single_hop') else {}),
                'headers':{k:v for k,v in response.headers.items() if k.lower() in ('access-control-allow-origin','access-control-allow-methods','access-control-allow-headers','access-control-expose-headers','vary')},
                **({'base64':base64.b64encode(data).decode()} if payload.get('binary') else {}),
                'content_type': response.headers.get('Content-Type', '')}


if __name__ == '__main__':
    try:
        print(json.dumps(fetch(json.load(sys.stdin))))
    except HTTPError as exc:
        print(json.dumps({'error': 'http', 'status': exc.code}))
    except Exception as exc:
        print(json.dumps({'error': 'network', 'reason': type(exc).__name__}))
