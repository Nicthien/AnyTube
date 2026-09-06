"""Resumable per-feature probes. Inventory and live results are distinct artifacts."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.inventory import report
from app.catalog import catalog
from app.connectors import default_connector
from app.verification import revision, engine_version
from app.main import run_worker
from app.pagination import capabilities
from app.registry import identities
from yt_dlp.version import __version__


async def audit(args):
    args.output.mkdir(parents=True, exist_ok=True)
    inventory = report([])
    (args.output/'inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    if not args.live:
        print(json.dumps(inventory['totals'], ensure_ascii=True))
        return
    platforms = sorted({item['platform_id'] for item in catalog() if item['search']})
    if args.platform:
        platforms = sorted(set(args.platform))
        unknown = set(platforms) - {item['platform_id'] for item in catalog()}
        if unknown:
            raise ValueError('Unknown platforms: ' + ', '.join(sorted(unknown)))
    platforms = platforms[args.start:args.start+20]
    semaphore = asyncio.Semaphore(3)

    async def platform_probe(platform):
        async with semaphore:
            distinct = {}
            for item in catalog():
                if item['platform_id'] != platform or not item['search']:
                    continue
                config = default_connector(item['id'])
                distinct.setdefault(json.dumps(config, sort_keys=True), []).append(item['id'])
            for serialized, aliases in distinct.items():
                config = json.loads(serialized)
                for feature in args.feature:
                    queries = args.query if feature == 'search' else capabilities(config)['home_rankings']
                    for query in queries:
                        key = __import__('hashlib').sha256(json.dumps([config,feature,query,engine_version(),__version__]).encode()).hexdigest()
                        path = args.output/(key+'.json')
                        if args.resume and path.exists():
                            continue
                        value = {'date':datetime.now(timezone.utc).isoformat(), 'environment':os.environ.get('ANYTUBE_ENVIRONMENT','local'),
                                 'platform':platform, 'extractors':aliases, 'feature':feature, 'query':query,
                                 'revision':revision(config), 'yt_dlp':__version__, 'connector_version':engine_version(), 'pages':[],
                                 'does_not_verify':['video','audio','live','download']}
                        current = dict(config)
                        if feature == 'home' and query != 'default':
                            current['home_url'] = config.get('home_'+query+'_url', '')
                        try:
                            seen = set()
                            for offset in (0, 2):
                                result = await run_worker({'mode':'search', 'connector':current,
                                    'query':query if feature=='search' else current['home_query'], 'limit':offset+2, 'page_size':2,
                                    'offset':offset, 'home':feature=='home', 'ranking':query if feature=='home' else 'default'}, timeout=55)
                                items=result['items'][:2] if result.get('native_page') else result['items'][offset:offset+2]
                                urls = {i['url'] for i in items if i.get('url')}
                                value['pages'].append({'count':len(items), 'new_urls':len(urls-seen),
                                                       'titles':[i['title'][:100] for i in items], 'status':'results_received' if items else 'empty'})
                                seen |= urls
                                if not items or result.get('native_page') and not result.get('has_more'):
                                    break
                            value['status'] = 'results_received' if seen else 'empty'
                        except Exception as exc:
                            value['status'] = getattr(exc, 'code', 'temporarily_unavailable')
                        temporary = path.with_suffix('.tmp')
                        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
                        temporary.replace(path)
                        print(platform, aliases[0], feature, query, value['status'], flush=True)
    await asyncio.gather(*(platform_probe(p) for p in platforms))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--platform',action='append')
    parser.add_argument('--feature',action='append',choices=['search','home'])
    parser.add_argument('--query',action='append')
    parser.add_argument('--start',type=int,default=0)
    parser.add_argument('--output',type=Path,default=Path('docs/source-audit'))
    args=parser.parse_args()
    args.feature=args.feature or ['search','home']
    args.query=args.query or ['nature','music']
    asyncio.run(audit(args))
