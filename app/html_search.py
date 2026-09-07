"""Bounded declarative HTML searches. No expressions or generated scripts."""
import re
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode, quote
from bs4 import BeautifulSoup
import soupsieve
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal


def selector(value):
    if len(value) > 200 or any(c in value for c in (':', '\\')):
        raise ValueError('Sélecteur CSS trop complexe (pseudo-classes interdites).')
    if value:
        try:
            soupsieve.compile(value)
        except soupsieve.SelectorSyntaxError:
            raise ValueError('Sélecteur CSS invalide.')
    return value


class HtmlField(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selector: str = ''
    attribute: Literal['text', 'href', 'src', 'data-src', 'title', 'content', 'datetime', 'aria-label'] = 'text'

    @model_validator(mode='after')
    def check(self):
        selector(self.selector)
        return self


class HtmlSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rendering: Literal['http', 'chromium'] = 'http'
    items: str = Field(default='article', min_length=1)
    title: HtmlField = Field(default_factory=lambda: HtmlField(selector='a'))
    link: HtmlField = Field(default_factory=lambda: HtmlField(selector='a', attribute='href'))
    thumbnail: HtmlField | None = None
    duration: HtmlField | None = None
    description: HtmlField | None = None
    next_selector: str = ''
    url_path_prefix: str = Field(default='',max_length=200,pattern=r'^(?:/[A-Za-z0-9_-]+/)?$')

    @model_validator(mode='after')
    def check(self):
        selector(self.items)
        selector(self.next_selector)
        if self.link.attribute != 'href':
            raise ValueError('Le lien vidéo doit lire href.')
        return self


def document(text):
    if len(text.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('Document HTML supérieur à 2 Mo.')
    soup = BeautifulSoup(text, 'html.parser')
    if len(soup.find_all(True, limit=20001)) > 20000:
        raise ValueError('Document HTML trop complexe.')
    return soup


def clean_url(base, value):
    from app.connectors import public_url
    url = urljoin(base, value or '')
    parts = urlsplit(public_url(url))
    if re.search(r'(?i)[?&](token|key|api_key|access_token|signature)=', url):
        raise ValueError('URL contenant un secret.')
    host = parts.hostname.lower()
    netloc = host if parts.port in (None, 80 if parts.scheme == 'http' else 443) else parts.netloc
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or '/', parts.query, ''))


def duration(value, unit='seconds'):
    from yt_dlp.utils import parse_duration
    try:
        number = float(value)
        return number / (1000 if unit == 'milliseconds' else 1) if 0 <= number < 1e10 else None
    except (ValueError, TypeError):
        return parse_duration(str(value)) if value else None


def read_field(item, field):
    if field is None:
        return ''
    node = item.select_one(field.selector) if field.selector else item
    if node is None:
        return ''
    value = node.get_text(' ', strip=True) if field.attribute == 'text' else node.get(field.attribute, '')
    return str(value).strip()[:3000]


def extract(text, base, config):
    spec = HtmlSpec.model_validate(config['html'])
    soup = document(text)
    items, seen = [], set()
    for node in soup.select(spec.items, limit=101):
        title, link = read_field(node, spec.title), read_field(node, spec.link)
        if link and spec.url_path_prefix and not urlsplit(urljoin(base,link)).path.startswith(spec.url_path_prefix):
            continue
        if not title or not link:
            raise ValueError('Un résultat HTML ne possède pas de titre ou de lien.')
        url = clean_url(base, link)
        if url in seen:
            continue
        seen.add(url)
        thumbnail = read_field(node, spec.thumbnail)
        try:
            thumbnail = clean_url(base, thumbnail) if thumbnail else None
        except ValueError:
            thumbnail = None
        items.append({'id':url, 'title':title, 'url':url, 'thumbnail':thumbnail,
                      'description':read_field(node,spec.description),
                      'duration':duration(read_field(node,spec.duration),config.get('duration_unit'))})
    following = soup.select_one(spec.next_selector) if spec.next_selector else None
    next_url = clean_url(base, following.get('href')) if following and following.get('href') else None
    if next_url and urlsplit(next_url).hostname != urlsplit(base).hostname:
        raise ValueError('Pagination vers un autre domaine refusée.')
    return items[:100], next_url


def template_from_example(url, query):
    clean_url(url, url)
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    if sum(v == query for _, v in pairs) == 1:
        return urlunsplit((parts.scheme,parts.netloc,parts.path,
            urlencode([(k,'{query}' if v == query else v) for k,v in pairs],safe='{}'),''))
    segments = parts.path.split('/')
    if segments.count(quote(query, safe='')) == 1:
        return urlunsplit((parts.scheme,parts.netloc,'/'.join('{query}' if s == quote(query,safe='') else s for s in segments),parts.query,''))
    raise ValueError('Le terme doit apparaître une seule fois dans l’URL de recherche.')


