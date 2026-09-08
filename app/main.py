import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import sys
import time
import uuid
from typing import Literal
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from yt_dlp.version import __version__
from app.catalog import catalog, SEARCH
from app.store import connect, data_dir, initialize, saved_sources, current_user, owner
from app.accounts import router as account_routes, authenticate, initialize_accounts
from app.library import router as library_routes, job_folder, job_file, media_root, persist, remove_record, restore_jobs, limits
from app.pagination import signature, encode as encode_cursor, decode as decode_cursor, capabilities, search_config, MAX_RESULTS
from app.connectors import Connector, PREFIXES, default_connector
from app.verification import evidence, record, revision, differences, engine_version
from app.vault import router as vault_routes, credential_revision
from app.failures import SourceFailure
from app.adapters import native_pagination
from app.discovery import router as discovery_routes, select_source
from app.playback import router as playback_routes
from app import source_assistant

logger = logging.getLogger('anytube')
workers = asyncio.Semaphore(4)
searches = asyncio.Semaphore(3)
jobs = {}
tasks = set()
media_tasks = {}
home_cache = {}
platform_locks = {}
platform_cooldowns = {}


@asynccontextmanager
async def lifespan(app):
    initialize()
    initialize_accounts(app)
    source_assistant.initialize()
    home_cache.clear()
    platform_locks.clear()
    platform_cooldowns.clear()
    from app.playback import sessions as playback_sessions
    playback_sessions.clear()
    jobs.clear()
    jobs.update(restore_jobs())
    media_tasks.clear()
    cleanup_cache()
    maintenance = asyncio.create_task(maintain_cache())
    yield
    await source_assistant.shutdown()
    maintenance.cancel()
    await asyncio.gather(maintenance, return_exceptions=True)
    for task in list(tasks):
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title='AnyTube', version='0.5.4-preview', docs_url=None, redoc_url=None, lifespan=lifespan)
app.include_router(account_routes)
app.include_router(library_routes)
app.include_router(vault_routes)
app.include_router(discovery_routes)
app.include_router(playback_routes)
app.include_router(source_assistant.router)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({'detail': ' ; '.join(error['msg'].removeprefix('Value error, ') for error in exc.errors())}, status_code=422)


@app.get('/api/connectors/options')
def connector_options():
    return {'prefixes': PREFIXES}


@app.get('/api/docs', include_in_schema=False)
def api_docs():
    return RedirectResponse('/openapi.json')


@app.middleware('http')
async def security(request: Request, call_next):
    from urllib.parse import urlsplit
    public_url = os.environ.get('ANYTUBE_PUBLIC_URL', '').rstrip('/')
    canonical = urlsplit(public_url)
    if canonical.scheme == 'https' and canonical.netloc and request.url.netloc.lower() != canonical.netloc.lower() and request.url.path != '/api/health':
        if request.method in ('GET', 'HEAD'):
            target = public_url + request.url.path
            if request.url.query:
                target += '?' + request.url.query
            return RedirectResponse(target, status_code=307)
        return JSONResponse({'detail': f'Ouvrez {public_url} pour vous connecter avec une session sécurisée.'}, status_code=400)
    if request.method in ('POST', 'PATCH', 'DELETE', 'PUT') and request.headers.get('x-anytube') != '1':
        return JSONResponse({'detail': 'Requête non autorisée.'}, status_code=403)
    from urllib.parse import urlsplit
    origin = request.headers.get('origin')
    allowed = {str(request.base_url).rstrip('/'), os.environ.get('ANYTUBE_PUBLIC_URL','').rstrip('/')}
    if request.method in ('POST','PUT','PATCH','DELETE') and origin and origin not in allowed:
        return JSONResponse({'detail':'Origine non autorisée.'},status_code=403)
    public = {'/api/health','/api/account/me','/api/account/setup','/api/account/login','/api/account/join'}
    user = authenticate(request) if request.url.path.startswith('/api/') or request.url.path == '/openapi.json' else None
    if (request.url.path.startswith('/api/') or request.url.path == '/openapi.json') and request.url.path not in public and not user:
        return JSONResponse({'detail':'Connectez-vous pour continuer.'},status_code=401)
    context = current_user.set(user['id'] if user else '')
    try:
        response = await call_next(request)
    finally:
        current_user.reset(context)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https: http:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


