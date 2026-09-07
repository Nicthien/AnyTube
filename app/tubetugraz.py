"""TU Graz public episode API, current and legacy response envelopes."""
from yt_dlp.extractor.tubetugraz import TubeTuGrazIE
from yt_dlp.utils import ExtractorError, float_or_none, parse_resolution


class AnyTubeTuGrazIE(TubeTuGrazIE):
    def _real_extract(self, url):
        video_id = self._match_id(url)
        data = self._download_json(self._API_EPISODE, video_id, query={'id': video_id, 'limit': 1})
        result = data.get('result', data.get('search-results', {}).get('result', []))
        entries = result if isinstance(result, list) else [result]
        episode = next((e for e in entries if isinstance(e, dict) and
                        (e.get('id') or e.get('mediapackage', {}).get('id')) == video_id), None)
        if not episode:
            raise ExtractorError('Episode absent from the accessible catalogue', expected=True)
        episode = {**episode, 'id': video_id}
        info = self._extract_episode(episode)
        info['duration'] = float_or_none(info.get('duration'), 1000)
        return info

    def _extract_formats(self, tracks, video_id):
        for track in tracks or []:
            url = track.get('url')
            if not isinstance(url, str) or not url.startswith('https://'):
                continue
            transport = (track.get('transport') or 'https').lower()
            kind = track.get('type') or 'unknown'
            if transport == 'hls':
                formats = self._extract_m3u8_formats(url, video_id, 'mp4', fatal=False)
            elif transport == 'dash':
                formats = self._extract_mpd_formats(url, video_id, fatal=False)
            elif transport == 'https':
                formats = [{'url': url, 'format_id': track.get('id'),
                            **parse_resolution((track.get('video') or {}).get('resolution'))}]
            else:
                continue
            yield from self._set_format_type(formats, kind)


def register_episode(ydl, target, extractor_key=None):
    if AnyTubeTuGrazIE.suitable(target):
        ydl.add_info_extractor(AnyTubeTuGrazIE())
        return AnyTubeTuGrazIE.ie_key()
    return extractor_key
