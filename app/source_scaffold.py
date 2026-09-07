from urllib.parse import parse_qsl, urlsplit
from app.connectors import Connector, Mapping, pointer

NAMES = {
    'id': ('id', 'uuid', 'pageid', 'trackId', 'contentId'),
    'title': ('title', 'name', 'trackName'),
    'url': ('webpage_url', 'descriptionurl', 'trackViewUrl', 'htmlUrl', 'link', 'url'),
    'thumbnail': ('thumburl', 'thumbnail', 'thumbnailUrl', 'artworkUrl600', 'imageUrl'),
    'description': ('description', 'shortDescription', 'summary'),
    'channel': ('channel', 'uploader', 'collectionName', 'displayName'),
    'duration': ('duration', 'lengthSeconds', 'trackTimeMillis'),
    'views': ('views', 'view_count', 'viewCounter'),
    'published': ('publishedAt', 'releaseDate', 'created_time', 'startTime'),
}


def escape(key):
    return str(key).replace('~', '~0').replace('/', '~1')


def leaves(data, path='', depth=0):
    if depth > 12:
        return
    if isinstance(data, dict):
        for key, value in data.items():
            yield from leaves(value, path + '/' + escape(key), depth + 1)
    elif isinstance(data, list):
        # Metadata arrays such as imageinfo generally describe one primary resource.
        if data:
            yield from leaves(data[0], path + '/0', depth + 1)
    else:
        yield path, data


def lists(data, path='', depth=0):
    if depth > 12:
        return
    if isinstance(data, list):
        if data and all(isinstance(item, dict) for item in data[:10]):
            yield path, data
    elif isinstance(data, dict):
        for key, value in data.items():
            yield from lists(value, path + '/' + escape(key), depth + 1)


def infer_mapping(entries):
    sample = entries[:10]
    paths = dict(leaves(sample[0]))
    mapping = {}
    for field, names in NAMES.items():
        candidates = []
        for path in paths:
            name = path.rsplit('/', 1)[-1]
            if name not in names:
                continue
            values = [pointer(item, path) for item in sample]
            if field in ('title', 'url') and not all(isinstance(v, str) and v.strip() for v in values):
                continue
            if field == 'url' and not all(v.startswith(('http://', 'https://', '/', 'serie/')) for v in values):
                continue
            candidates.append((names.index(name), path.count('/'), path))
        mapping[field] = min(candidates)[2] if candidates else ''
    return mapping


def scaffold(data, extractor, search_url, results_path=None, base_url=''):
    # Candidate files must never contain access keys. Auth belongs in the account vault.
    if any(key.lower() in ('key', 'api_key', 'apikey', 'token', 'access_token', 'x-token')
           for key, _ in parse_qsl(urlsplit(search_url).query)):
        raise ValueError('Retirez les identifiants de l’URL ; utilisez le coffre.')
    choices = list(lists(data)) if results_path is None else [(results_path, pointer(data, results_path))]
    candidates = []
    for path, entries in choices:
        if not isinstance(entries, list) or not entries or not all(isinstance(x, dict) for x in entries[:10]):
            continue
        mapping = infer_mapping(entries)
        if mapping['title'] and mapping['url']:
            candidates.append((path, mapping))
    if len(candidates) != 1:
        raise ValueError('Liste ambiguë ou inexploitable : indiquez --results-path sur une liste non vide avec titre et URL.')
    path, mapping = candidates[0]
    return Connector(kind='json', extractor=extractor, search_url=search_url,
                     results_path=path, result_base_url=base_url,
                     duration_unit='milliseconds' if mapping['duration'].endswith('/trackTimeMillis') else 'seconds',
                     mapping=Mapping(**mapping)).model_dump()


