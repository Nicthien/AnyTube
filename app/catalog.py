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

# Reviewed display names and access notes for templates covered by an audited batch.
REVIEWED = {
    'ArchiveOrg': {'name': 'Internet Archive · vidéos'},
    'GameJolt': {'name': 'Game Jolt · publications'},
    'GameJoltSearch': {'name': 'Game Jolt · recherche de publications'},
    'GoogleSearch': {'name': 'Google Vidéos'},
    'MailRuMusicSearch': {'name': 'Mail.ru · musique'},
    'Niconico': {'name': 'Niconico'},
    'NicovideoSearch': {'name': 'Niconico · recherche'},
    'NicovideoSearchDate': {'name': 'Niconico · recherche par date'},
    'NicovideoSearchURL': {'name': 'Niconico · recherche avancée'},
    'PRXSeries': {'name': 'PRX · séries', 'access_requirement': 'account'},
    'PRXSeriesSearch': {'name': 'PRX · recherche de séries', 'access_requirement': 'account'},
    'PRXStoriesSearch': {'name': 'PRX · recherche de podcasts', 'access_requirement': 'account'},
    'PRXStory': {'name': 'PRX · podcasts', 'access_requirement': 'account'},
    'RedGifsSearch': {'name': 'RedGifs · recherche'},
    'Rokfin': {'name': 'Rokfin'},
    'RokfinSearch': {'name': 'Rokfin · recherche'},
    'Soundcloud': {'name': 'SoundCloud'},
    'SoundcloudSearch': {'name': 'SoundCloud · recherche'},
    'Vimeo': {'name': 'Vimeo', 'access_requirement': 'api_token'},
    'VrSquareSearch': {'name': 'VR SQUARE · recherche'},
    'YahooSearch': {'name': 'Yahoo Vidéos'},
    'Youtube': {'name': 'YouTube'},
    'YoutubeMusicSearchURL': {'name': 'YouTube Music'},
    'YoutubeSearch': {'name': 'YouTube · recherche'},
    'YoutubeSearchURL': {'name': 'YouTube · recherche avancée'},
}

# Facts established by a reviewed batch, shown next to the template so a reader is not
# left guessing why a template answers nothing. Never a substitute for a dated trial.
LIMITATIONS = {
    'GoogleSearch': 'L’extracteur installé lit le HTML de google.com ; le repère qu’il cherche a disparu et aucun résultat n’est renvoyé. Aucune interface publique sans clé ne le remplace.',
    'YahooSearch': 'L’extracteur installé appelle une API JSON de Yahoo Vidéos qui ne répond plus en JSON. Aucune interface publique sans clé ne la remplace.',
    'Rokfin': 'L’extracteur installé récupère ses identifiants de recherche dans les scripts de rokfin.com ; ces scripts ont changé d’emplacement et la recherche échoue.',
    'RokfinSearch': 'L’extracteur installé récupère ses identifiants de recherche dans les scripts de rokfin.com ; ces scripts ont changé d’emplacement et la recherche échoue.',
    'VrSquareSearch': 'La recherche répond, mais VR SQUARE ne diffuse ces vidéos que dans son application : elles ne sont pas lisibles ici.',
    'PRXStory': 'L’API PRX exige un jeton de compte. Déposez-le dans le coffre puis rattachez-le à la source.',
    'PRXSeries': 'L’API PRX exige un jeton de compte. Déposez-le dans le coffre puis rattachez-le à la source.',
    'PRXStoriesSearch': 'L’API PRX exige un jeton de compte. Déposez-le dans le coffre puis rattachez-le à la source.',
    'PRXSeriesSearch': 'L’API PRX exige un jeton de compte. Déposez-le dans le coffre puis rattachez-le à la source.',
    'Vimeo': 'L’API Vimeo exige un jeton d’accès. Déposez-le dans le coffre puis rattachez-le à la source.',
    'BiliBili': 'Bilibili refuse par intermittence les recherches répétées (HTTP 412). Réessayez plus tard ; ce refus n’est pas définitif.',
    'BiliBiliSearch': 'Bilibili refuse par intermittence les recherches répétées (HTTP 412). Réessayez plus tard ; ce refus n’est pas définitif.',
    'GameJolt': 'La recherche liste des publications de la communauté ; certaines ne contiennent aucun média lisible.',
    'GameJoltSearch': 'La recherche liste des publications de la communauté ; certaines ne contiennent aucun média lisible.',
    'PeerTubePlaylist': 'Ce modèle sert aujourd’hui la recherche vidéo de PeerTube ; la recherche de listes de lecture reste à développer.',
    'MailRuMusicSearch': 'Mail.ru Musique ne diffuse que de l’audio ; la lecture depuis cette source n’a pas été essayée.',
}

# Self-hosted software: the same API answers on every instance, so one template covers many
# hosts. The chosen host is fixed inside the saved connector, never taken from a search query.
INSTANCE_SOFTWARE = {
    'PeerTube': {'software': 'PeerTube', 'default_instance': 'framatube.org',
                 'probe_url': 'https://{host}/videos/watch/{uuid}'},
    'PeerTubePlaylist': {'software': 'PeerTube', 'default_instance': 'framatube.org',
                         'probe_url': 'https://{host}/videos/watch/{uuid}'},
}
# A well-formed identifier of the right shape, used only to ask the installed extractor
# whether it recognises a host. Never fetched.
PROBE_UUID = '00000000-0000-4000-8000-000000000000'


def playback_supported(source_id, host):
    """yt-dlp only knows a fixed list of instances; search can work where playback cannot."""
    from yt_dlp.extractor import gen_extractor_classes
    entry = INSTANCE_SOFTWARE.get(source_id)
    if not entry or not host:
        return None
    target = entry['probe_url'].format(host=host, uuid=PROBE_UUID)
    return any(cls.ie_key() != 'Generic' and cls.suitable(target) for cls in gen_extractor_classes())

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
        if item['id'] in REVIEWED:
            item.update(REVIEWED[item['id']], search=True)
        if item['id'] in ('PeerTube','PeerTubePlaylist'):
            item.update(name='PeerTube · Framatube' + (' · collections' if item['id']=='PeerTubePlaylist' else ''),search=True)
        if item['id'] in LIMITATIONS:
            item['limitation'] = LIMITATIONS[item['id']]
        if item['id'] in INSTANCE_SOFTWARE:
            item['instance_software'] = INSTANCE_SOFTWARE[item['id']]['software']
            item['default_instance'] = INSTANCE_SOFTWARE[item['id']]['default_instance']
        item['template_status'] = 'search' if item['search'] else 'url_only'
        if checks.get('yt_dlp') == __version__ and item['id'] in checks.get('entries', {}):
            # A batch may re-probe part of the catalogue; an entry keeps its own date when it has one.
            item['last_check'] = {'date': checks['generated_at'], **checks['entries'][item['id']]}
    return sorted(items.values(), key=lambda item: (not item['search'], item['name'].casefold()))
