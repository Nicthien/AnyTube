"""Live probes for one reviewed batch. Availability, implementation and verification stay distinct.

A page of results never proves playback or download; it only proves that the listing answered.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yt_dlp.version import __version__
from app.catalog import catalog
from app.connectors import default_connector
from app.pagination import capabilities, search_config
from app.verification import revision, engine_version

# Batch 01: the first twenty search templates in identifier order.
LOT_01 = ['ArchiveOrg', 'BiliBili', 'BiliBiliSearch', 'Dailymotion', 'DailymotionSearch',
          'GameJolt', 'GameJoltSearch', 'GoogleSearch', 'MailRuMusicSearch', 'Niconico',
          'NicovideoSearch', 'NicovideoSearchDate', 'NicovideoSearchURL', 'PRXSeries',
          'PRXSeriesSearch', 'PRXStoriesSearch', 'PRXStory', 'PeerTube', 'PeerTubePlaylist',
          'RedGifsSearch']

# Queries chosen for the audience of each platform; a foreign-language query is not a defect.
QUERIES = {
    'default': ['nature', 'piano', 'documentaire'],
    'BiliBili': ['nature', '音乐', '风景'],
    'BiliBiliSearch': ['nature', '音乐', '风景'],
    'MailRuMusicSearch': ['nature', 'пианино', 'рок'],
    'Niconico': ['nature', '音楽', '風景'],
    'NicovideoSearch': ['nature', '音楽', '風景'],
    'NicovideoSearchDate': ['nature', '音楽', '風景'],
    'NicovideoSearchURL': ['nature', '音楽', '風景'],
    'RedGifsSearch': ['massage', 'dance', 'yoga'],
    'GameJolt': ['nature', 'pixel', 'horror'],
    'GameJoltSearch': ['nature', 'pixel', 'horror'],
    'PRXStory': ['nature', 'climate', 'music'],
    'PRXSeries': ['nature', 'climate', 'music'],
    'PRXStoriesSearch': ['nature', 'climate', 'music'],
    'PRXSeriesSearch': ['nature', 'climate', 'music'],
}

PAGE = 3

# One query answering is enough to show the template works; one failing query is not a verdict.
PRIORITY = ['results_received', 'authentication_required', 'geo_restricted', 'drm_protected',
            'rate_limited', 'empty', 'timeout', 'invalid_response', 'temporarily_unavailable']


def aggregate(statuses):
    statuses = list(statuses)
    return min(statuses, key=lambda s: PRIORITY.index(s) if s in PRIORITY else len(PRIORITY)) if statuses else 'empty'


def environment():
    return {'environment': os.environ.get('ANYTUBE_ENVIRONMENT', 'local'),
            'host': platform.platform(), 'python': platform.python_version(),
            'yt_dlp': __version__, 'connector_version': engine_version(),
            'proxy_configured': bool(os.environ.get('ANYTUBE_PROXY'))}


async def two_pages(config, query, *, home=False, ranking='default'):
    """Read two pages and report counts, fresh URLs and repeats, without merging the pages."""
    from app.main import run_worker
    from app.adapters import native_pagination
    pages, seen, native = [], set(), native_pagination(config)
    for offset in (0, PAGE):
        payload = {'mode': 'search', 'connector': config, 'query': query, 'limit': offset + PAGE,
                   'home': home, 'ranking': ranking}
        if native:
            payload.update(page_size=PAGE, offset=offset)
        try:
            result = await run_worker(payload, timeout=90)
        except Exception as exc:
            pages.append({'offset': offset, 'status': getattr(exc, 'code', 'temporarily_unavailable'),
                          'detail': str(exc)})
            break
        items = result['items'][:PAGE] if result.get('native_page') else result['items'][offset:offset + PAGE]
        urls = [item['url'] for item in items if item.get('url')]
        pages.append({'offset': offset, 'status': 'results_received' if items else 'empty',
                      'count': len(items), 'distinct_urls': len(set(urls)),
                      'new_urls': len(set(urls) - seen), 'repeated_urls': len(urls) - len(set(urls) - seen),
                      'titles': [item['title'][:80] for item in items[:2]],
                      'samples': urls[:2]})
        seen |= set(urls)
        if not items or (native and not result.get('has_more')):
            break
    statuses = [page['status'] for page in pages]
    status = 'results_received' if 'results_received' in statuses else statuses[0]
    return {'pages': pages, 'status': status, 'distinct_urls_over_two_pages': len(seen)}


async def probe(template_id):
    config = default_connector(template_id)
    caps = capabilities(config)
    entry = {'template': template_id, 'connector_kind': config['kind'],
             'extractor': config['extractor'], 'template_revision': revision(config),
             'capabilities': caps, 'date': datetime.now(timezone.utc).isoformat(),
             'does_not_verify': ['video', 'audio', 'live', 'subtitles', 'download'],
             'search': {}, 'home': {}, 'rankings': {}}
    for query in QUERIES.get(template_id, QUERIES['default']):
        entry['search'][query] = await two_pages(config, query)
    if caps['search']:
        entry['home']['default'] = {'query_used': config['home_query'],
                                    'served_by': 'feed' if config.get('home_url') else 'search',
                                    **await two_pages(config, config['home_query'], home=True)}
    for ranking in caps['home_rankings'][1:]:
        current = dict(config)
        custom = config.get('home_' + ranking + '_url')
        if custom:
            current['home_url'] = custom
        entry['rankings']['home:' + ranking] = {
            'served_by': 'feed' if custom and config.get('home_kind', 'feed') == 'feed' else 'search',
            **await two_pages(current, config['home_query'], home=True, ranking=ranking)}
    for ranking in caps['search_rankings'][1:]:
        query = QUERIES.get(template_id, QUERIES['default'])[0]
        entry['rankings']['search:' + ranking] = await two_pages(
            search_config(config, ranking, 'any', 0), query)
    entry['status'] = aggregate(probe['status'] for probe in entry['search'].values())
    entry['per_query_status'] = {query: probe['status'] for query, probe in entry['search'].items()}
    return entry


async def main(args):
    args.output.mkdir(parents=True, exist_ok=True)
    context = environment()
    semaphore = asyncio.Semaphore(2)

    async def guarded(template_id):
        async with semaphore:
            entry = await probe(template_id)
            (args.output / (template_id + '.json')).write_text(
                json.dumps({**context, **entry}, ensure_ascii=False, indent=2), encoding='utf-8')
            print(template_id, entry['status'], flush=True)
            return entry

    known = {item['id'] for item in catalog()}
    selection = [t for t in (args.template or LOT_01) if t in known]
    if args.summarize_only:
        # Re-derive the batch verdict from stored evidence, without touching the network.
        entries = []
        for template_id in selection:
            path = args.output / (template_id + '.json')
            if not path.exists():
                continue
            entry = json.loads(path.read_text(encoding='utf-8'))
            entry['status'] = aggregate(probe['status'] for probe in entry['search'].values())
            entry['per_query_status'] = {q: p['status'] for q, p in entry['search'].items()}
            path.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding='utf-8')
            entries.append(entry)
        context = {key: entries[0][key] for key in ('environment', 'host', 'python', 'yt_dlp',
                                                    'connector_version', 'proxy_configured')} if entries else context
    else:
        entries = await asyncio.gather(*(guarded(t) for t in selection))
    summary = {**context, 'generated_at': datetime.now(timezone.utc).isoformat(),
               'aggregation': 'un modèle est déclaré au meilleur état observé sur ses requêtes',
               'batch': 'lot-01', 'templates': len(entries),
               'results': {e['template']: {'search': e['status'], 'per_query': e['per_query_status'],
                                           'home': e['home'].get('default', {}).get('status'),
                                           'rankings': {k: v['status'] for k, v in e['rankings'].items()}}
                           for e in entries}}
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.update_checks:
        update_checks(args.output, summary)
    print(json.dumps(summary['results'], ensure_ascii=False, indent=2))


def update_checks(output, summary):
    """Refresh only this batch's entries; templates outside the batch keep their own date."""
    path = Path(__file__).resolve().parents[1] / 'app' / 'template_checks.json'
    checks = json.loads(path.read_text(encoding='utf-8'))
    if checks.get('yt_dlp') != summary['yt_dlp']:
        raise SystemExit('yt-dlp a changé de version : reprendre l’audit complet du catalogue.')
    for name in sorted(summary['results']):
        entry = json.loads((output / (name + '.json')).read_text(encoding='utf-8'))
        best = max((page.get('count', 0) for probe in entry['search'].values()
                    for page in probe['pages']), default=0)
        checks['entries'][name] = {'status': entry['status'], 'count': best,
                                   'date': entry['date'], 'batch': summary['batch']}
    checks.setdefault('batches', {})[summary['batch']] = {
        'date': summary['generated_at'], 'connector_version': summary['connector_version'],
        'environment': summary['environment'], 'templates': sorted(summary['results'])}
    path.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    print('template_checks.json :', len(summary['results']), 'entrées du lot rafraîchies')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('docs/source-audit-lot-01'))
    parser.add_argument('--template', action='append')
    parser.add_argument('--summarize-only', action='store_true')
    parser.add_argument('--update-checks', action='store_true')
    asyncio.run(main(parser.parse_args()))
