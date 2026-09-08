"""Owner-bound encrypted browser state; no live browser or document persistence."""
import base64
import json
import time
import uuid
from contextvars import ContextVar
from urllib.parse import urlsplit

from Cryptodome.Cipher import AES
from fastapi import HTTPException

from app.store import connect, owner
from app.vault import encrypt, key

RETENTION = 30 * 86400
STATE_LIMIT = 1024 * 1024
active_session = ContextVar('browser_session', default='')


def initialize():
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS browser_sessions(
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, site TEXT NOT NULL,
            source TEXT NOT NULL, created REAL NOT NULL, validated REAL NOT NULL,
            expires REAL NOT NULL, revision TEXT NOT NULL, encrypted TEXT NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS browser_session_owner ON browser_sessions(owner,site)')
    prune()


def prune():
    with connect() as db:
        now = time.time()
        # Retain a source's expiry marker, never its expired authentication state.
        db.execute("UPDATE browser_sessions SET encrypted='' WHERE expires<=?", (now,))
        db.execute('''DELETE FROM browser_sessions WHERE expires<=? AND (source='' OR EXISTS(
            SELECT 1 FROM browser_sessions newer WHERE newer.owner=browser_sessions.owner
            AND newer.source=browser_sessions.source AND newer.validated>browser_sessions.validated))''', (now,))


def site_origin(url):
    from app.connectors import public_url
    public_url(url)
    parts = urlsplit(url)
    return f'{parts.scheme}://{parts.netloc.lower()}'


def get(identifier):
    with connect() as db:
        row = db.execute('SELECT * FROM browser_sessions WHERE id=? AND owner=?', (identifier, owner())).fetchone()
    if not row:
        raise HTTPException(404, 'Session introuvable.')
    return dict(row)


def metadata(row):
    return {**{k: row[k] for k in ('id', 'site', 'source', 'created', 'validated', 'expires', 'revision')},
            'state': 'expired' if row['expires'] <= time.time() else 'saved' if row['validated'] else 'unvalidated'}


def create(url, source='', revision=None):
    if revision is None:
        from app.network_settings import settings
        revision = settings()['revision']
    identifier = uuid.uuid4().hex
    site = site_origin(url)
    if source:
        with connect() as db:
            if not db.execute('SELECT 1 FROM sources WHERE id=? AND owner=?', (source, owner())).fetchone():
                raise HTTPException(404, 'Source introuvable.')
    now = time.time()
    prune()
    with connect() as db:
        if db.execute('SELECT count(*) FROM browser_sessions WHERE owner=? AND expires>?', (owner(), now)).fetchone()[0] >= 100:
            raise HTTPException(409, 'Supprimez une session avant d’en créer une autre.')
        db.execute('INSERT INTO browser_sessions VALUES (?,?,?,?,?,?,?,?,?)',
                   (identifier, owner(), site, source, now, 0, now + RETENTION, revision,
                    encrypt('browser-' + identifier, {'cookies': [], 'origins': []})))
    return metadata(get(identifier))


def read(identifier, revision=None):
    row = get(identifier)
    if row['expires'] <= time.time():
        prune()
        raise HTTPException(409, 'Session expirée. Ouvrez une nouvelle session.')
    if revision is None:
        from app.network_settings import settings
        revision = settings()['revision']
    if row['revision'] != revision:
        raise HTTPException(409, 'Le trajet réseau a changé. Recontrôlez cette session.')
    try:
        raw = base64.b64decode(row['encrypted'], validate=True)
        cipher = AES.new(key(), AES.MODE_GCM, nonce=raw[:12])
        cipher.update(f'anytube:1:{owner()}:browser-{identifier}'.encode())
        return json.loads(cipher.decrypt_and_verify(raw[28:], raw[12:28]))
    except (ValueError, KeyError):
        raise HTTPException(503, 'État de session illisible. Vérifiez la clé du coffre.')


def sanitize_state(state, site):
    """Keep only supported state belonging to the exact site, never arbitrary fields.

    Cross-site identity-provider state deliberately remains ephemeral. Cookie domains
    may cover subdomains only when Chromium actually scoped them to this site's host.
    """
    if not isinstance(state, dict) or len(json.dumps(state).encode()) > STATE_LIMIT:
        raise HTTPException(422, 'État de session trop volumineux ou invalide.')
    host = urlsplit(site).hostname
    result = {'cookies': [], 'origins': []}
    for cookie in state.get('cookies', [])[:1000]:
        if not isinstance(cookie, dict):
            continue
        domain = cookie.get('domain', '')
        base_domain = domain.lstrip('.').lower()
        if not (base_domain == host or (domain.startswith('.') and '.' in base_domain and host.endswith('.' + base_domain))):
            continue
        if not isinstance(cookie.get('name'), str) or not isinstance(cookie.get('value'), str):
            continue
        if not str(cookie.get('path', '')).startswith('/'):
            continue
        expiry = cookie.get('expires', -1)
        if not isinstance(expiry, (int, float)) or (expiry != -1 and expiry <= time.time()):
            continue
        saved = {k: cookie[k] for k in
            ('name', 'value', 'domain', 'path', 'expires', 'httpOnly', 'secure', 'sameSite', 'partitionKey') if k in cookie}
        # Narrow parent-domain cookies to the explicitly selected site. This
        # preserves its login without sharing state with sibling sites.
        if base_domain != host:
            saved['domain'] = host
        result['cookies'].append(saved)
    for origin in state.get('origins', [])[:100]:
        if isinstance(origin, dict) and origin.get('origin') in (site, site.replace('http://', 'https://', 1)):
            result['origins'].append({k: origin[k] for k in ('origin', 'localStorage', 'indexedDB') if k in origin})
    return result


def save(identifier, state, *, explicitly_validated=False, revision=None):
    row = get(identifier)
    if row['expires'] <= time.time():
        raise HTTPException(409, 'Session expirée. Renouvelez-la explicitement.')
    state = sanitize_state(state, row['site'])
    now = time.time()
    with connect() as db:
        db.execute('UPDATE browser_sessions SET encrypted=?,validated=?,expires=?,revision=? WHERE id=? AND owner=?',
                   (encrypt('browser-' + identifier, state), now if explicitly_validated else row['validated'],
                    now + RETENTION if explicitly_validated else row['expires'],
                    revision if revision is not None else row['revision'], identifier, owner()))
    return metadata(get(identifier))


def delete(identifier):
    get(identifier)
    with connect() as db:
        db.execute('DELETE FROM browser_sessions WHERE id=? AND owner=?', (identifier, owner()))


def cookie_header(state, url):
    """A request-local cookie header, never reusable across redirects."""
    parts = urlsplit(url)
    host, path = (parts.hostname or '').lower(), parts.path or '/'
    selected = []
    for cookie in state.get('cookies', []):
        domain = cookie.get('domain', '').lower()
        if not (host == domain.lstrip('.') or (domain.startswith('.') and host.endswith(domain))):
            continue
        prefix = cookie.get('path', '/')
        if not (path == prefix or (path.startswith(prefix) and (prefix.endswith('/') or path[len(prefix):].startswith('/')))):
            continue
        if cookie.get('secure') and parts.scheme != 'https':
            continue
        if cookie.get('expires', -1) != -1 and cookie['expires'] <= time.time():
            continue
        name, value = cookie.get('name', ''), cookie.get('value', '')
        if any(c in name + value for c in '\r\n\x00;'):
            continue
        selected.append((len(prefix), name + '=' + value))
    return '; '.join(value for _, value in sorted(selected, reverse=True))


def cookie_jar(state):
    from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy
    jar = CookieJar(policy=DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain))
    for cookie in state.get('cookies', []):
        domain = cookie['domain']
        expiry = cookie.get('expires', -1)
        jar.set_cookie(Cookie(0, cookie['name'], cookie['value'], None, False, domain,
                            domain.startswith('.'), domain.startswith('.'), cookie.get('path', '/'), True,
                            cookie.get('secure', False), None if expiry == -1 else int(expiry), expiry == -1,
                            None, None, {'HttpOnly': None} if cookie.get('httpOnly') else {}, False))
    return jar


def for_connector(config):
    if active_session.get():
        return active_session.get()
    if not owner():
        return ''
    from app.pagination import signature
    with connect() as db:
        rows = db.execute('''SELECT b.id,s.connector FROM browser_sessions b JOIN sources s
                            ON b.owner=s.owner AND b.source=s.id
                            WHERE b.owner=? AND b.validated>0 ORDER BY b.validated DESC''', (owner(),)).fetchall()
    return next((row['id'] for row in rows if row['connector'] and signature(json.loads(row['connector'])) == signature(config)), '')


def bind(identifier, source):
    row = get(identifier)
    if not row['validated'] or row['expires'] <= time.time():
        raise HTTPException(409, 'Validez d’abord la session.')
    with connect() as db:
        if not db.execute('SELECT 1 FROM sources WHERE owner=? AND id=?', (owner(), source)).fetchone():
            raise HTTPException(404, 'Source introuvable.')
        db.execute('UPDATE browser_sessions SET source=? WHERE owner=? AND id=?', (source, owner(), identifier))