@app.get('/api/health')
def health():
    return {'status': 'ok', 'version': app.version, 'yt_dlp': __version__,
            'dependencies': {name: shutil.which(name) is not None for name in ('ffmpeg', 'ffprobe', 'node')}}


@app.get('/api/catalog')
def available(q: str = Query('', max_length=200), grouped: bool = False):
    from app.catalog import source_catalog
    items = [s for s in (source_catalog() if grouped else catalog())
             if q.casefold() in (s['name'] + ' ' + s.get('search_terms', '')).casefold()]
    return {'items': items, 'total': len(items)}


@app.get('/api/catalog/report')
def catalog_report():
    from app.inventory import report
    return JSONResponse(report(saved_sources()), headers={'Content-Disposition': 'attachment; filename="anytube-catalogue.json"'})


@app.get('/api/catalog/coverage')
def coverage():
    from app.inventory import platform_inventory
    from app.registry import totals
    return totals(platform_inventory())


@app.get('/api/sources/{source_id}/evidence')
def source_evidence(source_id: str):
    from app.verification import history
    source = next((s for s in saved_sources() if s['id'] == source_id), None)
    if not source:
        raise HTTPException(404, 'Source introuvable.')
    return {'items': history(source['connector'])}


@app.get('/api/sources')
def sources(q: str = Query('', max_length=200)):
    items = [{**s, 'enabled': bool(s['enabled']), 'search': s['connector']['kind'] != 'url', 'capabilities':capabilities(s['connector']), 'revision':signature(s['connector'])}
             for s in saved_sources() if q.casefold() in s['name'].casefold()]
    for item in items:
        item['verifications'] = evidence(item['connector'])
    return {'items': items, 'total': len(items)}


@app.get('/api/templates/{source_id}')
def source_template(source_id: str, instance: str = Query('', max_length=200)):
    from app.catalog import playback_supported
    from app.connectors import instance_host
    entry = next((s for s in catalog() if s['id'] == source_id), None)
    if not entry:
        raise HTTPException(404, 'Modèle introuvable.')
    if instance and not entry.get('instance_software'):
        raise HTTPException(400, 'Ce modèle ne se décline pas par instance.')
    try:
        config = default_connector(source_id, instance)
        host = instance_host(instance, entry.get('default_instance', ''))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    known = playback_supported(source_id, host)
    return {**entry, 'connector': config, 'revision': revision(config), 'instance': host,
            # A search that answers on an unknown instance still has no playback path.
            'playback_extractor': None if known is None else ('installed' if known else 'missing'),
            'connector_version': engine_version(), 'yt_dlp': __version__}


@app.get('/api/sources/{source_id}/template-diff')
def template_diff(source_id: str):
    source = next((s for s in saved_sources() if s['id'] == source_id), None)
    if not source:
        raise HTTPException(404, 'Source introuvable.')
    template_id = source_id if not source_id.startswith('custom-') else source['connector']['extractor']
    delivered = source_template(template_id, '')
    return {**delivered, 'differences': differences(source['connector'], delivered['connector'])}


class SourceCreate(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=150)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    instance: str | None = Field(default=None, max_length=200)
    connector: Connector | None = None


class SourceEdit(BaseModel):
    enabled: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    connector: Connector | None = None


