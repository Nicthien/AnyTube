"""Bounded declarative HTML searches. No expressions or generated scripts."""
import re
import json
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
    attribute: Literal['text', 'href', 'src', 'data-src', 'title', 'content', 'datetime', 'aria-label', 'alt', 'mmeta', 'vrhm'] = 'text'
    path: Literal['', '/murl', '/turl', '/vt', '/du'] = ''

    @model_validator(mode='after')
    def check(self):
        selector(self.selector)
        if bool(self.path) != (self.attribute in ('mmeta','vrhm')):
            raise ValueError('Un chemin structuré est requis uniquement pour les métadonnées vidéo.')
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
        if self.link.attribute != 'href' and not (self.link.attribute=='mmeta' and self.link.path=='/murl'):
            raise ValueError('Le lien vidéo doit lire href ou la destination des métadonnées vidéo.')
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
    if field.path:
        if len(value)>16000:
            raise ValueError('Métadonnées vidéo trop volumineuses.')
        try:
            value=json.loads(value).get(field.path[1:],'')
        except (ValueError,AttributeError):
            raise ValueError('Métadonnées vidéo invalides.')
        if not isinstance(value,str):
            raise ValueError('Champ de métadonnées vidéo invalide.')
    return str(value).strip()[:3000]


def search_destination(url, pattern):
    """A related query is not a video, even when the listing embeds a player."""
    destination=urlsplit(url)
    origin=urlsplit(pattern)
    path_pattern=re.escape(origin.path.rstrip('/')).replace(re.escape('{query}'), '[^/]*')
    return (destination.hostname==origin.hostname and
            re.fullmatch(path_pattern,destination.path.rstrip('/')) is not None)


def bing_card_evidence(node, base, url, title):
    if urlsplit(base).hostname not in ('www.bing.com','bing.com') or urlsplit(base).path!='/videos/search':
        return None
    try:
        meta=json.loads(node.get('mmeta','{}'))
        details=node.select_one('[vrhm]')
        detail=json.loads(details.get('vrhm','{}')) if details else {}
        if (re.fullmatch(r'[0-9A-Fa-f]{20,80}',meta.get('mid','')) and
            meta['mid']==detail.get('mid') and clean_url(base,meta.get('murl'))==url and
            clean_url(base,detail.get('murl'))==url and detail.get('vt','').strip()==title and
            urlsplit(url).hostname not in ('www.bing.com','bing.com')):
            return {'method':'bing_video_card','url':url,'media_id':meta['mid'],'title':title}
    except (ValueError,TypeError,KeyError,AttributeError):
        pass
    return None


def video_page_evidence(text, base):
    soup=document(text)
    values=[n.get('src') for n in soup.select('video[src], video source[src]')]
    values.extend(n.get('content') for n in soup.select('meta[property="og:video"],meta[property="og:video:url"],meta[property="og:video:secure_url"]'))
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            pending=[json.loads(script.get_text())]
            for _ in range(500):
                if not pending:break
                item=pending.pop()
                if isinstance(item,list):pending.extend(item[:100])
                elif isinstance(item,dict):
                    types=item.get('@type',[])
                    if types=='VideoObject' or isinstance(types,list) and 'VideoObject' in types:
                        values.extend([item.get('contentUrl'),item.get('embedUrl')])
                    pending.extend(v for v in item.values() if isinstance(v,(dict,list)))
        except ValueError:
            continue
    for value in values:
        if isinstance(value,str) and value.strip():
            try:
                clean_url(base,value)
                return True
            except ValueError:
                pass
    return False


