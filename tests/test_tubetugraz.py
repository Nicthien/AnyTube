import unittest
from unittest.mock import Mock
from yt_dlp import YoutubeDL
from yt_dlp.utils import ExtractorError
from app.tubetugraz import AnyTubeTuGrazIE


class TubeTuGrazTests(unittest.TestCase):
    def test_envelopes_duration_and_only_published_tracks(self):
        video_id = '5dd8e81e-7c83-4d76-844b-67b2401d8701'
        episode = {'id': video_id, 'mediapackage': {'title': 'Lecture', 'duration': 12500,
                   'media': {'track': [{'id': 'track', 'type': 'presentation/delivery',
                   'url': 'https://tube.tugraz.at/static/track.mp4',
                   'video': {'resolution': '1280x720'}}]}}}
        for envelope in [{'result': [episode]}, {'search-results': {'result': episode}}]:
            ie = AnyTubeTuGrazIE(YoutubeDL({'quiet': True}))
            ie._download_json = Mock(return_value=envelope)
            ie._extract_m3u8_formats = Mock(side_effect=AssertionError('No guessed HLS request'))
            ie._extract_mpd_formats = Mock(side_effect=AssertionError('No guessed DASH request'))
            result = ie._real_extract('https://tube.tugraz.at/portal/watch/' + video_id)
            self.assertEqual(result['duration'], 12.5)
            self.assertEqual(result['formats'][0]['height'], 720)
            self.assertEqual(len(result['formats']), 1)
            ie._download_json.assert_called_once()

    def test_missing_episode_is_not_replaced_with_another_video(self):
        ie = AnyTubeTuGrazIE(YoutubeDL({'quiet': True}))
        ie._download_json = Mock(return_value={'result': [{'id': 'other'}]})
        with self.assertRaises(ExtractorError):
            ie._real_extract('https://tube.tugraz.at/portal/watch/5dd8e81e-7c83-4d76-844b-67b2401d8701')