def validate_connector(config):
    if config.extractor and config.extractor not in {s['id'] for s in catalog()}:
        raise HTTPException(400, 'Extracteur vidéo inconnu du catalogue yt-dlp.')
    if config.credential_id:
        from app.vault import row
        access = row(config.credential_id)
        if config.kind != 'json' and access['kind'] != 'cookies':
            raise HTTPException(400, 'Ce connecteur yt-dlp accepte les cookies importés. Utilisez une API JSON pour une clé ou un jeton.')
    if config.media_credential_id:
        from app.vault import row
        if row(config.media_credential_id)['kind'] != 'cookies':
            raise HTTPException(400, 'L’extraction média yt-dlp accepte les cookies importés.')
    return config.model_dump()


@app.post('/api/sources', status_code=201)
def add_source(body: SourceCreate):
    if body.connector is not None:
        if not body.name or not body.name.strip():
            raise HTTPException(400, 'Donnez un nom à la source.')
        item = {'id': 'custom-' + uuid.uuid4().hex, 'name': body.name.strip()}
        config = validate_connector(body.connector)
    else:
        item = next((s for s in catalog() if s['id'] == body.id), None)
        if not item:
            raise HTTPException(400, 'Source inconnue du catalogue yt-dlp.')
        if body.instance:
            # One template, many self-hosted instances: each becomes its own saved source.
            if not item.get('instance_software'):
                raise HTTPException(400, 'Ce modèle ne se décline pas par instance.')
            delivered = source_template(item['id'], body.instance)
            config, host = delivered['connector'], delivered['instance']
            item = {**item, 'id': 'custom-' + uuid.uuid4().hex,
                    'name': (body.name or f'{item["instance_software"]} · {host}').strip()[:100],
                    'instance': host, 'playback_extractor': delivered['playback_extractor']}
        else:
            config = default_connector(item['id'])
    with connect() as db:
        if db.execute('SELECT 1 FROM sources WHERE id=? AND owner=?', (item['id'],owner())).fetchone():
            raise HTTPException(409, 'Cette source est déjà ajoutée.')
        if db.execute('SELECT count(*) FROM sources WHERE owner=?',(owner(),)).fetchone()[0] >= 100:
            raise HTTPException(400, 'Limite de 100 sources atteinte.')
        db.execute('INSERT INTO sources(id,name,connector,owner) VALUES (?,?,?,?)', (item['id'], item['name'], json.dumps(config),owner()))
    return {**item, 'enabled': True, 'connector': config, 'search': config['kind'] != 'url'}


@app.patch('/api/sources/{source_id}')
def edit_source(source_id: str, body: SourceEdit):
    values = {}
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(400, 'Donnez un nom à la source.')
        values['name'] = body.name.strip()
    if body.enabled is not None:
        values['enabled'] = body.enabled
    if body.connector is not None:
        values['connector'] = json.dumps(validate_connector(body.connector))
    if not values:
        raise HTTPException(400, 'Aucune modification fournie.')
    with connect() as db:
        if not db.execute('UPDATE sources SET ' + ','.join(f'{key}=?' for key in values) + ' WHERE id=? AND owner=?', (*values.values(), source_id,owner())).rowcount:
            raise HTTPException(404, 'Source introuvable.')
    return {'ok': True}


@app.delete('/api/sources/{source_id}')
def delete_source(source_id: str):
    with connect() as db:
        if not db.execute('DELETE FROM sources WHERE id=? AND owner=?', (source_id,owner())).rowcount:
            raise HTTPException(404, 'Source introuvable.')
    return {'ok': True}


def worker_platform(config):
    """Extractor aliases share a provider budget; independent JSON hosts do not."""
    from urllib.parse import urlsplit
    if config.get('kind') in ('json','html'):
        return urlsplit(config.get('search_url', '')).hostname or 'unknown'
    from app.registry import identities
    extractor = config.get('extractor', '')
    return identities().get(extractor, {}).get('platform_id') or extractor or 'unknown'


