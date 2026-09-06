"""Complete installed inventory, kept separate from human reviews and live evidence."""
from collections import Counter
from functools import lru_cache
import hashlib
import inspect
import json
from pathlib import Path
from yt_dlp.extractor import gen_extractor_classes
from yt_dlp.version import __version__

FEATURES = ('search', 'home', 'rankings', 'filters', 'pagination', 'collections',
            'resolve', 'video', 'audio', 'live', 'subtitles', 'download')
SCHEMA_VERSION = 1


@lru_cache(maxsize=1)
def identities():
    from yt_dlp.extractor.common import SearchInfoExtractor
    result = {}
    for lazy in gen_extractor_classes():
        if lazy.ie_key() == 'Generic':
            continue
        cls = lazy.real_class if 'real_class' in dir(lazy) else lazy
        module = cls.__module__.removeprefix('yt_dlp.extractor.')
        try:
            source = inspect.getsource(cls)
        except (OSError, TypeError):
            # Some aliases are generated with type(); hash their defining module.
            source = Path(inspect.getfile(cls)).read_text(encoding='utf-8') + '\n' + cls.ie_key()
        # These are code-derived candidates, never a reviewed platform mapping.
        search = issubclass(cls, SearchInfoExtractor) or 'Search' in cls.ie_key()
        collection = any(word in cls.ie_key() for word in ('Playlist', 'Channel', 'User', 'Tab', 'Series'))
        result[cls.ie_key()] = {
            'platform_id': module.split('.')[0], 'mapping_status': 'inferred_from_module',
            'role': 'search' if search else 'collection' if collection else 'media_or_variant',
            'role_status': 'inferred_from_code',
            'extractor_revision': hashlib.sha256(source.encode()).hexdigest()[:16],
            'references': [f'https://github.com/yt-dlp/yt-dlp/blob/{__version__}/yt_dlp/extractor/{module.replace(".", "/")}.py'],
            'access': {'netrc_machine': getattr(cls, '_NETRC_MACHINE', None),
                       'login_method_present': cls._perform_login.__qualname__ != 'InfoExtractor._perform_login'},
        }
    return result


def feature_matrix(config):
    from app.pagination import capabilities
    caps = capabilities(config)
    implemented = {'search': caps['search'], 'home': caps['search'],
                   'rankings': len(caps['home_rankings']) > 1 or len(caps['search_rankings']) > 1,
                   'filters': caps['duration'] or caps['date'], 'pagination': caps['pagination'],
                   'collections': bool(config.get('extractor')), 'resolve': bool(config.get('extractor')),
                   'video': bool(config.get('extractor')), 'audio': bool(config.get('extractor')),
                   'live': bool(config.get('extractor')), 'subtitles': bool(config.get('extractor')),
                   'download': bool(config.get('extractor'))}
    return {feature: {'availability': 'not_reviewed',
                      'implementation': 'generic_path' if implemented.get(feature) else 'to_develop',
                      'verification': 'not_verified'} for feature in FEATURES}


def registry_revision():
    return hashlib.sha256(json.dumps(identities(), sort_keys=True).encode()).hexdigest()[:16]


def totals(platforms):
    entries = [entry for group in platforms for entry in group['extractors']]
    return {'platforms': len(platforms), 'extractors': len(entries),
            'reviewed_platforms': sum(p['review_status'] == 'reviewed' for p in platforms),
            'features': {name: dict(Counter(e['features'][name]['implementation'] for e in entries)) for name in FEATURES},
            'verified_platforms': 0,
            'note': 'Les chemins génériques ne constituent ni une revue ni une vérification de plateforme.'}