def infer(text, base, search_url, examples=(), rendering='http'):
    """Rank repeated cards using video semantics or multiple example links."""
    from app.connectors import Connector
    soup = document(text)
    groups = {}
    examples = {clean_url(base,u) for u in examples if urlsplit(u).hostname == urlsplit(base).hostname}
    for anchor in soup.select('a[href]', limit=500):
        href = anchor.get('href','')
        url = urljoin(base, href)
        if urlsplit(url).hostname != urlsplit(base).hostname:
            continue
        semantic = bool(re.search(r'(?i)(/videos?/|/watch(?:/|\?)|/w/|[?&]v=)', url))
        if not semantic and url not in examples:
            continue
        parent = anchor.find_parent(['article','li']) or anchor.find_parent('div')
        if parent is None:
            continue
        classes = [c for c in parent.get('class',[]) if re.fullmatch(r'[A-Za-z_][\w-]*',c)]
        css = parent.name + ('.'+'.'.join(classes[:3]) if classes else '')
        groups.setdefault(css, set()).add(url)
    ranked = sorted(groups, key=lambda css:(len(groups[css]&examples),len(groups[css])), reverse=True)
    result = []
    for css in ranked[:3]:
        if len(groups[css]) < 2:
            continue
        first = soup.select_one(css)
        link_selector = 'a[href]'
        if first.select_one('h2 a[href], h3 a[href]'):
            link_selector = 'h2 a[href], h3 a[href]'
        spec = {'rendering':rendering,'items':css,'title':{'selector':link_selector},
                'link':{'selector':link_selector,'attribute':'href'}}
        prefixes={urlsplit(u).path.split('/')[1] for u in groups[css] if len(urlsplit(u).path.split('/'))>2}
        if len(prefixes)==1 and re.fullmatch(r'[A-Za-z0-9_-]+',next(iter(prefixes))):
            spec['url_path_prefix']='/'+next(iter(prefixes))+'/'
        if first.select_one('img'):
            spec['thumbnail']={'selector':'img','attribute':'src'}
        if first.select_one('time'):
            spec['duration']={'selector':'time'}
        next_node = soup.select_one('a[rel="next"], a.next')
        if next_node:
            spec['next_selector']='a[rel="next"], a.next'
        config = Connector(kind='html',search_url=search_url,html=spec,
            pagination={'mode':'page' if next_node else 'single'}).model_dump()
        try:
            entries,_ = extract(text,base,config)
            if len(entries)>=2:
                result.append(config)
        except ValueError:
            continue
    return result[:3]


async def search(payload):
    from app.source_assistant import http, settings, service_headers
    from app.connectors import Connector
    from app.worker import normalize
    from app.failures import SourceFailure
    config = Connector.model_validate(payload['connector']).model_dump()
    spec = config['html']
    size = min(100,max(1,payload.get('page_size',payload.get('limit',8))))
    offset = payload.get('offset',0)
    if not isinstance(offset,int) or offset < 0 or offset >= 100:
        raise ValueError('Pagination HTML limitée à 100 résultats.')
    base = config['search_url'].format(query=quote(payload['query'],safe=''),limit=size)
    url = base
    paging=config['pagination']
    if paging['mode']=='page' and not spec['next_selector']:
        parts=urlsplit(base)
        pairs=[(k,v) for k,v in parse_qsl(parts.query,keep_blank_values=True) if k!=paging['parameter']]
        pairs.append((paging['parameter'],str(paging['first_page'])))
        url=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(pairs),''))
    collected, visited, seen = [], set(), set()
    more = False
    first_count = 0
    for index in range(10):
        if url in visited:
            raise ValueError('La pagination répète une page.')
        visited.add(url)
        if spec['rendering'] == 'chromium':
            service = settings().browser
            if not service.url:
                raise SourceFailure('browser_unavailable')
            try:
                response = await http(service.url.rstrip('/')+'/observe',trusted=True,method='POST',
                    body={'url':url,'query':payload['query'],'submit_search':False},headers=service_headers('browser'),timeout=85)
                import json
                response = json.loads(response['text'])
                text, final = response['html'], response['url']
                from app.source_assistant import metrics
                if metrics.get() is not None:
                    metrics.get()['browser_requests']=metrics.get().get('browser_requests',0)+response.get('requests',0)
            except Exception:
                raise SourceFailure('browser_unavailable')
        else:
            response = await http(url)
            text, final = response['text'], response.get('url',url)
        entries, next_url = extract(text,final,config)
        if index==0:
            first_count=len(entries)
        new = [entry for entry in entries if entry['url'] not in seen]
        if index and entries and not new:
            raise ValueError('La pagination répète les mêmes résultats.')
        collected.extend(new)
        seen.update(entry['url'] for entry in new)
        paging = config['pagination']
        if paging['mode']=='single':
            next_url=None
        elif not spec['next_selector']:
            parts=urlsplit(base)
            pairs=[(k,v) for k,v in parse_qsl(parts.query,keep_blank_values=True) if k!=paging['parameter']]
            pairs.append((paging['parameter'],str(paging['first_page']+index+1)))
            next_url=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(pairs),'')) if entries else None
        more = bool(next_url)
        if len(collected)>=offset+size or not next_url:
            break
        url=next_url
    return {'items':[normalize(i) for i in collected[offset:offset+size]],'native_page':True,
            'has_more':offset+size < min(100,len(collected)) or (more and offset+size<100),
            'page_urls':list(visited),'source_page_size':first_count}
