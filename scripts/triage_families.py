"""Rank the families that have no search template yet, cheapest first.

The catalogue holds 927 inferred families, but most expose no interface a declarative
connector could use. This reads the installed extractor code and separates the families
where a JSON API on a fixed host is already visible from the ones where nothing is.

It is a triage, never a review: a family named here still has to be read, implemented and
probed like any other. It only says where the next batch is likely to be worth its time.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yt_dlp.version import __version__
from yt_dlp.extractor import gen_extractor_classes
from yt_dlp.extractor.common import SearchInfoExtractor
from app.catalog import catalog

# A JSON call whose host is written in the code: the endpoint is stable enough to declare.
API_CALL = re.compile(r"""_download_json\(\s*f?['"](https?://[^'"{}\s]+)""")
# Hosts that belong to an authentication or measurement service, not to a catalogue.
INFRASTRUCTURE = ('adobe', 'auth', 'login', 'token', 'analytics', 'metrics', 'sentry', 'license')


def extractor_root():
    from yt_dlp import extractor
    return Path(extractor.__file__).parent


def families():
    covered, modules = set(), {}
    for item in catalog():
        if item['search']:
            covered.add(item['platform_id'])
    for lazy in gen_extractor_classes():
        if lazy.ie_key() == 'Generic':
            continue
        cls = lazy.real_class if 'real_class' in dir(lazy) else lazy
        module = cls.__module__.removeprefix('yt_dlp.extractor.').split('.')[0]
        entry = modules.setdefault(module, {'family': module, 'extractors': 0, 'search_class': False,
                                            'covered': module in covered})
        entry['extractors'] += 1
        entry['search_class'] |= issubclass(cls, SearchInfoExtractor) or 'search' in lazy.ie_key().lower()
    return modules


def inspect(modules):
    root = extractor_root()
    for name, entry in modules.items():
        path = root / f'{name}.py'
        source = path.read_text(encoding='utf-8', errors='replace') if path.is_file() else ''
        if not source and (root / name).is_dir():
            source = '\n'.join(part.read_text(encoding='utf-8', errors='replace')
                               for part in sorted((root / name).glob('*.py')))
        hosts = {url.split('/')[2] for url in API_CALL.findall(source) if url.count('/') >= 2}
        entry['api_hosts'] = sorted(host for host in hosts
                                    if '.' in host and not host.endswith('.')
                                    and not any(word in host for word in INFRASTRUCTURE))
        entry['mentions_search'] = bool(re.search(r'search', source, re.I))
        # Helpers such as _search_regex are used by nearly every extractor and do
        # not imply a provider search interface. Prefer a literal route hint.
        entry['search_route_hint'] = bool(re.search(
            r'''[/'"](?:search|suche|recherche|buscar)(?:[/?.'"-])''', source, re.I))
        entry['login_required'] = '_perform_login' in source or '_NETRC_MACHINE' in source
    return modules


def score(entry):
    """Cheap first: a visible API, a search hint, several extractors to benefit, no login."""
    return (bool(entry['api_hosts']) * 4 + entry['mentions_search'] * 3
            + entry.get('search_route_hint', False) * 4
            + entry['search_class'] * 3 + min(entry['extractors'], 5)
            - entry['login_required'] * 2)


def main(arguments):
    modules = inspect(families())
    pending = [entry for entry in modules.values() if not entry['covered']]
    status_path = Path(__file__).resolve().parents[1] / 'docs' / 'source-candidate-status.json'
    known = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
    for entry in pending:
        entry['score'] = score(entry)
        if entry['family'] in known:
            entry['last_investigation'] = known[entry['family']]
    held = [entry for entry in pending if entry['family'] in known]
    eligible = pending if arguments.include_held else [entry for entry in pending if entry['family'] not in known]
    ranked = sorted(eligible, key=lambda entry: (-entry['score'], entry['family']))
    with_api = [entry for entry in pending if entry['api_hosts']]
    report = {'yt_dlp': __version__, 'families': len(modules),
              'families_with_a_search_template': len(modules) - len(pending),
              'families_pending': len(pending),
              'pending_with_a_visible_json_api': len(with_api),
              'pending_with_api_and_search_hint': sum(e['mentions_search'] for e in with_api),
              'pending_with_api_and_search_route_hint': sum(e['search_route_hint'] for e in with_api),
              'held_candidates': held,
              'note': 'Un tri de candidats, pas une revue : chaque famille reste à lire, '
                      'implémenter et sonder.',
              'candidates': ranked[:arguments.limit]}
    if arguments.output:
        arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"{report['families']} familles · {report['families_with_a_search_template']} avec modèle "
          f"· {report['families_pending']} restantes")
    print(f"  dont une API JSON visible        : {report['pending_with_a_visible_json_api']}")
    print(f"  dont le code mentionne 'search'  : {report['pending_with_api_and_search_hint']}")
    print(f"\n{min(arguments.limit, len(ranked))} premiers candidats :")
    for entry in ranked[:arguments.limit]:
        flags = ''.join(('A' if entry['api_hosts'] else '-', 'S' if entry['mentions_search'] else '-',
                         'C' if entry['search_class'] else '-', 'L' if entry['login_required'] else '-'))
        print(f"  {entry['score']:3}  {flags}  {entry['family']:24} "
              f"{entry['extractors']:3} extracteur(s)  {', '.join(entry['api_hosts'][:2])}")
    print('\nA = API JSON visible · S = mentionne search · C = classe de recherche · L = connexion requise')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--output', type=Path, default=None)
    parser.add_argument('--include-held', action='store_true', help='Réexaminer aussi les pistes déjà bloquées ou sans recherche textuelle identifiée.')
    main(parser.parse_args())
