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
        # A batch reviews search templates, never a whole platform: the two counts stay apart.
        batch = (entry.get('last_check') or {}).get('batch')
        group['extractors'].append({'id': entry['id'], 'name': entry['name'], **identity,
            'features': feature_matrix(config),
            'capabilities': capabilities(config), 'template_revision': revision(config),
            'search': 'to_develop' if config['kind'] == 'url' else 'implemented_not_verified',
            'search_review': f'batch:{batch}' if batch else 'not_reviewed',
            'limitation': entry.get('limitation', ''),
            'playback': 'not_verified', 'download': 'not_verified'})
        group['search_templates_reviewed'] = sum(
            item['search_review'] != 'not_reviewed' for item in group['extractors'])
    return sorted(groups.values(), key=lambda g: g['platform'])


def search_template_review(platforms):
    """Counts what the batches actually covered, without implying a platform-wide review."""
    entries = [item for group in platforms for item in group['extractors']]
    reviewed = [item for item in entries if item['search_review'] != 'not_reviewed']
    return {'search_templates': sum(item['search'] != 'to_develop' for item in entries),
            'search_templates_reviewed': len(reviewed),
            'platforms_touched_by_a_batch': sum(bool(g.get('search_templates_reviewed')) for g in platforms),
            'batches': sorted({item['search_review'] for item in reviewed}),
            'note': 'Un lot examine des modèles de recherche : ni la plateforme entière, '
                    'ni la lecture, ni le téléchargement ne sont couverts par ce décompte.'}


def report(sources):
    from app.verification import evidence
    platforms = platform_inventory()
    return {'generated_at': datetime.now(timezone.utc).isoformat(), 'yt_dlp': __version__,
        'schema_version': SCHEMA_VERSION, 'registry_revision': registry_revision(), 'totals': totals(platforms),
        'search_template_review': search_template_review(platforms),
        'connector_version': engine_version(), 'complete_platform_review': False,
        'platform_count': len(platforms), 'extractor_count': sum(len(p['extractors']) for p in platforms),
        'platforms': platforms,
        'personal_sources': [{'id': s['id'], 'name': s['name'], 'revision': revision(s['connector']),
                             'verifications': evidence(s['connector'])} for s in sources],
        'limitations': ['La présence d’un extracteur ne certifie ni la recherche, ni la lecture, ni le téléchargement.',
                       'Le rapport distingue l’inventaire automatique et l’examen fonctionnel complet, qui reste ouvert.',
                       'Les anciens tests non associés à une révision du connecteur ne constituent pas une vérification actuelle.',
                       'Un modèle de recherche examiné par un lot reste sans plateforme revue : aucune plateforme n’est déclarée revue dans son ensemble.']}
