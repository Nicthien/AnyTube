"""Private expiring media sessions. Only resources discovered by the server are fetchable."""
import asyncio
import base64
import hashlib
import re
import secrets
import time
from urllib.parse import urljoin, urlsplit, quote
from xml.etree import ElementTree as ET
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from app.connectors import public_url
from app.discovery import SourceURL, select_source
from app.store import owner, saved_sources
from app.verification import revision

router = APIRouter()
sessions = {}
TTL = 30 * 60
MAX_AGE = 6 * 3600
MAX_RESOURCES = 20000
DASH_VAR = re.compile(r'\$(RepresentationID|Number|Bandwidth|Time)(?:%0\d{1,2}d)?\$')


def prune():
    for identifier, session in list(sessions.items()):
        if session['expires'] < time.time() or session['created'] + MAX_AGE < time.time():
            sessions.pop(identifier, None)


def session_for(identifier):
    prune()
    session = sessions.get(identifier)
    if not session or session['owner'] != owner():
        raise HTTPException(404, 'Session de lecture absente ou expirée.')
    source = next((s for s in saved_sources() if s['id'] == session['source_id'] and s['enabled']), None)
    if not source or revision(source['connector']) != session['revision']:
        sessions.pop(identifier, None)
        raise HTTPException(410, 'La source ou ses accès ont changé. Rouvrez le média.')
    session['expires'] = min(time.time()+TTL, session['created']+MAX_AGE)
    return session


def register(session, url, *, headers=None):
    variables = list(DASH_VAR.finditer(url))
    if '$' in urlsplit(url).netloc:
        raise ValueError('Domaine média variable interdit.')
    sample = DASH_VAR.sub('1', url)
    if '$' in sample or '{$' in url:
        raise ValueError('Variable de manifeste non prise en charge.')
    public_url(sample)
    if len(url) > 12000:
        raise ValueError('URL média trop longue.')
    identifier = hashlib.sha256((url + str(headers or {})).encode()).hexdigest()[:32]
    if identifier not in session['resources']:
        if len(session['resources']) >= MAX_RESOURCES:
            raise ValueError('Limite de ressources atteinte. Rouvrez le direct.')
        session['resources'][identifier] = {'url': url, 'headers': headers or {},
                                          'variables': [(v[0], v[1]) for v in variables]}
    suffix = '/'.join(v[0] for v in variables) if variables else 'file'
    return f'/api/playback/{session["id"]}/resource/{identifier}/{suffix}'


def resource_url(session, resource, suffix):
    variables = resource['variables']
    if not variables:
        if suffix != 'file':
            raise HTTPException(404, 'Ressource introuvable.')
        return resource['url']
    values = suffix.split('/')
    if len(values) != len(variables):
        raise HTTPException(400, 'Paramètres média invalides.')
    target = resource['url']
    replacements = {}
    for (token, name), value in zip(variables, values):
        if name == 'RepresentationID':
            if value not in session.get('representations', set()) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', value):
                raise HTTPException(400, 'Piste inconnue.')
        elif not re.fullmatch(r'\d{1,20}', value):
            raise HTTPException(400, 'Index de segment invalide.')
        if token in replacements and replacements[token] != value:
            raise HTTPException(400, 'Index incohérent.')
        replacements[token] = value
    for token, value in replacements.items():
        target = target.replace(token, value)
    return public_url(target)


def rewrite_hls(session, data, base, headers):
    text = data.decode('utf-8-sig')
    if not text.startswith('#EXTM3U') or len(data) > 2*1024*1024:
        raise ValueError('Manifeste HLS invalide.')
    if '#EXT-X-DEFINE' in text or 'SAMPLE-AES' in text or 'KEYFORMAT="com.' in text:
        raise ValueError('Ce manifeste chiffré ou à variables n’est pas pris en charge.')
    lines = []
    for line in text.splitlines():
        if line.startswith('#'):
            line = re.sub(r'URI="([^"]+)"', lambda match: 'URI="' + register(session, urljoin(base, match[1]), headers=headers) + '"', line)
            # External steering and interstitial assets must never escape the relay.
            if line.startswith(('#EXT-X-CONTENT-STEERING', '#EXT-X-DATERANGE')):
                continue
        elif line.strip():
            line = register(session, urljoin(base, line.strip()), headers=headers)
        lines.append(line)
    return ('\n'.join(lines) + '\n').encode()


def rewrite_dash(session, data, base, headers):
    text = data.decode('utf-8-sig')
    if len(data) > 2*1024*1024 or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('Manifeste DASH invalide.')
    root = ET.fromstring(text)
    local = lambda tag: tag.rsplit('}', 1)[-1]
    if local(root.tag) != 'MPD':
        raise ValueError('Manifeste DASH requis.')
    representations = {e.attrib['id'] for e in root.iter() if local(e.tag) == 'Representation' and 'id' in e.attrib}
    session.setdefault('representations', set()).update(representations)
    if any(local(e.tag) == 'ContentProtection' for e in root.iter()):
        raise ValueError('Le manifeste annonce une protection de contenu.')

    def walk(element, inherited):
        bases = [child for child in element if local(child.tag) == 'BaseURL']
        resolved = urljoin(inherited, bases[0].text.strip()) if bases and bases[0].text else inherited
        for child in bases:
            element.remove(child)
        for key in list(element.attrib):
            if local(key) in ('href', 'actuate'):
                raise ValueError('Références DASH externes non prises en charge.')
            if local(key) in ('media', 'initialization', 'sourceURL', 'index'):
                element.attrib[key] = register(session, urljoin(resolved, element.attrib[key]), headers=headers)
        for child in list(element):
            if local(child.tag) in ('UTCTiming', 'Location', 'PatchLocation', 'ContentSteering'):
                element.remove(child)
            else:
                walk(child, resolved)
        # SegmentBase and single-file representations require their inherited file URL.
        if local(element.tag) == 'Representation' and resolved != base:
            child = ET.SubElement(element, '{urn:mpeg:dash:schema:mpd:2011}BaseURL')
            child.text = register(session, resolved, headers=headers)
    walk(root, base)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


