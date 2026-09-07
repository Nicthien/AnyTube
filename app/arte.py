"""Retain collection metadata discarded by the upstream flat mini-series listing."""
from yt_dlp.extractor.arte import ArteTVPlaylistIE
from yt_dlp.utils import unified_strdate


class AnyTubeArteTVPlaylistIE(ArteTVPlaylistIE):
    def _download_json(self, *args, **kwargs):
        data = super()._download_json(*args, **kwargs)
        if isinstance(data, dict):
            for program in data.get('programs') or []:
                for video in program.get('videos') or []:
                    if isinstance(video.get('url'), str):
                        self._listing_metadata[video['url']] = video
        return data

    def _real_extract(self, url):
        self._listing_metadata = {}
        result = super()._real_extract(url)
        entries = result['entries']
        def enriched():
            for entry in entries:
                details = self._listing_metadata.get(entry.get('url'), {})
                if details and not entry.get('title'):
                    title = ' — '.join(part for part in (details.get('title'), details.get('subtitle')) if isinstance(part, str) and part)
                    entry = {**entry, 'id': details.get('programId'), 'title': title,
                             'description': details.get('shortDescription'),
                             'duration': details.get('durationSeconds'),
                             'upload_date': unified_strdate(details.get('firstBroadcastDate')),
                             'thumbnail': (details.get('mainImage') or {}).get('url')}
                yield entry
        result['entries'] = enriched()
        return result