def extract(text, base, config):
    spec = HtmlSpec.model_validate(config['html'])
    soup = document(text)
    items, seen = [], set()
    nodes=soup.select(spec.items,limit=101)
    for index,node in enumerate(nodes):
        title, link = read_field(node, spec.title), read_field(node, spec.link)
        if not title or not link:
            from app.source_diagnostics import ControlError,emit
            emit(selected_count=len(nodes),inspected_count=index+1,valid_count=len(items),card_index=index+1,missing_field='title' if not title else 'link',selector=(spec.title if not title else spec.link).selector,outcome='failed',code='missing_fields')
            raise ControlError('missing_fields',f'Carte {index+1} : champ {"titre" if not title else "lien"} absent.',True)
        if spec.url_path_prefix and not urlsplit(urljoin(base,link)).path.startswith(spec.url_path_prefix):
            continue
        url = clean_url(base, link)
        if search_destination(url,config['search_url']):
            raise ValueError('Les résultats pointent vers des recherches associées, pas vers des vidéos.')
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
                      'duration':duration(read_field(node,spec.duration),config.get('duration_unit')),
                      '_listing_evidence':bing_card_evidence(node,base,url,title)})
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


def card_links(node, base, search_url, examples=()):
    """Recognize card destinations from their structure, not a URL-prefix catalogue."""
    found = set()
    for anchor in node.select('a[href]', limit=40):
        href = anchor.get('href', '')
        url = urljoin(base, href)
        if not href or href.startswith(('#', 'javascript:', 'mailto:')) or search_destination(url, search_url):
            continue
        if urlsplit(url).hostname != urlsplit(base).hostname:
            continue
        # Association with an image/heading or media metadata is stronger than a
        # path shape. Multiple competing destinations remain ambiguous.
        associated = anchor.select_one('img,video,picture,h2,h3,[itemprop="thumbnailUrl"]') is not None
        heading = anchor.find_parent(['h2', 'h3']) is not None
        media_card = node.select_one('img,video,picture,[itemprop="duration"]') is not None
        same_image = any(urljoin(base, a.get('href', '')) == url for a in node.select('a:has(img),a:has(picture)'))
        if url in examples or associated or heading or (media_card and same_image):
            found.add(url)
    return found


def card_fields(nodes, base, search_url, examples=()):
    """Infer one consistent mapping, with an unambiguous destination per card."""
    def links(node):
        return card_links(node, base, search_url, examples)
    if not nodes or any(len(links(n))!=1 for n in nodes):return None
    options=[]
    for node in nodes[:5]:
        for tag in node.select('a[href], h2, h3, img',limit=40):
            classes=[c for c in tag.get('class',[]) if re.fullmatch(r'[A-Za-z_][\w-]*',c)]
            css=tag.name+(''.join('.'+c for c in classes[:3]))
            previous=tag.find_previous_sibling()
            parent_classes=[c for c in tag.parent.get('class',[]) if re.fullmatch(r'[A-Za-z_][\w-]*',c)]
            if tag.parent is not node and parent_classes:css=tag.parent.name+''.join('.'+c for c in parent_classes[:3])+' '+css
            elif previous is not None and not classes:css=previous.name+' + '+css
            for attr in ('text','title','aria-label','alt'):
                if attr=='alt' and tag.name!='img':continue
                if attr=='text' and tag.name=='img':continue
                spec={'selector':css+(f'[{attr}]' if attr!='text' else ''),'attribute':attr}
                if spec not in options:options.append(spec)
    link_options=['h2 a[href]','h3 a[href]','a[href]']
    for option in options:
        for link_css in link_options:
            valid=True
            for node in nodes:
                expected=next(iter(links(node)))
                title_node=node.select_one(option['selector'])
                link_node=node.select_one(link_css)
                if title_node is None or link_node is None or urljoin(base,link_node['href'])!=expected:
                    valid=False;break
                anchor=title_node if title_node.name=='a' else title_node.find_parent('a')
                if anchor and urljoin(base,anchor.get('href',''))!=expected:
                    valid=False;break
                if not read_field(node,HtmlField.model_validate(option)):
                    valid=False;break
            if valid:return option,{'selector':link_css,'attribute':'href'}
    return None