@router.post('/api/playback', status_code=201)
async def create(body: SourceURL):
    from app.main import run_worker, searches
    source, extractor_key = select_source(body.url, body.source_id)
    prune()
    if sum(s['owner'] == owner() for s in sessions.values()) >= 3 or len(sessions) >= 30:
        raise HTTPException(429, 'Fermez une autre lecture avant d’en ouvrir une nouvelle.')
    try:
        async with searches:
            result = await run_worker({'mode': 'resolve', 'url': body.url, 'connector': source['connector'], 'extractor_key': extractor_key})
        identifier = secrets.token_hex(24)
        session = {'id': identifier, 'owner': owner(), 'source_id': source['id'], 'revision': revision(source['connector']),
                   'connector': source['connector'], 'created': time.time(), 'expires': time.time()+TTL,
                   'resources': {}, 'representations': set(), 'lock': asyncio.Semaphore(3)}
        choices, seen = [], set()
        for item in reversed(result['formats']):
            protocol = item.get('protocol') or ''
            adaptive = 'm3u8' in protocol or 'dash' in protocol
            if 'dash' in protocol and not item.get('manifest_url') and not urlsplit(item['url']).path.endswith('.mpd'):
                continue
            target = (item.get('manifest_url') or item['url']) if adaptive else item['url']
            if target in seen:
                continue
            if not adaptive and item.get('acodec') == 'none':
                continue
            if not adaptive and protocol not in ('http', 'https'):
                continue
            mime = 'application/dash+xml' if 'dash' in protocol else 'application/x-mpegURL' if adaptive else 'audio/mp4' if item.get('vcodec') == 'none' else 'video/mp4'
            if not adaptive and item.get('ext') in ('webm', 'mp3', 'ogg', 'opus'):
                mime = {'mp3': 'audio/mpeg', 'ogg': 'audio/ogg', 'opus': 'audio/ogg', 'webm': 'audio/webm' if item.get('vcodec') == 'none' else 'video/webm'}[item['ext']]
            uri = register(session, target, headers=item.get('http_headers') or result.get('http_headers'))
            choices.append({'url': uri, 'mime': mime, 'adaptive': adaptive,
                            'label': 'Qualité automatique' if adaptive else f'{item.get("height") or "Audio"}' + ('p' if item.get('height') else ''),
                            'height': item.get('height'), 'language': item.get('language'), 'audio_only':item.get('vcodec') == 'none'})
            seen.add(target)
        if not choices:
            raise HTTPException(400, 'Aucun flux directement lisible. Essayez la préparation locale.')
        choices.sort(key=lambda c:(c['audio_only'], not c['adaptive'], -(c['height'] or 0)))
        subtitles = [{'language': language, 'url': register(session, item['url']), 'ext': item['ext']}
                     for language, entries in result['subtitles'].items() for item in entries if item['ext'] == 'vtt']
        sessions[identifier] = session
        return {'id': identifier, 'video': result['video'], 'source_id': source['id'], 'is_live': result['is_live'],
                'choices': choices, 'subtitles': subtitles, 'expires_in': TTL}
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except ValueError:
        raise HTTPException(400, 'Le manifeste contient une ressource incompatible ou interdite.')


@router.delete('/api/playback/{identifier}')
def close(identifier: str):
    session_for(identifier)
    sessions.pop(identifier, None)
    return {'ok': True}


@router.api_route('/api/playback/{identifier}/resource/{resource_id}/{suffix:path}', methods=['GET', 'HEAD'])
async def resource(identifier: str, resource_id: str, suffix: str, request: Request):
    from app.main import run_worker
    session = session_for(identifier)
    item = session['resources'].get(resource_id)
    if not item:
        raise HTTPException(404, 'Ressource inconnue.')
    try:
        target = resource_url(session, item, suffix)
        async with session['lock']:
            result = await run_worker({'mode': 'fetch', 'url': target, 'connector': session['connector'],
                                       'headers': item['headers'], 'range': request.headers.get('range'), 'head': request.method == 'HEAD'}, timeout=25)
        session_for(identifier)  # A credential can be revoked while the worker is running.
        data = base64.b64decode(result['data'])
        mime = result['headers'].get('Content-Type', 'application/octet-stream').split(';')[0].lower()
        manifest = False
        if request.method != 'HEAD':
            if data.lstrip(b'\xef\xbb\xbf').startswith(b'#EXTM3U'):
                data = rewrite_hls(session, data, result['url'], item['headers'])
                mime, manifest = 'application/vnd.apple.mpegurl', True
            elif mime in ('application/dash+xml', 'application/xml', 'text/xml') or data.lstrip().startswith((b'<?xml', b'<MPD')):
                data = rewrite_dash(session, data, result['url'], item['headers'])
                mime, manifest = 'application/dash+xml', True
        if mime in ('text/html', 'application/javascript', 'image/svg+xml'):
            raise ValueError('Type de ressource interdit.')
        headers = {k: v for k, v in result['headers'].items() if k in ('Content-Range', 'Accept-Ranges') and not manifest}
        headers['Cache-Control'] = 'no-store'
        if request.method == 'HEAD' and 'Content-Length' in result['headers']:
            headers['Content-Length'] = result['headers']['Content-Length']
        return Response(data, status_code=200 if manifest else result['status'], media_type=mime, headers=headers)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    except (ValueError, ET.ParseError):
        raise HTTPException(400, 'Ressource média incompatible ou interdite.')
