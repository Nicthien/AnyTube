"""Short-lived cursors bound to the account, query and connector revision."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from fastapi import HTTPException
from app.store import connect,owner

MAX_RESULTS=100


def secret():
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO settings VALUES ('cursor_secret',?)",(secrets.token_hex(32),))
        return db.execute("SELECT value FROM settings WHERE key='cursor_secret'").fetchone()['value'].encode()


def signature(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def encode(offset,context):
    raw=json.dumps({'offset':offset,'context':signature([owner(),context]),'expires':time.time()+900},separators=(',',':')).encode()
    token=base64.urlsafe_b64encode(raw).decode().rstrip('=')
    return token+'.'+hmac.new(secret(),raw,hashlib.sha256).hexdigest()


def decode(token,context):
    if not token:return 0
    try:
        encoded,mac=token.split('.')
        raw=base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4))
        if not hmac.compare_digest(mac,hmac.new(secret(),raw,hashlib.sha256).hexdigest()):raise ValueError()
        payload=json.loads(raw)
        if payload['expires']<time.time() or payload['context']!=signature([owner(),context]):raise ValueError()
        offset=payload['offset']
        if type(offset)!=int or not 0<=offset<10000000:raise ValueError()
        return offset
    except (ValueError,KeyError,TypeError):
        raise HTTPException(400,'Pagination expirée ou filtres modifiés. Relancez la recherche.')


def capabilities(config):
    from app.adapters import native_pagination
    from urllib.parse import urlsplit
    kind=config['kind']
    dm=kind=='json' and urlsplit(config.get('search_url','')).hostname=='api.dailymotion.com'
    yt=kind=='ytdlp' and config.get('prefix')=='ytsearch' and not config.get('search_url')
    # Legacy Dailymotion/YouTube rankings stay inferred so sources saved before the
    # declarative fields existed keep the exact same capabilities.
    legacy=['views','recent','trending'] if dm else ['views'] if yt else []
    return {'search':kind!='url','pagination':kind!='url' and config.get('pagination',{}).get('mode')!='single',
            'pagination_mode': 'native' if native_pagination(config) else 'prefix',
            'max_results':(config.get('pagination',{}).get('maximum_results') or None) if native_pagination(config) else MAX_RESULTS,
            'search_rankings':['default']+[r for r in ('views','recent','trending') if r in legacy or config.get(f'search_{r}_url')],
            'duration':dm,'date':dm,
            'home_rankings':['default']+[r for r in ('trending','views','recent') if config.get(f'home_{r}_url') or dm or (yt and r=='views')],
            'home_kind':config.get('home_kind','feed') if config.get('home_url') else 'search'}


def search_config(config,ranking,duration,days):
    from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
    config=dict(config)
    caps=capabilities(config)
    if ranking not in caps['search_rankings'] or (duration!='any' and not caps['duration']) or (days and not caps['date']):
        raise HTTPException(400,'Ce filtre n’est pas disponible pour une source sélectionnée.')
    declared=config.get(f'search_{ranking}_url','') if ranking!='default' else ''
    if declared:
        config['search_url']=declared
    if caps['duration']:
        parts=urlsplit(config['search_url']);params=dict(parse_qsl(parts.query,keep_blank_values=True))
        if ranking!='default' and not declared:params['sort']={'views':'visited','recent':'recent','trending':'trending'}[ranking]
        if duration=='short':params['shorter_than']='4'
        if duration=='long':params['longer_than']='20'
        if days:params['created_after']=str(int(time.time()-days*86400))
        config['search_url']=urlunsplit(parts._replace(query=urlencode(params,safe='{}')))
    elif ranking=='views' and not declared:
        config['search_url']='https://www.youtube.com/results?search_query={query}&sp=CAMSAhAB'
    return config
