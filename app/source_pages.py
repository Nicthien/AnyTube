"""Task-local, bounded page observations and independent validation summaries."""
import json
import re
import time
from contextvars import ContextVar
from urllib.parse import urlsplit
from app.pagination import signature
from app.connectors import public_url
from app.source_diagnostics import emit

cache = ContextVar('source_page_cache', default=None)
progress = ContextVar('source_page_progress', default=None)
STATES = ('recognized', 'deleted', 'access_required', 'network_error', 'unrecognized_player', 'non_video', 'unchecked')


def summarize(evidence):
    pages = evidence.get('pages', [])
    counts = {state: sum(p.get('status') == state for p in pages) for state in STATES}
    positive = [sum(p.get('status') == 'recognized' and index in p.get('terms', []) for p in pages) for index in (0, 1)]
    eligible = (evidence.get('search') == 'verified' and evidence.get('pagination') in ('verified', 'first_page_only')
                and all(positive) and not counts['non_video'] and counts['recognized']<len(pages))
    return {'counts': counts, 'total': len(pages), 'recognized_per_term': positive,
            'eligible_partial': bool(eligible), 'complete': bool(pages) and counts['recognized'] == len(pages)}


def checkpoint(candidate, evidence):
    evidence['page_summary'] = summarize(evidence)
    evidence['configuration_signature'] = signature(candidate)
    if progress.get(): progress.get()(candidate, evidence)


def inspect(response, url, method):
    from app.html_search import document, video_page_evidence
    from app.search_response import classify
    from app.source_assistant import safe_text
    final = public_url(response.get('url') or url)
    text = response.get('text', '')
    status = response.get('status')
    status = status if isinstance(status,int) else None
    category, reason = classify(text, final, status, response.get('content_type', ''))
    soup = document(text)
    hints = {'player_present': bool(soup.select_one('video, iframe')), 'metadata_present': bool(soup.select_one('meta[property^="og:video"], script[type="application/ld+json"]'))}
    state = 'unrecognized_player'
    if category == 'access_required': state = 'access_required'
    elif status in (404, 410): state = 'deleted'
    elif status and status >= 500: state = 'network_error'
    elif category == 'error_page': state = 'deleted'
    elif category == 'usable' and video_page_evidence(text, final):
        state, reason = 'recognized', 'Adresse de lecteur ou métadonnées vidéo exploitables.'
    elif category == 'usable' and soup.select_one('meta[property="og:type"][content="article"], meta[property="og:type"][content="product"]'):
        state, reason = 'non_video', 'Métadonnées explicites de contenu non vidéo, sans indice vidéo exploitable.'
    elif category == 'usable': reason = 'Lecteur non reconnu ; absence de métadonnées probantes, sans preuve de contenu non vidéo.'
    return {'status': state, 'method': method, 'final_url': safe_text(final, 2000), 'http_status': status,
            'reason': reason, 'hints': hints}


async def observe(url, candidate):
    from app import source_assistant as sa
    from app.html_search import search_destination
    public_url(url)
    if search_destination(url, candidate.get('search_url','')):
        return {'status':'non_video','method':'url','final_url':sa.safe_text(url,2000),'reason':'Destination de recherche, pas une page vidéo.','observations':[]}
    observations = cache.get()
    if observations is None: observations = {}
    entry = observations.setdefault(url, {})
    started = time.monotonic()
    for method in ('http', 'chromium'):
        if method not in entry:
            if method == 'chromium' and not sa.settings().browser.url: break
            try:
                if method == 'http': response = await sa.http(url)
                else:
                    response = json.loads((await sa.http(sa.settings().browser.url.rstrip('/')+'/observe', trusted=True,
                        method='POST', body={'url': url, 'query': 'video', 'submit_search': False},
                        headers=sa.service_headers('browser'), timeout=95))['text'])
                    if not isinstance(response,dict):raise ValueError('Observation structurée attendue.')
                    if sa.metrics.get() is not None:
                        sa.metrics.get()['browser_requests'] = sa.metrics.get().get('browser_requests', 0)+response.get('requests', 0)
                    response = {**response, 'text': response.get('html', '')}
                entry[method] = inspect(response, url, method)
            except (sa.DiscoveryError, ValueError, KeyError, OSError, TimeoutError) as exc:
                status = getattr(exc, 'http_status', None)
                entry[method] = {'status': 'deleted' if status in (404,410) else 'access_required' if status in (401,403,429) else 'network_error',
                                 'method': method, 'http_status': status, 'final_url': sa.safe_text(url,2000), 'reason': 'Observation indisponible ou URL refusée.'}
        result = dict(entry[method])
        # Connector-dependent interpretation is deliberately not cached.
        final = result['final_url']
        if search_destination(final, candidate.get('search_url','')) or re.search(r'/(?:categor(?:y|ies)|tags?)(?:/|$)', urlsplit(final).path):
            result.update(status='non_video', reason='Destination identifiée comme recherche ou catégorie, pas comme page vidéo.')
        if result['status'] in ('recognized','non_video','deleted','access_required'): break
    result['duration'] = round(time.monotonic()-started,3)
    result['observations'] = [dict(v) for v in entry.values()]
    return result


async def validate(candidate, evidence, sets):
    ordered=[]
    for index in range(max(len(sets[0]),len(sets[1]))):
        for group in sets[:2]:
            urls=sorted(group)
            if index<len(urls) and urls[index] not in ordered:ordered.append(urls[index])
    evidence['pages'] = [{'url': url, 'terms': [i for i,s in enumerate(sets[:2]) if url in s], 'status': 'unchecked', 'reason': 'Pas encore contrôlée.'} for url in ordered]
    checkpoint(candidate, evidence)
    for page in evidence['pages']:
        page.update(await observe(page['url'], candidate))
        emit(phase='video', requested_url=page['url'], outcome='passed' if page['status']=='recognized' else 'inconclusive',
             code=page['status'], message=page['reason'], method=page['method'], http_status=page.get('http_status'), final_url=page['final_url'])
        if page['status']=='recognized':evidence.setdefault('listing_evidence',{})[page['url']]={'url':page['url'],'method':'rendered_metadata' if page['method']=='chromium' else 'http_metadata'}
        checkpoint(candidate, evidence)
    return evidence
