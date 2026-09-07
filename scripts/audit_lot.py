"""Live probes for one reviewed batch. Availability, implementation and verification stay distinct.

A page of results never proves playback or download; it only proves that the listing answered.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yt_dlp.version import __version__
from app.catalog import catalog
from app.connectors import default_connector
from app.pagination import capabilities, search_config, signature
from app.verification import revision, engine_version

# Batch 01: the first twenty search templates in identifier order.
LOT_01 = ['ArchiveOrg', 'BiliBili', 'BiliBiliSearch', 'Dailymotion', 'DailymotionSearch',
          'GameJolt', 'GameJoltSearch', 'GoogleSearch', 'MailRuMusicSearch', 'Niconico',
          'NicovideoSearch', 'NicovideoSearchDate', 'NicovideoSearchURL', 'PRXSeries',
          'PRXSeriesSearch', 'PRXStoriesSearch', 'PRXStory', 'PeerTube', 'PeerTubePlaylist',
          'RedGifsSearch']

# Batch 02: the eleven remaining search templates, still in identifier order.
LOT_02 = ['Rokfin', 'RokfinSearch', 'Soundcloud', 'SoundcloudSearch', 'Vimeo', 'VrSquareSearch',
          'YahooSearch', 'Youtube', 'YoutubeMusicSearchURL', 'YoutubeSearch', 'YoutubeSearchURL']

LOT_03 = ['NRKTV', 'Wikimedia', 'ApplePodcasts', 'MicrosoftLearnPlaylist', 'OpenRec', 'ArteTV', 'ARDBetaMediathek', 'CBSNews', 'PatreonCampaign', 'ToonGoggles', 'TubeTuGraz']
BATCHES = {'lot-01': LOT_01, 'lot-02': LOT_02, 'lot-03': LOT_03, 'all': LOT_01 + LOT_02 + LOT_03}

# Queries chosen for the audience of each platform; a foreign-language query is not a defect.
QUERIES = {
    'ToonGoggles': ['robot', 'bernard', 'adventure'],
    'TubeTuGraz': ['science', 'data', 'mathematik'],
    'PatreonCampaign': ['science', 'piano', 'history'],
    'CBSNews': ['nature', 'science', 'music'],
    'ARDBetaMediathek': ['natur', 'musik', 'geschichte'],
    'ArteTV': ['nature', 'piano', 'histoire'],
    'OpenRec': ['minecraft', '佐々木', 'ゲーム'],
    'MicrosoftLearnPlaylist': ['python', 'azure', 'sql'],
    'ApplePodcasts': ['science', 'histoire', 'musique'],
    'Wikimedia': ['nature', 'piano', 'science'],
    'NRKTV': ['natur', 'musikk', 'nyheter'],
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
    'Rokfin': ['news', 'music', 'nature'],
    'RokfinSearch': ['news', 'music', 'nature'],
    'Soundcloud': ['nature', 'piano', 'lofi'],
    'SoundcloudSearch': ['nature', 'piano', 'lofi'],
    'VrSquareSearch': ['VR', 'ライブ', '櫻坂'],
    'YoutubeMusicSearchURL': ['nature', 'piano', 'jazz'],
}

PAGE = 3

# One query answering is enough to show the template works; one failing query is not a verdict.
# Ordered from the most to the least informative. A provider that answers and refuses its own
# media says more than a query that simply matched nothing.
PRIORITY = ['results_received', 'authentication_required', 'unsupported_media', 'geo_restricted',
            'drm_protected', 'rate_limited', 'empty', 'timeout', 'invalid_response',
            'temporarily_unavailable']


def aggregate(statuses):
    statuses = list(statuses)
    return min(statuses, key=lambda s: PRIORITY.index(s) if s in PRIORITY else len(PRIORITY)) if statuses else 'empty'


def environment():
    return {'environment': os.environ.get('ANYTUBE_ENVIRONMENT', 'local'),
            'host': platform.platform(), 'python': platform.python_version(),
            'yt_dlp': __version__, 'connector_version': engine_version(),
            'proxy_configured': bool(os.environ.get('ANYTUBE_PROXY'))}


async def two_pages(config, query, *, home=False, ranking='default', timeout=90):
    """Read two pages and report counts, fresh URLs and repeats, without merging the pages."""
    from app.main import run_worker
    from app.adapters import native_pagination
    pages, seen, native = [], set(), native_pagination(config)
    for offset in (0, PAGE):
        payload = {'mode': 'search', 'connector': config, 'query': query, 'limit': offset + PAGE,
                   'home': home, 'ranking': ranking}
        if native:
            payload.update(page_size=PAGE, offset=offset)
        started = time.monotonic()
        try:
            result = await run_worker(payload, timeout=timeout)
        except Exception as exc:
            pages.append({'offset': offset, 'status': getattr(exc, 'code', 'temporarily_unavailable'),
                          'detail': str(exc), 'elapsed_seconds': round(time.monotonic() - started, 3)})
            break
        items = result['items'][:PAGE] if result.get('native_page') else result['items'][offset:offset + PAGE]
        urls = [item['url'] for item in items if item.get('url')]
        pages.append({'offset': offset, 'status': 'results_received' if items else 'empty',
                      'elapsed_seconds': round(time.monotonic() - started, 3),
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


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


async def probe(template_id, instance='', *, checkpoint=None, resume=False, timeout=90):
    stored = {}
    if resume and checkpoint and checkpoint.exists():
        stored = json.loads(checkpoint.read_text(encoding='utf-8'))
    context = environment()
    scenarios = {}
    reused = set()

    async def measure(config, query, **options):
        key = signature([revision(config), config, query, options, PAGE, timeout, context, 1])
        if key in scenarios or key in stored:
            result = scenarios.get(key) or stored[key]
            reused.add(key)
        else:
            result = {**await two_pages(config, query, timeout=timeout, **options),
                      'date': datetime.now(timezone.utc).isoformat()}
        scenarios[key] = result
        if checkpoint:
            write_json(checkpoint, {**stored, **scenarios})
        return result

    config = default_connector(template_id, instance) if instance else default_connector(template_id)
    caps = capabilities(config)
    entry = {'template': template_id, 'instance': instance, 'connector_kind': config['kind'],
             'extractor': config['extractor'], 'template_revision': revision(config),
             'capabilities': caps, 'date': datetime.now(timezone.utc).isoformat(),
             'does_not_verify': ['video', 'audio', 'live', 'subtitles', 'download'],
             'search': {}, 'home': {}, 'rankings': {}}
    for query in QUERIES.get(template_id, QUERIES['default']):
        entry['search'][query] = await measure(config, query)
    if caps['search']:
        entry['home']['default'] = {'query_used': config['home_query'],
                                    'served_by': 'feed' if config.get('home_url') else 'search',
                                    **await measure(config, config['home_query'], home=True)}
    for ranking in caps['home_rankings'][1:]:
        current = dict(config)
        custom = config.get('home_' + ranking + '_url')
        if custom:
            current['home_url'] = custom
        entry['rankings']['home:' + ranking] = {
            'served_by': 'feed' if custom and config.get('home_kind', 'feed') == 'feed' else 'search',
            **await measure(current, config['home_query'], home=True, ranking=ranking)}
    for ranking in caps['search_rankings'][1:]:
        query = QUERIES.get(template_id, QUERIES['default'])[0]
        entry['rankings']['search:' + ranking] = await measure(
            search_config(config, ranking, 'any', 0), query)
    entry['status'] = aggregate(probe['status'] for probe in entry['search'].values())
    entry['per_query_status'] = {query: probe['status'] for query, probe in entry['search'].items()}
    dates = [result['date'] for result in scenarios.values()]
    entry['date'] = max(dates) if dates else entry['date']
    entry['oldest_scenario_date'] = min(dates) if dates else entry['date']
    entry['scenarios_reused'] = len(reused)
    entry['scenarios_executed'] = len(scenarios) - len(reused)
    return entry


def observed_timing(entry):
    seen, durations = set(), []
    def scan(value):
        if isinstance(value, dict):
            if 'pages' in value and 'date' in value:
                key = signature([value['date'], value['pages']])
                if key not in seen:
                    seen.add(key)
                    durations.extend(page.get('elapsed_seconds', 0) for page in value['pages'])
            else:
                for child in value.values():
                    scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)
    scan(entry)
    return {'template': entry['template'], 'observed_worker_seconds': round(sum(durations), 3),
            'page_probes': len(durations), 'status': entry['status']}


def schedule(selection, output, connector_version):
    """Start previously slow sources first, retaining every requested template."""
    path = output / 'performance.json'
    if not path.exists():
        return list(selection)
    try:
        report = json.loads(path.read_text(encoding='utf-8'))
        # Historical costs only influence order, never evidence reuse. Keeping them
        # after an engine change avoids leaving slow providers at the end of a run.
        # probe() independently requires the exact revision and environment.
        costs = {}
        for row in report['templates']:
            cost = row.get('observed_worker_seconds')
            if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0:
                costs[row['template']] = cost
        return sorted(selection, key=lambda name: -costs.get(name, 0))
    except (ValueError, KeyError, TypeError, AttributeError):
        return list(selection)


async def main(args):
    if args.instance:
        from app.connectors import instance_host
        args.instance = instance_host(args.instance)
    args.output.mkdir(parents=True, exist_ok=True)
    context = environment()
    if not 1 <= args.concurrency <= 4 or args.timeout <= 0:
        raise SystemExit('Concurrence : 1 à 4 ; délai strictement positif.')
    if args.instance and args.update_checks:
        raise SystemExit('Une instance ne doit pas remplacer la preuve du modèle par défaut.')
    started = time.monotonic()
    semaphore = asyncio.Semaphore(args.concurrency)
    checkpoint_dir = args.output / '.checkpoints'
    checkpoint_dir.mkdir(exist_ok=True)

    async def guarded(template_id):
        async with semaphore:
            name = template_id + ('@' + args.instance if args.instance else '')
            checkpoint = checkpoint_dir / (signature([template_id, args.instance]) + '.json')
            entry = await probe(template_id, args.instance, checkpoint=checkpoint,
                                resume=args.resume, timeout=args.timeout)
            (args.output / (name + '.json')).write_text(
                json.dumps({**context, **entry}, ensure_ascii=False, indent=2), encoding='utf-8')
            print(name, entry['status'], flush=True)
            return entry

    if args.instance and not args.template:
        raise SystemExit('--instance demande --template.')
    known = {item['id'] for item in catalog()}
    unknown = set(args.template or []) - known
    if unknown:
        raise SystemExit('Modèles inconnus : ' + ', '.join(sorted(unknown)))
    selection = [t for t in (args.template or BATCHES[args.batch]) if t in known]
    if args.summarize_only:
        # Re-derive the batch verdict from stored evidence, without touching the network.
        entries = []
        for template_id in selection:
            path = args.output / (template_id + ('@' + args.instance if args.instance else '') + '.json')
            if not path.exists():
                raise SystemExit(f'Preuve manquante : {template_id}. Relancez avec --resume.')
            entry = json.loads(path.read_text(encoding='utf-8'))
            entries.append(entry)
        context_keys = ('environment', 'host', 'python', 'yt_dlp', 'connector_version', 'proxy_configured')
        if entries and any(tuple(e.get(k) for k in context_keys) !=
                           tuple(entries[0].get(k) for k in context_keys) for e in entries):
            raise SystemExit('Preuves de révisions ou environnements différents. Relancez avec --resume.')
        for entry in entries:
            entry['status'] = aggregate(probe['status'] for probe in entry['search'].values())
            entry['per_query_status'] = {q: p['status'] for q, p in entry['search'].items()}
        context = {key: entries[0][key] for key in ('environment', 'host', 'python', 'yt_dlp',
                                                    'connector_version', 'proxy_configured')} if entries else context
    else:
        ordered = schedule(selection, args.output, context['connector_version'])
        entries = await asyncio.gather(*(guarded(t) for t in ordered))
        positions = {name: index for index, name in enumerate(selection)}
        entries.sort(key=lambda entry: positions[entry['template']])
    summary = {**context, 'generated_at': datetime.now(timezone.utc).isoformat(),
               'elapsed_seconds': round(time.monotonic() - started, 3),
               'aggregation': 'un modèle est déclaré au meilleur état observé sur ses requêtes',
               'batch': args.batch, 'templates': len(entries),
               'execution': {
                   'mode': 'summarize_only' if args.summarize_only else 'resume' if args.resume else 'network',
                   'scenarios_executed': 0 if args.summarize_only else sum(e.get('scenarios_executed', 0) for e in entries),
                   'scenarios_reused': 0 if args.summarize_only else sum(e.get('scenarios_reused', 0) for e in entries),
                   'proofs_aggregated': len(entries) if args.summarize_only else 0,
               },
               'results': {e['template']: {'search': e['status'], 'per_query': e['per_query_status'],
                                           'home': e['home'].get('default', {}).get('status'),
                                           'rankings': {k: v['status'] for k, v in e['rankings'].items()}}
                           for e in entries}}
    summary_name = 'summary-selection.json' if args.template else 'summary.json'
    write_json(args.output / ('performance-selection.json' if args.template else 'performance.json'), {
        'connector_version': context['connector_version'],
        'note': 'Durées cumulées des pages observées, pas le temps mural ; scénarios réutilisés comptés une fois.',
        'templates': sorted((observed_timing(entry) for entry in entries),
                            key=lambda row: -row['observed_worker_seconds'])})
    # Keep the fresh campaign duration when a later resume reuses its evidence.
    if not args.resume and not args.summarize_only:
        network_name = 'summary-selection-network.json' if args.template else 'summary-network.json'
        write_json(args.output / network_name, summary)
    write_json(args.output / summary_name, summary)
    if args.update_checks:
        update_checks(args.output, summary)
    # Windows redirected consoles can use cp1252 even when evidence files are UTF-8.
    print(json.dumps(summary['results'], ensure_ascii=True, indent=2))


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
        checks['entries'][name] = {'status': summary['results'][name]['search'], 'count': best,
                                   'date': entry['date'], 'batch': summary['batch']}
    checks.setdefault('batches', {})[summary['batch']] = {
        'date': summary['generated_at'], 'connector_version': summary['connector_version'],
        'environment': summary['environment'], 'templates': sorted(summary['results'])}
    path.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    print('template_checks.json :', len(summary['results']), 'entrées du lot rafraîchies')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', choices=sorted(BATCHES), default='lot-01')
    parser.add_argument('--output', type=Path, default=None)
    parser.add_argument('--template', action='append')
    parser.add_argument('--instance', default='',
                        help="hôte d'une instance auto-hébergée, pour un modèle qui se décline")
    parser.add_argument('--summarize-only', action='store_true')
    parser.add_argument('--update-checks', action='store_true')
    parser.add_argument('--resume', action='store_true', help='Réutiliser les scénarios de même révision et environnement ; omettre pour une mesure fraîche.')
    parser.add_argument('--concurrency', type=int, default=2)
    parser.add_argument('--timeout', type=float, default=90)
    arguments = parser.parse_args()
    if arguments.output is None:
        arguments.output = Path('docs/source-audit-' + arguments.batch)
    asyncio.run(main(arguments))