async def run_worker(payload, timeout=55):
    config = payload.get('connector') or {}
    platform = worker_platform(config)
    if payload.get('mode') == 'fetch':
        return await _run_worker(payload, timeout)
    lock = platform_locks.setdefault(platform, asyncio.Semaphore(2))
    async with lock:
        remaining_delay = platform_cooldowns.get(platform, 0) - time.monotonic()
        if remaining_delay > 0:
            raise SourceFailure('rate_limited', int(remaining_delay)+1)
        try:
            return await _run_worker(payload, timeout)
        except SourceFailure as exc:
            if exc.code == 'rate_limited':
                platform_cooldowns[platform] = time.monotonic() + (exc.retry_after or 60)
            raise


async def _run_worker(payload, timeout=55):
    config = payload.get('connector') or {}
    if payload.get('mode') == 'search' and config.get('kind') == 'html':
        from app.html_search import search
        try:
            async with workers, asyncio.timeout(timeout):
                return await search(payload)
        except TimeoutError:
            raise SourceFailure('timeout')
    identifier = config.get('credential_id')
    if payload.get('mode') != 'search':
        identifier = config.get('media_credential_id') or identifier
        if identifier:
            from app.vault import row
            if row(identifier)['kind'] != 'cookies':
                identifier = None  # API search tokens are never passed to another extractor.
    if identifier:
        from app.vault import reveal
        payload = {**payload, '_credential': reveal(identifier)}
    async with workers:
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'app.worker',
            env={k: v for k, v in os.environ.items() if not k.startswith('ANYTUBE_SERVICE_')},
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=os.name != 'nt', cwd=Path(__file__).resolve().parent.parent)
        try:
            output, errors = await asyncio.wait_for(process.communicate(json.dumps(payload).encode()), timeout)
            result = json.loads(output)
            if payload.get('_discovery_diagnostics'):
                from app.source_diagnostics import emit,ControlError
                for diagnostic in result.pop('_diagnostics',[])[:20]:emit(**diagnostic)
                if result.get('control_error'):
                    error=result['control_error']
                    raise ControlError(error['code'],error['message'],error.get('correctable',False))
            if process.returncode or result.get('error'):
                failure = SourceFailure(result.get('code'), result.get('retry_after'))
                logger.warning('worker: %s', failure.code)
                raise failure
            return result
        except asyncio.TimeoutError:
            raise SourceFailure('timeout')
        finally:
            if process.returncode is None:
                if os.name == 'nt':
                    killer = await asyncio.create_subprocess_exec('taskkill', '/PID', str(process.pid), '/T', '/F', stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                    await killer.wait()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    sources: list[str] | None = Field(default=None, max_length=100)
    limit: int = Field(default=8, ge=1, le=12)
    cursors: dict[str,str] | None = Field(default=None,max_length=100)
    ranking: Literal['default','views','recent','trending'] = 'default'
    duration: Literal['any','short','long'] = 'any'
    days: Literal[0,1,7,30] = 0


class ConnectorTest(BaseModel):
    connector: Connector
    query: str = Field(min_length=1, max_length=200)


@app.post('/api/connectors/test')
async def test_connector(body: ConnectorTest):
    config = validate_connector(body.connector)
    if not body.query.strip() or config['kind'] == 'url':
        raise HTTPException(400, 'Une recherche et un connecteur de recherche sont requis.')
    if searches.locked():
        raise HTTPException(429, 'Des recherches sont déjà en cours. Réessayez dans un instant.')
    async with searches:
        try:
            result = await run_worker({'mode': 'search', 'connector': config, 'query': body.query.strip(), 'limit': 3})
            check = record(config, body.query, 'verified' if result['items'] else 'empty', len(result['items']))
            result['verification'] = check
            return result
        except RuntimeError as exc:
            record(config, body.query, 'temporarily_unavailable', detail=str(exc))
            raise HTTPException(400, str(exc))


@app.post('/api/search')
async def search(body: SearchRequest):
    if not body.query.strip():
        raise HTTPException(400, 'Saisissez une recherche.')
    enabled = [s for s in saved_sources() if s['enabled']]
    selected = enabled if body.sources is None else [s for s in enabled if s['id'] in body.sources]
    if body.sources is not None and set(body.sources) - {s['id'] for s in selected}:
        raise HTTPException(400, 'Une source sélectionnée est absente ou désactivée.')
    searchable = [s for s in selected if s['connector']['kind'] != 'url']
    if not searchable:
        raise HTTPException(400, 'Sélectionnez au moins une source avec recherche.')
    contexts={s['id']:[s['id'],revision(s['connector']),body.query.strip(),body.ranking,body.duration,body.days,body.limit] for s in searchable}
    offsets={s['id']:decode_cursor((body.cursors or {}).get(s['id']),contexts[s['id']]) for s in searchable}
    configs={s['id']:search_config(s['connector'],body.ranking,body.duration,body.days) for s in searchable}
    if body.cursors is not None:
        searchable=[s for s in searchable if s['id'] in body.cursors]

    async def one(source):
        try:
            offset=offsets[source['id']]
            config = configs[source['id']]
            ceiling = capabilities(config)['max_results']
            if ceiling and offset >= ceiling:
                return {'id':source['id'], 'source': source['name'], 'items': []}
            result = await run_worker({'mode': 'search', 'source': source['id'], 'connector': config, 'query': body.query.strip(), 'limit': min(MAX_RESULTS,offset+body.limit),
                                      **({'page_size':body.limit, 'offset':offset} if native_pagination(config) else {})})
            items=result['items'][:body.limit] if result.get('native_page') else result['items'][offset:offset+body.limit]
            more=result.get('has_more',False) if result.get('native_page') else len(items)==body.limit and offset+body.limit<MAX_RESULTS
            more=more and (not ceiling or offset+body.limit<ceiling)
            record(source['connector'], body.query, 'verified' if items else 'empty', len(items))
            return {'id':source['id'],'source': source['name'], 'cursor':encode_cursor(offset+body.limit,contexts[source['id']]) if more else None,'items': [{**item, 'source': source['name'], 'source_id': source['id']} for item in items]}
        except Exception as exc:
            record(source['connector'], body.query, getattr(exc, 'code', 'temporarily_unavailable'))
            return {'id':source['id'],'source': source['name'], 'items': [], 'error': str(exc),'cursor':encode_cursor(offsets[source['id']],contexts[source['id']])}

    if searches.locked():
        raise HTTPException(429, 'Plusieurs recherches sont déjà en cours. Réessayez dans un instant.')
    async with searches:
        results = await asyncio.gather(*(one(s) for s in searchable))
    items, seen = [], set()
    for index in range(body.limit):
        for result in results:
            if index < len(result['items']):
                item = result['items'][index]
                if item['url'] not in seen:
                    items.append(item)
                    seen.add(item['url'])
    return {'items': items, 'next_cursors':{r['id']:r['cursor'] for r in results if r.get('cursor')}, 'max_results_per_source':MAX_RESULTS, 'errors': [{'source': r['source'], 'message': r['error']} for r in results if 'error' in r],
            'skipped': [s['name'] for s in selected if s['connector']['kind'] == 'url']}


@app.get('/api/home/{source_id}')
async def home_source(source_id: str, ranking: Literal['default', 'trending', 'views', 'recent'] = 'default',cursor: str | None = Query(default=None,max_length=2000)):
    source = next((s for s in saved_sources() if s['id'] == source_id and s['enabled']), None)
    if not source:
        raise HTTPException(404, 'Source absente ou désactivée.')
    config = Connector.model_validate(source['connector'])
    context=[source_id,revision(config.model_dump()),ranking]
    offset=decode_cursor(cursor,context)
    # A search standing in for a home feed is always named as such, never shown as a feed.
    query_label = config.home_query.strip()
    from_search = config.home_kind == 'search' or not config.home_url
    label = ('Flux d’accueil' if config.home_url else f'Recherche : {query_label}')
    if config.home_url and from_search:
        label = f'Recherche utilisée comme accueil : {query_label}'
    if ranking != 'default':
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        label = {'trending': 'Tendances', 'views': 'Plus vues', 'recent': 'Nouveautés'}[ranking]
        custom = getattr(config, f'home_{ranking}_url')
        parts = urlsplit(config.home_url)
        if config.kind in ('json', 'ytdlp') and custom:
            config.home_url = custom
            from_search = config.home_kind == 'search'
            if from_search:
                label += f' · recherche : {query_label}'
        elif config.kind == 'json' and parts.hostname == 'api.dailymotion.com' and parts.path == '/videos':
            from_search = False
            params = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != 'sort']
            params.append(('sort', {'trending': 'trending', 'views': 'visited', 'recent': 'recent'}[ranking]))
            # Keep template placeholders readable for the worker's URL formatting.
            config.home_url = urlunsplit(parts._replace(query=urlencode(params, safe='{}')))
        elif config.kind == 'ytdlp' and config.prefix == 'ytsearch' and ranking == 'views':
            from_search = True
            label += f' · recherche : {query_label}'
        else:
            return {'items': [], 'label': label, 'message': 'Ce classement n’est pas disponible pour cette source. Choisissez Sélection ou configurez un flux JSON dans Mes sources.'}
    if config.kind == 'url' or (not config.home_url and not config.home_query.strip()):
        return {'items': [], 'label': '', 'message': 'Configurez une recherche ou un flux d’accueil pour cette source.'}
    key = hashlib.sha256(json.dumps([owner(), source['id'], source['name'], revision(config.model_dump()), ranking,offset], sort_keys=True).encode()).hexdigest()
    cached = home_cache.get(key)
    if cached and time.monotonic() - cached[0] < 300:
        return cached[1]
    async with searches:
        try:
            result = await run_worker({'mode': 'search', 'source': source_id, 'connector': config.model_dump(),
                                       'query': config.home_query.strip(), 'limit': min(MAX_RESULTS,offset+10), 'home': True, 'ranking': ranking,
                                       **({'page_size':10, 'offset':offset} if native_pagination(config.model_dump()) else {})})
            items=result['items'][:10] if result.get('native_page') else result['items'][offset:offset+10]
            ceiling=capabilities(config.model_dump())['max_results']
            more=result.get('has_more',False) if result.get('native_page') else len(items)==10 and offset+10<MAX_RESULTS
            more=more and (not ceiling or offset+10<ceiling)
            record(source['connector'], ranking, 'verified' if items else 'empty', len(items), feature='home' if ranking=='default' else 'rankings')
            response = {'items': [{**item, 'source': source['name'], 'source_id': source_id} for item in items], 'label': label,'feed_kind':'search' if from_search else 'feed','next_cursor':encode_cursor(offset+10,context) if more else None,'max_results':capabilities(config.model_dump())['max_results']}
        except Exception as exc:
            return {'items': [], 'label': label, 'feed_kind': 'search' if from_search else 'feed', 'error': str(exc)}
    if len(home_cache) >= 100:
        home_cache.pop(next(iter(home_cache)))
    home_cache[key] = (time.monotonic(), response)
    return response


class MediaRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    destination: Literal['cache','library'] = 'cache'
    source_id: str | None = Field(default=None, max_length=150)
    media_kind: Literal['video', 'audio'] = 'video'


def validate_url(url):
    from urllib.parse import urlsplit
    from yt_dlp.extractor import gen_extractor_classes
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('https', 'http') or not parts.hostname or parts.username or parts.password or parts.port not in (None, 80, 443):
            raise ValueError()
    except ValueError:
        raise HTTPException(400, 'Utilisez une URL vidéo HTTP(S) sur un port standard.')
    enabled = {s['connector']['extractor'] for s in saved_sources() if s['enabled']}
    if not any(cls.ie_key() in enabled and cls.suitable(url) for cls in gen_extractor_classes()):
        raise HTTPException(400, 'Ajoutez et activez la source correspondant à cette URL dans Mes sources.')


async def prepare(job_id, url):
    job = jobs[job_id]
    folder = job_folder(job)
    try:
        folder.mkdir(parents=True)
        result = await run_worker({'mode': 'media', 'url': url, 'folder': str(folder), 'max_bytes':job['reserved'],
                                   'connector': job.get('connector'), 'extractor_key': job.get('extractor_key'),
                                   'media_kind': job.get('media_kind','video'), 'max_height':job.get('max_height',720)}, timeout=600)
        jobs[job_id].update(filename=result.get('filename','video.mp4'), media_type=result.get('media_type','video/mp4'))
        jobs[job_id].update(status='ready', video=result['video'], size=job_file(jobs[job_id]).stat().st_size,progress=100)
        if job.get('connector'):
            record(job['connector'], url, 'verified', feature='download')
    except asyncio.CancelledError:
        shutil.rmtree(folder, ignore_errors=True)
        jobs[job_id].update(status='cancelled',error='Préparation annulée ou serveur arrêté.')
        raise
    except Exception as exc:
        jobs[job_id].update(status='error', error=str(exc))
        shutil.rmtree(folder, ignore_errors=True)
    finally:
        persist(jobs[job_id])


