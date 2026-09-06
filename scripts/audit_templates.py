"""Audit every installed default; optionally probe unique searches without saving sources."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.catalog import catalog
from app.connectors import Connector, default_connector
from app.main import run_worker
from yt_dlp.version import __version__


async def audit(live):
    entries = []
    for source in catalog():
        config = Connector.model_validate(default_connector(source['id'])).model_dump()
        entries.append({**source, 'connector': config, 'verification': 'not_tested' if source['search'] else 'url_only_not_tested'})
    if live:
        groups = {}
        for entry in entries:
            if entry['search']:
                groups.setdefault(json.dumps(entry['connector'], sort_keys=True), []).append(entry)
        async def probe(group):
            try:
                result = await run_worker({'mode':'search', 'connector':group[0]['connector'], 'query':'nature', 'limit':2}, timeout=35)
                status = 'results_received' if result['items'] else 'empty'
                detail = {'count':len(result['items'])}
            except Exception as exc:
                status, detail = 'failed', {'error':str(exc)}
            for entry in group:
                entry.update(verification=status, probe=detail)
            print(group[0]['id'], status, flush=True)
        await asyncio.gather(*(probe(group) for group in groups.values()))
    report = {'generated_at':datetime.now(timezone.utc).isoformat(), 'yt_dlp':__version__, 'total':len(entries),
              'search_templates':sum(e['search'] for e in entries), 'query':'nature' if live else None, 'entries':entries}
    path = Path('docs/template-audit.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if live:
        checks = {'generated_at':report['generated_at'], 'yt_dlp':__version__,
                  'entries':{e['id']:{'status':e['verification'], **e.get('probe', {})} for e in entries if e['search']}}
        Path('app/template_checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{path}: {report["total"]} modèles, {report["search_templates"]} avec recherche')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    asyncio.run(audit(parser.parse_args().live))
