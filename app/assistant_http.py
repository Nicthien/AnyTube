"""Bounded HTTP subprocess protocol. Public discovery cannot access private DNS."""
import json
import base64
import os
import sys
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Redirection du service configuré refusée.')


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
    headers = {'User-Agent': 'AnyTube-Source-Assistant/1', **payload.get('headers', {})}
    if payload.get('trusted') and os.environ.get('ANYTUBE_SERVICE_PROXY'):
        headers['Proxy-Authorization'] = 'Bearer ' + os.environ['ANYTUBE_SERVICE_TOKEN']
    if raw is not None:
        headers.setdefault('Content-Type', 'application/json')
    opener = build_opener(ProxyHandler({'http': proxy, 'https': proxy} if proxy else {}), NoRedirect() if payload.get('trusted') else PublicRedirect())
    request = Request(payload['url'], data=raw, headers=headers, method=payload.get('method', 'GET'))
    with opener.open(request, timeout=max(1,min(float(payload.get('timeout',15)),120))) as response:
        data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('Réponse supérieure à 2 Mo.')
        return {'url': response.url, 'text': data.decode('utf-8', errors='replace'),
                'headers':{k:v for k,v in response.headers.items() if k.lower() in ('access-control-allow-origin','access-control-allow-methods','access-control-allow-headers','access-control-expose-headers','vary')},
                **({'base64':base64.b64encode(data).decode()} if payload.get('binary') else {}),
                'content_type': response.headers.get('Content-Type', '')}


if __name__ == '__main__':
    try:
        print(json.dumps(fetch(json.load(sys.stdin))))
    except HTTPError as exc:
        print(json.dumps({'error': 'http', 'status': exc.code}))
    except Exception:
        print(json.dumps({'error': 'network'}))