def infer(text, base, search_url, examples=(), rendering='http'):
    """Rank repeated cards using video semantics or multiple example links."""
    from app.connectors import Connector
    from app.search_response import require_usable
    require_usable(text,base)
    soup = document(text)
    if urlsplit(base).hostname in ('www.bing.com','bing.com') and soup.select_one('div.mc_vtvc[mmeta]'):
        candidate=Connector(kind='html',search_url=search_url,pagination={'mode':'single'},html={
            'rendering':rendering,'items':'div.mc_vtvc[mmeta]',
            'title':{'selector':'[vrhm]','attribute':'vrhm','path':'/vt'},
            'link':{'attribute':'mmeta','path':'/murl'},
            'thumbnail':{'attribute':'mmeta','path':'/turl'},
            'duration':{'selector':'[vrhm]','attribute':'vrhm','path':'/du'}}).model_dump()
        try:
            entries,_=extract(text,base,candidate)
            if entries and all(e['_listing_evidence'] for e in entries):
                return [candidate]
        except ValueError:
            pass
    groups = {}
    examples = {clean_url(base,u) for u in examples if urlsplit(u).hostname == urlsplit(base).hostname}
    for anchor in soup.select('a[href]', limit=500):
        href = anchor.get('href','')
        url = urljoin(base, href)
        if search_destination(url,search_url):
            continue
        if urlsplit(url).hostname != urlsplit(base).hostname:
            continue
        card=anchor.find_parent(['article','li'])
        parents=[card] if card is not None else anchor.find_parents('div',limit=3)
        for parent in parents:
            if url not in card_links(parent, base, search_url, examples):
                continue
            classes = [c for c in parent.get('class',[]) if re.fullmatch(r'[A-Za-z_][\w-]*',c)]
            css = parent.name + ('.'+'.'.join(classes[:3]) if classes else '')
            groups.setdefault(css, set()).add(url)
    ranked = sorted(groups, key=lambda css:(len(groups[css]&examples),len(groups[css])), reverse=True)
    result = []
    for css in ranked[:3]:
        if len(groups[css]) < 2:
            continue
        nodes=soup.select(css,limit=101)
        first = nodes[0]
        link_selector = 'a[href]'
        if first.select_one('h2 a[href], h3 a[href]'):
            link_selector = 'h2 a[href], h3 a[href]'
        spec = {'rendering':rendering,'items':css,'title':{'selector':link_selector},
                'link':{'selector':link_selector,'attribute':'href'}}
        fields=card_fields(nodes,base,search_url,examples)
        if fields:
            spec['title'],spec['link']=fields
        else:
            from app.source_diagnostics import emit
            emit(outcome='inconclusive',code='ambiguous_cards',selected_count=len(nodes),selector=css,
                 message='Association titre et destination ambiguë dans les cartes sélectionnées.')
            continue
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
    from app.source_assistant import http, runtime_settings, service_headers
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
            service = runtime_settings().browser
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
        from app.search_response import require_usable
        require_usable(text,final,response.get('status'),response.get('content_type','text/html'))
        entries, next_url = extract(text,final,config)
        from app.source_diagnostics import emit
        emit(requested_url=url,final_url=final,http_status=response.get('status'),content_type=response.get('content_type','text/html'),selected_count=len(document(text).select(spec['items'],limit=101)),valid_count=len(entries),outcome='observed')
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
        if (payload.get('_discovery_diagnostics') and offset==0) or len(collected)>=offset+size or not next_url:
            break
        url=next_url
    return {'items':[normalize(i) for i in collected[offset:offset+size]],'native_page':True,
            'listing_evidence':{i['url']:i['_listing_evidence'] for i in collected[offset:offset+size] if i.get('_listing_evidence')},
            'has_more':offset+size < min(100,len(collected)) or (more and offset+size<100),
            'page_urls':list(visited),'source_page_size':first_count}
