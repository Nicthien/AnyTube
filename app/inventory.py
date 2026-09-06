"""Export the installed extractor inventory without inventing platform support."""
from datetime import datetime, timezone
from functools import lru_cache
from yt_dlp.extractor import gen_extractor_classes
from yt_dlp.version import __version__
from app.catalog import catalog
from app.connectors import default_connector
from app.pagination import capabilities
from app.verification import engine_version, revision
from app.registry import identities, feature_matrix, totals, registry_revision, SCHEMA_VERSION


@lru_cache(maxsize=1)
def platform_inventory():
    classes = {c.ie_key(): c for c in gen_extractor_classes()}
    groups = {}
    for entry in catalog():
        cls = classes[entry['id']]
        real = cls.real_class if 'real_class' in dir(cls) else cls
        identity = identities()[entry['id']]
        platform = identity['platform_id']
        config = default_connector(entry['id'])
        group = groups.setdefault(platform, {'platform': platform, 'extractors': [],
            'review_status': 'extractor_inventory_only',
            'limitation': 'Les extracteurs installés ont été inventoriés. L’examen des API publiques et les essais réels de cette plateforme restent à effectuer.'})
        group['extractors'].append({'id': entry['id'], 'name': entry['name'], **identity,
            'features': feature_matrix(config),
            'capabilities': capabilities(config), 'template_revision': revision(config),
            'search': 'to_develop' if config['kind'] == 'url' else 'implemented_not_verified',
            'playback': 'not_verified', 'download': 'not_verified'})
    return sorted(groups.values(), key=lambda g: g['platform'])


def report(sources):
    from app.verification import evidence
    platforms = platform_inventory()
    return {'generated_at': datetime.now(timezone.utc).isoformat(), 'yt_dlp': __version__,
        'schema_version': SCHEMA_VERSION, 'registry_revision': registry_revision(), 'totals': totals(platforms),
        'connector_version': engine_version(), 'complete_platform_review': False,
        'platform_count': len(platforms), 'extractor_count': sum(len(p['extractors']) for p in platforms),
        'platforms': platforms,
        'personal_sources': [{'id': s['id'], 'name': s['name'], 'revision': revision(s['connector']),
                             'verifications': evidence(s['connector'])} for s in sources],
        'limitations': ['La présence d’un extracteur ne certifie ni la recherche, ni la lecture, ni le téléchargement.',
                       'Le rapport distingue l’inventaire automatique et l’examen fonctionnel complet, qui reste ouvert.',
                       'Les anciens tests non associés à une révision du connecteur ne constituent pas une vérification actuelle.']}
