"""Infer a declarative candidate from a saved public JSON response; never certify it."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.connectors import Connector, Mapping, pointer

from app.source_scaffold import NAMES, escape, leaves, lists, infer_mapping, scaffold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', required=True, type=Path, help='Réponse JSON publique, locale, max. 2 Mo')
    parser.add_argument('--extractor', required=True)
    parser.add_argument('--search-url', required=True, help='URL avec {query} et éventuellement {limit}')
    parser.add_argument('--results-path')
    parser.add_argument('--base-url', default='')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--probe', metavar='QUERY', help='Sonder réellement deux pages après génération')
    args = parser.parse_args()
    from app.catalog import catalog
    if args.extractor not in {entry['id'] for entry in catalog()}:
        parser.error('Extracteur inconnu du moteur installé.')
    if args.sample.stat().st_size > 2 * 1024 * 1024:
        parser.error('Réponse trop volumineuse.')
    try:
        config = scaffold(json.loads(args.sample.read_text(encoding='utf-8-sig')),
                          args.extractor, args.search_url, args.results_path, args.base_url)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Candidat écrit. Vérifier pertinence, pagination, champs, accès et lecture ; aucune publication automatique.')
    if args.probe is not None:
        from scripts.audit_lot import two_pages, environment, write_json
        result = asyncio.run(two_pages(config, args.probe, timeout=30))
        from datetime import datetime, timezone
        write_json(args.output.with_suffix('.probe.json'), {
            **environment(), 'date': datetime.now(timezone.utc).isoformat(),
            'query': args.probe, 'result': result,
            'does_not_verify': ['video', 'audio', 'live', 'subtitles', 'download'],
        })
        print(result['status'])


if __name__ == '__main__':
    main()