def remaining(destination):
    with connect() as db:
        user = db.execute('SELECT quota FROM users WHERE id=?',(owner(),)).fetchone()
    maximum = user['quota'] if destination == 'library' else limits()['cache_bytes']
    used = sum(j.get('size',0) if j['status'] == 'ready' else j.get('reserved',0) if j['status'] == 'preparing' else 0
               for j in jobs.values() if j.get('destination','cache') == destination and (destination == 'cache' or j['owner'] == owner()))
    return max(0, maximum-used)


def cleanup_cache():
    expiration = limits()['cache_hours'] * 3600
    for key, job in list(jobs.items()):
        if job.get('destination','cache') == 'cache' and job['status'] != 'preparing' and time.time() - job['created'] > expiration:
            shutil.rmtree(job_folder(job), ignore_errors=True)
            remove_record(key)
            jobs.pop(key, None)


async def maintain_cache():
    while True:
        await asyncio.sleep(60)
        cleanup_cache()
        source_assistant.cleanup()


@app.get('/api/admin/diagnostics')
def diagnostics():
    from app.accounts import require_admin
    require_admin()
    usage = shutil.disk_usage(media_root())
    return {'health': health(), 'disk': {'total': usage.total, 'free': usage.free},
            'jobs': {status: sum(j['status'] == status for j in jobs.values()) for status in ('preparing','ready','error','cancelled')},
            'cache_bytes': sum(j.get('size',0) for j in jobs.values() if j.get('destination') == 'cache'),
            'limits': limits(), 'network_isolation_configured': bool(os.environ.get('ANYTUBE_PROXY'))}


