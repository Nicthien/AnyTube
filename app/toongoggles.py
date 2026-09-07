"""Modern ToonGoggles episode pages using their public embedded player."""
import re
from urllib.parse import urljoin
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import extract_attributes


class AnyTubeToonGogglesEpisodeIE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?toongoggles\.com/shows/(?P<id>[a-zA-Z0-9-]+)/season/\d+/episode/\d+(?:[/?#]|$)'

    def _real_extract(self, url):
        display_id = self._match_id(url)
        webpage = self._download_webpage(url, display_id)
        video_id = self._search_regex(r'\bdata-ottera-id=["\x27](\d+)', webpage, 'player ID')
        player = self._download_webpage(
            'https://api.toongoggles.com/embeddedVideoPlayer', video_id,
            query={'version': '11.0', 'device_type': 'desktop', 'platform': 'web',
                   'partner': 'internal', 'language': 'en', 'connection': 'wifi',
                   'id': video_id, 'div_id': 'video_player', 'content_page_url': url,
                   'image_width': '1280', 'mute': 'false'})
        manifest = self._search_regex(
            r'playerSources\.hls\s*=\s*\[\s*\{\s*url:\s*["\x27](https://[^"\x27]+)',
            player, 'public HLS source')
        formats, subtitles = self._extract_m3u8_formats_and_subtitles(manifest, video_id, 'mp4')
        return {'id': video_id, 'title': self._og_search_title(webpage),
                'thumbnail': self._og_search_thumbnail(webpage),
                'description': self._og_search_description(webpage),
                'formats': formats, 'subtitles': subtitles}


def register_episode(ydl, target, extractor_key=None):
    if AnyTubeToonGogglesEpisodeIE.suitable(target):
        ydl.add_info_extractor(AnyTubeToonGogglesEpisodeIE())
        return AnyTubeToonGogglesEpisodeIE.ie_key()
    return extractor_key


class AnyTubeToonGogglesShowIE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?toongoggles\.com/shows/(?P<id>[a-zA-Z][a-zA-Z0-9-]*)/?(?:[?#]|$)'

    def _real_extract(self, url):
        show = self._match_id(url)
        webpage = self._download_webpage(url, show)
        entries, seen = [], set()
        for anchor in re.findall(r'<a\b[^>]*>', webpage):
            attributes = extract_attributes(anchor)
            path = attributes.get('href', '')
            if not re.fullmatch(r'/shows/' + re.escape(show) + r'/season/\d+/episode/\d+/?', path):
                continue
            target = urljoin('https://www.toongoggles.com', path).rstrip('/')
            if target in seen:
                continue
            seen.add(target)
            entries.append(self.url_result(target, AnyTubeToonGogglesEpisodeIE,
                video_id=attributes.get('data-ottera-id'), video_title=attributes.get('title')))
        return self.playlist_result(entries, show, self._og_search_title(webpage))
