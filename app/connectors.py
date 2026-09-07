"""Declarative search connectors. No executable expressions or user scripts."""
import ipaddress
import json
import math
import re
import os
from string import Formatter
from typing import Literal
from urllib.parse import quote, urlsplit, parse_qsl, urlencode, urlunsplit, urljoin
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from pydantic import BaseModel, ConfigDict, Field, model_validator
from yt_dlp.utils import clean_html
from app.catalog import SEARCH, URL_SEARCH, search_prefixes

PREFIXES = sorted(({value[1] for value in SEARCH.values()} | set(search_prefixes().values())) - {'dailymotion'})


def public_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.port not in (None, 80, 443):
        raise ValueError('URL HTTP(S) publique sans identifiants, sur un port standard, requise.')
    host = parts.hostname.lower()
    if host == 'localhost' or host.endswith(('.localhost', '.local')):
        raise ValueError('Les adresses locales ne sont pas autorisées.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return url
    if not address.is_global:
        raise ValueError('Les adresses privées ne sont pas autorisées.')
    return url


def template(value, allowed):
    names = set()
    for _, name, spec, conversion in Formatter().parse(value):
        if name is not None and (name not in allowed or spec or conversion):
            raise ValueError('Variable de modèle invalide.')
        if name is not None:
            names.add(name)
    rendered = value.format(**{key: 'example' for key in allowed})
    public_url(rendered)
    if '{' in urlsplit(value).netloc or '}' in urlsplit(value).netloc:
        raise ValueError('Le domaine doit être fixe, sans variable.')
    return names


class Mapping(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = '/id'
    title: str = '/title'
    url: str = '/url'
    thumbnail: str = '/thumbnail'
    description: str = '/description'
    channel: str = '/channel'
    duration: str = '/duration'
    views: str = '/views'
    published: str = ''

    @model_validator(mode='after')
    def paths(self):
        for value in self.model_dump().values():
            if len(value) > 300 or (value and not value.startswith('/')) or re.search(r'~(?![01])', value):
                raise ValueError('Les chemins JSON doivent commencer par / (exemple : /owner/name).')
        return self


class Pagination(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['prefix', 'page', 'offset', 'single'] = 'prefix'
    parameter: str = Field(default='page', max_length=100, pattern=r'^\$?[A-Za-z_][A-Za-z0-9_]*(?:\[[A-Za-z_][A-Za-z0-9_]*\])?$')
    has_more_path: str = Field(default='', max_length=300)
    # Documented ceiling of the provider window; 0 means the provider states no limit.
    maximum_results: int = Field(default=0, ge=0, le=100000)
    fixed_page_size: int = Field(default=0, ge=0, le=1000)
    first_page: int = Field(default=1, ge=0, le=1)
    page_url_path: str = Field(default='', max_length=300)
    initial_results_path: str = Field(default='', max_length=300)

    @model_validator(mode='after')
    def check(self):
        if self.fixed_page_size and self.mode != 'page':
            raise ValueError('La taille fixe nécessite une pagination par numéro de page.')
        if self.page_url_path:
            if self.mode != 'page' or not self.initial_results_path:
                raise ValueError('Un lien de pagination nécessite le mode page et la liste initiale.')
            for path in (self.page_url_path, self.initial_results_path):
                if not path.startswith('/') or re.search(r'~(?![01])', path):
                    raise ValueError('Chemin de découverte de pagination invalide.')
        if self.has_more_path and (not self.has_more_path.startswith('/') or re.search(r'~(?![01])', self.has_more_path)):
            raise ValueError('Chemin de pagination JSON Pointer invalide.')
        return self


class Connector(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['url', 'ytdlp', 'json'] = 'url'
    query_escape: Literal['none', 'plain'] = 'none'
    credential_id: str = Field(default='', max_length=64, pattern=r'^[a-zA-Z0-9-]*$')
    media_credential_id: str = Field(default='', max_length=64, pattern=r'^[a-zA-Z0-9-]*$')
    method: Literal['GET', 'POST'] = 'GET'
    body: dict[str, str | int | bool] = Field(default_factory=dict, max_length=30)
    pagination: Pagination = Field(default_factory=Pagination)
    extractor: str = Field(default='', max_length=150)
    prefix: str = Field(default='ytsearch', max_length=50)
    search_url: str = Field(default='', max_length=2000)
    search_trending_url: str = Field(default='', max_length=2000)
    search_views_url: str = Field(default='', max_length=2000)
    search_recent_url: str = Field(default='', max_length=2000)
    item_url: str = Field(default='', max_length=2000)
    results_path: str = Field(default='/list', max_length=300)
    results_total_path: str = Field(default='', max_length=300)
    duration_unit: Literal['seconds', 'milliseconds'] = 'seconds'
    video_url: str = Field(default='', max_length=2000)
    video_url_boolean_path: str = Field(default='', max_length=300)
    video_url_false: str = Field(default='', max_length=2000)
    result_base_url: str = Field(default='', max_length=2000)
    thumbnail_url: str = Field(default='', max_length=2000)
    thumbnail_substitutions: dict[str, str] = Field(default_factory=dict, max_length=8)
    home_query: str = Field(default='vidéos', max_length=200)
    home_kind: Literal['feed', 'search'] = 'feed'
    home_url: str = Field(default='', max_length=2000)
    home_trending_url: str = Field(default='', max_length=2000)
    home_views_url: str = Field(default='', max_length=2000)
    home_recent_url: str = Field(default='', max_length=2000)
    mapping: Mapping = Field(default_factory=Mapping)

    @model_validator(mode='after')
    def check(self):
        if self.video_url_boolean_path or self.video_url_false:
            if self.kind != 'json' or not self.video_url or not self.video_url_false:
                raise ValueError('Deux modèles JSON sont requis pour les URL conditionnelles.')
            if not self.video_url_boolean_path.startswith('/') or re.search(r'~(?![01])', self.video_url_boolean_path):
                raise ValueError('Chemin du booléen de sélection URL invalide.')
            template(self.video_url_false, {'id'})
        if self.result_base_url:
            if self.kind != 'json':
                raise ValueError('La base des URL de résultats nécessite un connecteur JSON.')
            template(self.result_base_url, set())
        for key, value in self.thumbnail_substitutions.items():
            if not key or len(key) > 100 or len(value) > 200:
                raise ValueError('Substitution de vignette invalide.')
        if self.kind != 'json' and (self.method != 'GET' or self.body or self.pagination.mode != 'prefix'):
            raise ValueError('POST et pagination native nécessitent un connecteur JSON.')
        if self.method == 'GET' and self.body:
            raise ValueError('Un corps JSON nécessite la méthode POST.')
        if self.pagination.page_url_path and self.method != 'GET':
            raise ValueError('La découverte de pagination nécessite GET.')
        body_query = False
        for value in self.body.values():
            if isinstance(value, str):
                if len(value) > 2000:
                    raise ValueError('Valeur JSON trop longue.')
                for _, name, spec, conversion in Formatter().parse(value):
                    if name is not None and (name not in ('query', 'limit') or spec or conversion):
                        raise ValueError('Variable de corps JSON invalide.')
                    body_query |= name == 'query'
        for url in (self.home_url, self.home_trending_url, self.home_views_url, self.home_recent_url):
            if not url:
                continue
            if self.kind not in ('json', 'ytdlp'):
                raise ValueError('Un connecteur de recherche est requis pour un flux d’accueil.')
            if 'query' in template(url, {'query', 'limit'}):
                # An accueil built from home_query is a search and is named as one, always.
                self.home_kind = 'search'
        for url in (self.search_trending_url, self.search_views_url, self.search_recent_url):
            if not url:
                continue
            if self.kind not in ('json', 'ytdlp'):
                raise ValueError('Un connecteur de recherche est requis pour un classement de recherche.')
            if 'query' not in template(url, {'query', 'limit'}) and not body_query:
                raise ValueError('L’URL de classement doit contenir {query}.')
        if self.item_url:
            if self.kind != 'ytdlp':
                raise ValueError('Le modèle d’URL par résultat s’applique aux connecteurs yt-dlp ; utilisez video_url en JSON.')
            template(self.item_url, {'id'})
        if self.kind == 'ytdlp' and self.prefix not in PREFIXES:
            raise ValueError('Préfixe de recherche yt-dlp non pris en charge.')
        if self.kind == 'ytdlp' and self.search_url:
            if 'query' not in template(self.search_url, {'query', 'limit'}):
                raise ValueError('L’URL de recherche doit contenir {query}.')
        if self.kind == 'json':
            if self.results_total_path and (not self.results_total_path.startswith('/') or re.search(r'~(?![01])', self.results_total_path)):
                raise ValueError('Le chemin du total doit être un JSON Pointer valide.')
            if self.thumbnail_url:
                template(self.thumbnail_url, {'id'})
                if not self.mapping.id:
                    raise ValueError('Un identifiant est requis pour le modèle de vignette.')
            names = template(self.search_url, {'query', 'limit'})
            if 'query' not in names and not body_query:
                raise ValueError('L’URL de recherche doit contenir {query}.')
            if self.results_path and not self.results_path.startswith('/'):
                raise ValueError('Le chemin des résultats doit commencer par /.')
            if re.search(r'~(?![01])', self.results_path):
                raise ValueError('Échappement JSON Pointer invalide.')
            if not self.mapping.title or not (self.mapping.url or self.video_url):
                raise ValueError('Le titre et une URL vidéo sont requis.')
            if self.video_url:
                template(self.video_url, {'id'})
                if not self.mapping.id:
                    raise ValueError('Le champ identifiant est requis pour le modèle d’URL vidéo.')
        return self


def instance_host(value, fallback=''):
    """Self-hosted software shares one API across many hosts; the host stays fixed once chosen."""
    value = (value or '').strip()
    if not value:
        return fallback
    parts = urlsplit(value if '//' in value else 'https://' + value)
    if parts.scheme not in ('http', 'https'):
        raise ValueError('Indiquez le domaine de l’instance, éventuellement préfixé par https://.')
    if parts.path.strip('/') or parts.query or parts.fragment:
        raise ValueError('Indiquez seulement le domaine de l’instance, sans chemin ni paramètre.')
    public_url(urlunsplit(('https', parts.netloc, '/', '', '')))
    return parts.hostname.lower()


def default_connector(source_id, instance=''):
    from app.catalog import declarative_templates
    delivered = declarative_templates().get(source_id)
    if delivered:
        return Connector.model_validate(delivered['connector']).model_dump()
    if source_id in ('PeerTube', 'PeerTubePlaylist'):
        base = 'https://' + instance_host(instance, 'framatube.org') + '/api/v1/'
        feed = base + 'videos?count={limit}'
        return Connector(kind='json', extractor='PeerTube', home_query='peertube',
            search_url=base+'search/videos?search={query}&count={limit}&sort=-match',
            search_views_url=base+'search/videos?search={query}&count={limit}&sort=-views',
            search_recent_url=base+'search/videos?search={query}&count={limit}&sort=-publishedAt',
            home_url=feed+'&sort=-publishedAt', home_recent_url=feed+'&sort=-publishedAt',
            home_views_url=feed+'&sort=-views', home_trending_url=feed+'&sort=-trending',
            pagination=Pagination(mode='offset',parameter='start'), results_path='/data',
            mapping=Mapping(id='/uuid',title='/name',thumbnail='/thumbnailPath',channel='/channel/displayName',published='/publishedAt')).model_dump()
    if source_id == 'Vimeo':
        base = 'https://api.vimeo.com/videos?query={query}&per_page={limit}'
        return Connector(kind='json',extractor='Vimeo',search_url=base,home_url=base,
            search_recent_url=base+'&sort=date&direction=desc',search_views_url=base+'&sort=plays&direction=desc',
            home_recent_url=base+'&sort=date&direction=desc',home_views_url=base+'&sort=plays&direction=desc',
            pagination=Pagination(mode='page'),results_path='/data',
            mapping=Mapping(id='/uri',title='/name',url='/link',thumbnail='/pictures/sizes/2/link',channel='/user/name',views='/stats/plays',published='/created_time')).model_dump()
    if source_id == 'ArchiveOrg':
        base = 'https://archive.org/advancedsearch.php?output=json&rows={limit}&fl[]=identifier&fl[]=title&fl[]=description&fl[]=creator'
        browse = base + '&q=mediatype%3Amovies&sort[]='
        query = base + '&q=mediatype%3Amovies%20AND%20({query})'
        recent = browse + 'publicdate+desc'
        return Connector(kind='json', extractor='ArchiveOrg', query_escape='plain',
            pagination=Pagination(mode='page'),
            search_url=query,
            search_views_url=query + '&sort[]=downloads+desc',
            search_recent_url=query + '&sort[]=publicdate+desc',
            search_trending_url=query + '&sort[]=week+desc',
            home_url=recent, home_recent_url=recent,
            home_views_url=browse + 'downloads+desc', home_trending_url=browse + 'week+desc',
            results_path='/response/docs', video_url='https://archive.org/details/{id}',
            thumbnail_url='https://archive.org/services/img/{id}',
            mapping=Mapping(id='/identifier', url='', thumbnail='', channel='/creator', duration='', views='')).model_dump()
    if source_id in ('PRXStory', 'PRXStoriesSearch', 'PRXSeries', 'PRXSeriesSearch'):
        # yt-dlp calls the same CMS API, but only a JSON connector can carry a vault bearer.
        series = source_id.startswith('PRXSeries')
        endpoint = 'series/search' if series else 'stories/search'
        return Connector(kind='json', extractor='PRXSeries' if series else 'PRXStory',
            search_url=f'https://cms.prx.org/api/v1/{endpoint}?q={{query}}&per={{limit}}',
            pagination=Pagination(mode='page'), results_path='/_embedded/prx:items',
            video_url=('https://beta.prx.org/series/{id}' if series else 'https://beta.prx.org/stories/{id}'),
            mapping=Mapping(id='/id', title='/title', url='', description='/description',
                            thumbnail='/_embedded/prx:image/_links/enclosure/href',
                            channel='/_embedded/prx:account/name', duration='/duration',
                            views='', published='/releasedAt')).model_dump()
    if source_id in ('Niconico', 'NicovideoSearch', 'NicovideoSearchDate', 'NicovideoSearchURL'):
        # yt-dlp scrapes nicovideo.jp/search, whose markup no longer carries data-video-id.
        # The Snapshot Search API v2 is the documented public interface for the same listing.
        base = ('https://snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search'
                '?fields=contentId%2Ctitle%2Cdescription%2CviewCounter%2ClengthSeconds%2CstartTime%2CthumbnailUrl'
                '&_context=AnyTube&_limit={limit}')
        search = base + '&targets=title%2Cdescription%2Ctags&q={query}&_sort='
        # An empty q with tagsExact is a corpus-wide listing, not a query typed by the reader.
        feed = base + '&targets=tagsExact&q=&_sort='
        default = '-startTime' if source_id == 'NicovideoSearchDate' else '-viewCounter'
        return Connector(kind='json', extractor='Niconico',
            # The snapshot API answers 400 past _offset + _limit = 1600.
            pagination=Pagination(mode='offset', parameter='_offset', maximum_results=1600),
            results_path='/data',
            search_url=search + default,
            search_views_url=search + '-viewCounter', search_recent_url=search + '-startTime',
            home_url=feed + '-startTime', home_recent_url=feed + '-startTime',
            home_views_url=feed + '-viewCounter',
            video_url='https://www.nicovideo.jp/watch/{id}',
            mapping=Mapping(id='/contentId', title='/title', url='', thumbnail='/thumbnailUrl',
                            channel='', duration='/lengthSeconds', views='/viewCounter',
                            published='/startTime')).model_dump()
    if source_id in ('Dailymotion', 'DailymotionSearch'):
        feed = 'https://api.dailymotion.com/videos?sort={sort}&limit={{limit}}&fields=id,title,description,thumbnail_480_url,duration,views_total,owner.screenname,created_time'
        return Connector(kind='json', extractor='Dailymotion',
            pagination=Pagination(mode='page', has_more_path='/has_more'),
            search_url='https://api.dailymotion.com/videos?search={query}&sort=relevance&limit={limit}&fields=id,title,description,thumbnail_480_url,duration,views_total,owner.screenname,created_time',
            home_url='https://api.dailymotion.com/videos?sort=recent&limit={limit}&fields=id,title,description,thumbnail_480_url,duration,views_total,owner.screenname,created_time',
            home_trending_url=feed.format(sort='trending'), home_views_url=feed.format(sort='visited'), home_recent_url=feed.format(sort='recent'),
            video_url='https://www.dailymotion.com/video/{id}',
            mapping=Mapping(url='', thumbnail='/thumbnail_480_url', channel='/owner.screenname', views='/views_total', published='/created_time')).model_dump()
    prefix = SEARCH[source_id][1] if source_id in SEARCH else search_prefixes().get(source_id)
    extractor = source_id
    aliases = {'YoutubeSearch':'Youtube', 'BiliBiliSearch':'BiliBili', 'SoundcloudSearch':'Soundcloud', 'NicovideoSearch':'Niconico', 'NicovideoSearchDate':'Niconico', 'RokfinSearch':'Rokfin', 'PRXStoriesSearch':'PRXStory', 'PRXSeriesSearch':'PRXSeries'}
    extractor = aliases.get(source_id, extractor)
    search_url = ''
    if source_id in URL_SEARCH:
        _, search_url, extractor = URL_SEARCH[source_id]
    config = Connector(kind='ytdlp' if prefix or search_url else 'url', extractor=extractor,
                       prefix=prefix or 'ytsearch', search_url=search_url)
    if source_id == 'VrSquareSearch':
        config.home_query = 'VR'
    if source_id == 'MailRuMusicSearch':
        # The listing entries carry a distinct File id but inherit the search page as webpage_url.
        config.item_url = 'https://my.mail.ru/music/songs/track-{id}'
    if source_id == 'RedGifsSearch':
        browse = 'https://www.redgifs.com/browse?tags={query}&order='
        config.search_url = browse + 'trending'
        config.search_trending_url = browse + 'trending'
        config.search_views_url = browse + 'top'
        config.search_recent_url = browse + 'latest'
    if config.kind == 'ytdlp' and extractor == 'Youtube' and source_id != 'YoutubeMusicSearchURL':
        # A results page for home_query, not a feed published by the platform. Only the
        # view-count filter changes the ordering: the upload-date codes tested (CAISAhAB
        # and CAI%3D) returned the default ranking, so no "recent" ranking is offered.
        results = 'https://www.youtube.com/results?search_query={query}&sp='
        config.home_kind = 'search'
        config.home_views_url = results + 'CAMSAhAB'
        config.search_views_url = results + 'CAMSAhAB'
    return config.model_dump()


# Lucene-style backends read these as syntax; archive.org rejects backslash escapes,
# so the operators are neutralised instead of escaped.
LUCENE_OPERATORS = re.compile(r'[-+&|!(){}\[\]^"~*?:\\/]+')
LUCENE_KEYWORDS = re.compile(r'\b(AND|OR|NOT|TO)\b')


def neutralize_query(query, mode):
    if mode != 'plain':
        return query
    plain = LUCENE_KEYWORDS.sub(lambda found: found.group(0).lower(),
                                LUCENE_OPERATORS.sub(' ', query))
    return ' '.join(plain.split()) or 'video'


def pointer(data, path):
    if path == '':
        return data
    for key in path[1:].split('/'):
        key = key.replace('~1', '/').replace('~0', '~')
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and key.isdigit() and int(key) < len(data):
            data = data[int(key)]
        else:
            return None
    return data


class PublicRedirect(HTTPRedirectHandler):
    def __init__(self, credential=None):
        super().__init__()
        self.credential = credential

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected:
            from app.vault import scoped_headers
            sensitive = {'authorization', 'cookie', 'proxy-authorization'}
            if self.credential:
                sensitive.add(self.credential.get('header', '').lower())
            for name in list(redirected.headers):
                if name.lower() in sensitive:
                    redirected.remove_header(name)
            for name, value in scoped_headers(self.credential, newurl).items():
                redirected.add_header(name, value)
        return redirected


def search_json(config, query, limit, home=False, *, offset=None, credential=None, return_page=False):
    config = Connector.model_validate(config)
    if config.pagination.mode == 'single' and offset:
        return {'items': [], 'native_page': True, 'has_more': False} if return_page else []
    if config.pagination.fixed_page_size:
        size = config.pagination.fixed_page_size
        start = offset or 0
        if start < 0 or not 1 <= limit <= 100:
            raise ValueError('Fenêtre de pagination invalide.')
        # Fetch only provider pages intersecting the requested window. Recursive
        # calls use the provider's size and the ordinary page-number machinery.
        inner = config.model_dump()
        inner['pagination']['fixed_page_size'] = 0
        items, position, more = [], start, False
        while len(items) < limit:
            page_start = position // size * size
            page = search_json(inner, query, size, home, offset=page_start,
                               credential=credential, return_page=True)
            within = position - page_start
            available = page['items'][within:]
            take = min(limit - len(items), len(available))
            items.extend(available[:take])
            more = take < len(available) or page['has_more']
            if len(items) == limit or not page['has_more'] or not take:
                break
            position = page_start + size
        result = {'items': items, 'native_page': True, 'has_more': bool(items and more)}
        return result if return_page else items
    pattern = config.home_url if home and config.home_url else config.search_url
    query = neutralize_query(query, config.query_escape)
    url = pattern.format(query=quote(query, safe=''), limit=limit)
    body = {key: value.format(query=query, limit=limit) if isinstance(value, str) else value for key, value in config.body.items()}
    native = offset is not None and config.pagination.mode != 'prefix'
    if native and config.pagination.mode != 'single':
        value = offset // limit + config.pagination.first_page if config.pagination.mode == 'page' else offset
        if config.method == 'POST':
            body[config.pagination.parameter] = value
        else:
            parts = urlsplit(url)
            # keep_blank_values: a deliberately empty parameter is part of the template.
            params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != config.pagination.parameter]
            url = urlunsplit(parts._replace(query=urlencode(params + [(config.pagination.parameter, value)])))
    public_url(url)
    # DNS and secondary requests are additionally checked by the worker network guard.
    proxy=os.environ.get('ANYTUBE_PROXY')
    from app.vault import scoped_headers
    request_headers = {'Accept': 'application/json', 'User-Agent': 'AnyTube/0.3 (self-hosted media catalog)',
                       **scoped_headers(credential, url)}
    if config.method == 'POST':
        request_headers['Content-Type'] = 'application/json'
    with build_opener(ProxyHandler({'http':proxy,'https':proxy} if proxy else {}), PublicRedirect(credential)).open(Request(url, headers=request_headers,
            data=json.dumps(body).encode() if config.method == 'POST' else None, method=config.method), timeout=12) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('La réponse dépasse 2 Mo.')
    data = json.loads(raw)
    if config.pagination.page_url_path:
        target = pointer(data, config.pagination.page_url_path)
        if not target and pointer(data, config.pagination.initial_results_path) == []:
            return {'items': [], 'native_page': True, 'has_more': False} if return_page else []
        if not isinstance(target, str):
            raise ValueError('Le lien de pagination est absent ou invalide.')
        # The provider supplies a discovery URL, not permission to send credentials
        # elsewhere. Validate it and scope headers again for this exact destination.
        target = public_url(urljoin(url, target))
        parts = urlsplit(target)
        params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                  if k != config.pagination.parameter]
        url = urlunsplit(parts._replace(query=urlencode(params + [
            (config.pagination.parameter, (offset or 0) // limit + 1)])))
        request_headers = {'Accept': 'application/json', 'User-Agent': 'AnyTube/0.3 (self-hosted media catalog)',
                           **scoped_headers(credential, url)}
        with build_opener(ProxyHandler({'http':proxy,'https':proxy} if proxy else {}), PublicRedirect(credential)).open(
                Request(url, headers=request_headers), timeout=12) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('La réponse dépasse 2 Mo.')
        data = json.loads(raw)
    entries = pointer(data, config.results_path)
    total = pointer(data, config.results_total_path) if config.results_total_path else None
    if config.results_total_path:
        if type(total) is not int or total < 0:
            raise ValueError('Le total des résultats doit être un entier positif ou nul.')
        if entries is None and total == 0:
            entries = []
    if not isinstance(entries, list):
        raise ValueError('Le chemin des résultats ne désigne pas une liste JSON.')
    items = []
    for entry in entries[:limit]:
        values = {name: pointer(entry, path) if path else None for name, path in config.mapping.model_dump().items()}
        if not isinstance(values['title'], str) or not values['title'].strip():
            raise ValueError('Le champ titre est absent ou invalide dans les résultats.')
        if config.video_url:
            if not isinstance(values['id'], (str, int)) or isinstance(values['id'], bool):
                raise ValueError('Identifiant vidéo absent ou invalide.')
            url_template = config.video_url
            if config.video_url_boolean_path:
                flag = pointer(entry, config.video_url_boolean_path)
                if type(flag) is not bool:
                    raise ValueError('Le champ de sélection URL doit être booléen.')
                url_template = config.video_url if flag else config.video_url_false
            values['url'] = url_template.format(id=quote(str(values['id']), safe=''))
        if not isinstance(values['url'], str):
            raise ValueError('Le champ URL vidéo est absent ou invalide.')
        if config.result_base_url or values['url'].startswith('/'):
            values['url'] = urljoin(config.result_base_url or url, values['url'])
        public_url(values['url'])
        if isinstance(values['thumbnail'], str) and values['thumbnail'].startswith('/'):
            values['thumbnail'] = urljoin(url, values['thumbnail'])
        if config.thumbnail_url:
            if not isinstance(values['id'], (str, int)) or isinstance(values['id'], bool):
                raise ValueError('Identifiant requis pour la vignette.')
            values['thumbnail'] = config.thumbnail_url.format(id=quote(str(values['id']), safe=''))
        if isinstance(values['thumbnail'], str) and config.thumbnail_substitutions:
            for key, value in config.thumbnail_substitutions.items():
                values['thumbnail'] = values['thumbnail'].replace(key, value)
            public_url(values['thumbnail'])
        for field in ('duration', 'views'):
            value = values[field]
            try:
                values[field] = float(value) if value is not None else None
                if values[field] is not None and (not math.isfinite(values[field]) or values[field] < 0):
                    values[field] = None
            except (ValueError, TypeError):
                values[field] = None
        if values['duration'] is not None and config.duration_unit == 'milliseconds':
            values['duration'] /= 1000
        items.append({'id': str(values['id'] or ''), 'title': values['title'][:500], 'webpage_url': values['url'],
            'thumbnail': values['thumbnail'] if isinstance(values['thumbnail'], str) else None,
            'description': clean_html(values['description'])[:3000] if isinstance(values['description'], str) else '',
            'uploader': values['channel'][:300] if isinstance(values['channel'], str) else '',
            'duration': values['duration'], 'view_count': values['views'], 'upload_date': values['published']})
    if return_page:
        if config.pagination.mode == 'single':
            return {'items': items, 'native_page': True, 'has_more': False}
        has_more = pointer(data, config.pagination.has_more_path) if config.pagination.has_more_path else len(entries) >= limit
        if total is not None and not config.pagination.has_more_path:
            has_more = (offset or 0) + len(entries) < total
        if config.pagination.has_more_path and type(has_more) is not bool:
            raise ValueError('Le champ de pagination doit être booléen.')
        return {'items': items, 'native_page': native, 'has_more': bool(has_more and items)}
    return items
