"""Preserve metadata already supplied by Microsoft's collection API."""
from urllib.parse import urljoin

from yt_dlp.extractor.microsoftembed import MicrosoftLearnPlaylistIE


class AnyTubeMicrosoftLearnPlaylistIE(MicrosoftLearnPlaylistIE):
    def _entries(self, url_base, video_id):
        skip = 0
        while True:
            data = self._download_json(url_base, video_id, query={'locale': 'en-us', '$skip': skip})
            entries = data.get('results') or []
            if not entries:
                break
            for entry in entries:
                path = entry.get('url')
                if not isinstance(path, str) or not path.startswith('/') or path.startswith('//'):
                    continue
                duration = entry.get('duration_in_milliseconds')
                yield self.url_result(
                    urljoin('https://learn.microsoft.com/en-us/', '/en-us' + path),
                    video_id=entry.get('entry_id') or entry.get('uid'),
                    video_title=entry.get('title'),
                    thumbnail=entry.get('image_url'),
                    duration=duration / 1000 if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0 else None,
                    upload_date=entry.get('upload_date'),
                )
            skip += len(entries)
            if skip >= data.get('count', 0):
                break
