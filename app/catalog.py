from functools import lru_cache
import json
from pathlib import Path
from yt_dlp.extractor import gen_extractor_classes

SEARCH = {
    'Youtube': ('YouTube', 'ytsearch'),
    'Dailymotion': ('Dailymotion', 'dailymotion'),
    'BiliBili': ('Bilibili', 'bilisearch'),
    'Soundcloud': ('SoundCloud', 'scsearch'),
    'Niconico': ('Niconico', 'nicosearch'),
    'GoogleSearch': ('Google Vidéos', 'gvsearch'),
    'YahooSearch': ('Yahoo Vidéos', 'yvsearch'),
    'Rokfin': ('Rokfin', 'rkfnsearch'),
    'PRXStory': ('PRX · podcasts', 'prxstories'),
    'PRXSeries': ('PRX · séries', 'prxseries'),
}

# Search pages explicitly implemented by the installed yt-dlp extractors.
URL_SEARCH = {
    'YoutubeMusicSearchURL': ('YouTube Music', 'https://music.youtube.com/search?q={query}', 'Youtube'),
    'YoutubeSearchURL': ('YouTube · recherche avancée', 'https://www.youtube.com/results?search_query={query}&sp=EgIQAfABAQ%3D%3D', 'Youtube'),
    'GameJolt': ('Game Jolt', 'https://gamejolt.com/search?q={query}', 'GameJolt'),
    'GameJoltSearch': ('Game Jolt · recherche', 'https://gamejolt.com/search?q={query}', 'GameJolt'),
    'MailRuMusicSearch': ('Mail.ru · musique', 'https://my.mail.ru/music/search/{query}', 'MailRuMusic'),
    'NicovideoSearchURL': ('Niconico · recherche avancée', 'https://www.nicovideo.jp/search/{query}', 'Niconico'),
    'RedGifsSearch': ('RedGifs · recherche', 'https://www.redgifs.com/browse?tags={query}', 'RedGifs'),
    'VrSquareSearch': ('VR Square · recherche', 'https://livr.jp/web-search?w={query}', 'VrSquare'),
}


@lru_cache(maxsize=1)
def search_prefixes():
    # Resolve real classes: lazy classes do not expose SearchInfoExtractor ancestry.
    from yt_dlp.extractor.common import SearchInfoExtractor
    found = {}
    for cls in gen_extractor_classes():
        real = cls.real_class if 'real_class' in dir(cls) else cls
        if issubclass(real, SearchInfoExtractor) and real._SEARCH_KEY:
            found[cls.ie_key()] = real._SEARCH_KEY
    return found


@lru_cache(maxsize=1)
def catalog():
    from app.registry import identities
    from yt_dlp.version import __version__
    try:
        checks = json.loads(Path(__file__).with_name('template_checks.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        checks = {}
    items = {cls.ie_key(): {'id': cls.ie_key(), 'name': cls.IE_NAME, 'search': False}
             for cls in gen_extractor_classes() if cls.ie_key() != 'Generic'}
    for key, (name, _) in SEARCH.items():
        if key in items:
            items[key].update(name=name, search=True)
    for key in search_prefixes():
        if key in items:
            items[key]['search'] = True
    for key, (name, _, _) in URL_SEARCH.items():
        if key in items:
            items[key].update(name=name, search=True)
    if 'DailymotionSearch' in items:
        items['DailymotionSearch']['search'] = True
    for item in items.values():
        item.update(identities()[item['id']])
        if item['id'] == 'ArchiveOrg':
            item.update(name='Internet Archive · vidéos', search=True)
        if item['id'] in ('PeerTube','PeerTubePlaylist'):
            item.update(name='PeerTube · Framatube' + (' · collections' if item['id']=='PeerTubePlaylist' else ''),search=True)
        if item['id'] == 'Vimeo':
            item.update(name='Vimeo',search=True,access_requirement='api_token')
        item['template_status'] = 'search' if item['search'] else 'url_only'
        if checks.get('yt_dlp') == __version__ and item['id'] in checks.get('entries', {}):
            item['last_check'] = {**checks['entries'][item['id']], 'date': checks['generated_at']}
    return sorted(items.values(), key=lambda item: (not item['search'], item['name'].casefold()))
