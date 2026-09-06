"""Bounded fetch protocol used only inside the isolated worker."""
import base64
import os
import re
from urllib.request import Request, ProxyHandler, build_opener
from app.connectors import public_url, PublicRedirect
from app.vault import scoped_headers
from app.failures import SourceFailure

MAX_CHUNK = 8 * 1024 * 1024


def media_mime(data, original):
    """Identify packed HLS audio even when the upstream sends octet-stream."""
    if original.split(';')[0].lower() != 'application/octet-stream':
        return original
    offset = 0
    if data.startswith(b'ID3') and len(data) >= 10:
        offset = 10 + sum((value & 127) << shift for value, shift in zip(data[6:10], (21, 14, 7, 0)))
    if len(data) >= offset + 2 and data[offset] == 255 and data[offset+1] & 246 == 240:
        return 'audio/aac'
    if len(data) > 376 and data[0] == data[188] == data[376] == 71:
        return 'video/mp2t'
    return original


def fetch(payload):
    url = public_url(payload['url'])
    credential = payload.get('_credential')
    headers = {k: v for k, v in (payload.get('headers') or {}).items()
               if k.lower() in ('user-agent', 'referer', 'origin', 'accept') and isinstance(v, str)
               and '\r' not in v and '\n' not in v}
    headers.update(scoped_headers(credential, url))
    headers['Accept-Encoding'] = 'identity'
    byte_range = payload.get('range')
    if byte_range:
        match = re.fullmatch(r'bytes=(\d{1,16})-(\d{0,16})', byte_range)
        if not match:
            raise ValueError('Plage média invalide.')
        start = int(match[1])
        end = min(int(match[2]) if match[2] else start+MAX_CHUNK-1, start+MAX_CHUNK-1)
        if end < start:
            raise ValueError('Plage média invalide.')
        headers['Range'] = f'bytes={start}-{end}'
    proxy = os.environ.get('ANYTUBE_PROXY')
    opener = build_opener(ProxyHandler({'http': proxy, 'https': proxy} if proxy else {}), PublicRedirect(credential))
    with opener.open(
            Request(url, headers=headers, method='HEAD' if payload.get('head') else 'GET'), timeout=15) as response:
        data = b'' if payload.get('head') else response.read(MAX_CHUNK+1)
        if len(data) > MAX_CHUNK:
            raise SourceFailure('unavailable_format')
        result_headers = {name: response.headers[name] for name in ('Content-Type', 'Content-Range', 'Accept-Ranges', 'Content-Length') if name in response.headers}
        sample = data
        if payload.get('head') and result_headers.get('Content-Type', '').split(';')[0].lower() == 'application/octet-stream':
            # Opaque relay URLs have no extension. Shaka uses HEAD to choose its
            # transmuxer, so preserve content identity without exposing upstream URLs.
            with opener.open(Request(url, headers={**headers, 'Range': 'bytes=0-1023'}), timeout=15) as probe:
                sample = probe.read(1024)
        result_headers['Content-Type'] = media_mime(sample, result_headers.get('Content-Type', 'application/octet-stream'))
        return {'data': base64.b64encode(data).decode(), 'status': response.status, 'url': response.url,
                'headers': result_headers}
