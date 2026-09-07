import unittest
from unittest.mock import Mock

from app.patreon import AnyTubePatreonCampaignIE
from app.worker import normalize


class PatreonCollectionTests(unittest.TestCase):
    def test_explicit_non_media_and_access_flags_are_preserved(self):
        extractor = AnyTubePatreonCampaignIE()
        extractor._call_api = Mock(return_value={'data': [
            {'id': '1', 'attributes': {'url': '/posts/1', 'post_type': 'text_only',
                                      'current_user_can_view': True}},
            {'id': '2', 'attributes': {'url': '/posts/2', 'post_type': 'video_embed',
                                      'current_user_can_view': False}},
            {'id': '3', 'attributes': {'url': '/posts/3', 'post_type': 'video_embed',
                                      'current_user_can_view': True}},
        ]})
        items = [normalize(item) for item in extractor._entries('42')]
        self.assertEqual([(x['non_media'], x['access_required']) for x in items],
                         [(True, False), (False, True), (False, False)])

    def test_metadata_cursor_and_external_url_rejection(self):
        extractor = AnyTubePatreonCampaignIE()
        extractor._call_api = Mock(side_effect=[
            {'data': [
                {'id': '12', 'attributes': {'url': '/creator/posts/example-12',
                 'title': 'Example', 'published_at': '2026-09-01T12:00:00Z'}},
                {'attributes': {'url': 'https://other.example/post'}},
            ], 'meta': {'pagination': {'cursors': {'next': 'cursor-one'}}}},
            {'data': [], 'meta': {'pagination': {'cursors': {'next': 'cursor-one'}}}},
        ])
        entries = list(extractor._entries('42'))
        self.assertEqual(len(entries), 1)
        item = normalize(entries[0])
        self.assertEqual((item['id'], item['title'], item['published']),
                         ('12', 'Example', '2026-09-01'))
        self.assertEqual(extractor._call_api.call_count, 2)
        self.assertEqual(extractor._call_api.call_args.kwargs['query']['page[cursor]'], 'cursor-one')