@app.post('/api/media', status_code=202)
async def media(body: MediaRequest):
    source, extractor_key = select_source(body.url, body.source_id)
    cleanup_cache()
    source_revision = revision(source['connector'])
    existing = next((j for j in jobs.values() if j.get('owner') == owner() and j['url'] == body.url and j.get('media_kind','video') == body.media_kind and j.get('source_revision') == source_revision and j['status'] in ('ready', 'preparing')), None)
    if existing:
        if body.destination == 'library' and existing.get('destination','cache') != 'library':
            if existing['status'] != 'ready':
                raise HTTPException(409,'Attendez la préparation pour conserver cette vidéo.')
            return await keep_media(existing['id'])
        return existing
    if sum(j['status'] == 'preparing' for j in jobs.values()) >= limits()['preparations']:
        raise HTTPException(429, 'Une vidéo est déjà en préparation. Réessayez après sa fin.')
    reserved = min(limits()['media_bytes'], remaining(body.destination))
    if reserved < 1024**2:
        raise HTTPException(409,'Quota atteint. Supprimez des vidéos ou augmentez le quota.')
    reservations = sum(j.get('reserved',0) for j in jobs.values() if j['status'] == 'preparing')
    if shutil.disk_usage(media_root()).free < 2*(reserved+reservations)+100*1024**2:
        raise HTTPException(507,'Espace disque insuffisant pour préparer la vidéo.')
    key = uuid.uuid4().hex
    jobs[key] = {'id': key, 'status': 'preparing', 'created': time.time(), 'url': body.url, 'owner':owner(), 'destination':body.destination,'reserved':reserved,'progress':0}
    jobs[key].update(connector=source['connector'], source_id=source['id'], source_revision=source_revision, extractor_key=extractor_key,
                     media_kind=body.media_kind, max_height=limits()['max_height'])
    persist(jobs[key])
    task = asyncio.create_task(prepare(key, body.url))
    tasks.add(task)
    media_tasks[key] = task
    task.add_done_callback(tasks.discard)
    task.add_done_callback(lambda _: media_tasks.pop(key, None))
    return jobs[key]


@app.get('/api/media')
def media_list():
    return {'items': list(reversed([j for j in jobs.values() if j.get('owner') == owner()])), 'library_remaining':remaining('library')}


@app.get('/api/media/{key}')
def media_status(key: str):
    if key not in jobs or jobs[key].get('owner') != owner():
        raise HTTPException(404, 'Vidéo introuvable ou cache expiré.')
    job = jobs[key]
    if job['status'] == 'preparing':
        try:
            progress = json.loads((job_folder(job) / 'progress.json').read_text())
            job['progress'] = progress['percent']
        except (OSError,ValueError,KeyError):
            pass
    return job


@app.delete('/api/media/{key}')
async def media_delete(key: str):
    job = media_status(key)
    if job['status'] == 'preparing':
        task = media_tasks.get(key)
        if task:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
    shutil.rmtree(job_folder(job), ignore_errors=True)
    remove_record(key)
    del jobs[key]
    return {'ok': True}


@app.get('/api/media/{key}/file')
def media_file(key: str, download: bool = False):
    job = media_status(key)
    if job['status'] != 'ready':
        raise HTTPException(409, 'La vidéo n’est pas prête.')
    return FileResponse(job_file(job), media_type=job.get('media_type','video/mp4'), filename=job_file(job).name if download else None)


@app.post('/api/media/{key}/keep')
async def keep_media(key: str):
    job = media_status(key)
    if job['status'] != 'ready':
        raise HTTPException(409,'La vidéo n’est pas prête.')
    if job.get('destination') == 'library':
        return job
    size = job_file(job).stat().st_size
    if size > remaining('library'):
        raise HTTPException(409,'Quota de bibliothèque insuffisant.')
    original = job_folder(job)
    updated = {**job,'destination':'library','size':size}
    target = job_folder(updated)
    target.parent.mkdir(parents=True,exist_ok=True)
    original.rename(target)
    jobs[key] = updated
    persist(updated)
    return updated


@app.get('/api/sponsors/{video_id}')
def sponsors(video_id: str):
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise HTTPException(400, 'Identifiant YouTube invalide.')
    digest = hashlib.sha256(video_id.encode()).hexdigest()
    try:
        with urlopen(f'https://sponsor.ajay.app/api/skipSegments/{digest[:4]}?categories=%5B%22sponsor%22%5D', timeout=8) as response:
            matches = json.load(response)
        segments = next((m['segments'] for m in matches if m['videoID'] == video_id), [])
        return {'segments': segments, 'status': 'ok'}
    except HTTPError as exc:
        return {'segments': [], 'status': 'empty' if exc.code == 404 else 'unavailable'}
    except Exception:
        return {'segments': [], 'status': 'unavailable'}


app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')


@app.get('/', include_in_schema=False)
def index():
    return FileResponse(Path(__file__).with_name('index.html'))
