import unittest
from yt_dlp import YoutubeDL
from unittest.mock import Mock, patch
from fastapi import HTTPException
from app.discovery import select_source
from app.toongoggles import AnyTubeToonGogglesEpisodeIE, AnyTubeToonGogglesShowIE, register_episode


class ToonGogglesTests(unittest.TestCase):
    def test_modern_urls_require_the_enabled_matching_source(self):
        source = {'id': 'toon', 'enabled': True, 'connector': {'extractor': 'ToonGoggles'}}
        urls = ['https://www.toongoggles.com/shows/bernard',
                'https://www.toongoggles.com/shows/bernard/season/1/episode/1']
        with patch('app.discovery.saved_sources', return_value=[source]):
            for url in urls:
                self.assertEqual(select_source(url, 'toon'), (source, 'ToonGoggles'))
                with self.assertRaises(HTTPException):
                    select_source(url, 'other')
            with self.assertRaises(HTTPException):
                select_source('https://toongoggles.com.example.org/shows/bernard')
            source['enabled'] = False
            for url in urls:
                with self.assertRaises(HTTPException):
                    select_source(url)

    def test_show_collects_seasons_once_and_rejects_other_show_links(self):
        ie = AnyTubeToonGogglesShowIE(YoutubeDL({'quiet': True}))
        ie._download_webpage = Mock(return_value='''<meta property="og:title" content="Bernard">
            <a href="/shows/bernard/season/1/episode/1" title="One" data-ottera-id="1">
            <a href="/shows/bernard/season/1/episode/1" title="Duplicate">
            <a href="/shows/bernard/season/2/episode/1" title="Two" data-ottera-id="2">
            <a href="/shows/other/season/1/episode/1" title="Other">''')
        result = ie._real_extract('https://www.toongoggles.com/shows/bernard')
        self.assertEqual([x['title'] for x in result['entries']], ['One', 'Two'])
        self.assertEqual(ie._download_webpage.call_count, 1)

    def test_modern_episode_uses_only_official_player_source(self):
        ie = AnyTubeToonGogglesEpisodeIE(YoutubeDL({"quiet": True}))
        ie._download_webpage = Mock(side_effect=[
            '<meta property="og:title" content="Table Tennis"><div data-ottera-id="257914">',
            "playerSources.hls = [{url: 'https://cdn.example/a.m3u8'}];",
        ])
        ie._extract_m3u8_formats_and_subtitles = Mock(return_value=([{'format_id': 'hls'}], {}))
        result = ie._real_extract('https://www.toongoggles.com/shows/bernard/season/1/episode/1')
        self.assertEqual((result['id'], result['title']), ('257914', 'Table Tennis'))
        self.assertEqual(ie._download_webpage.call_count, 2)
        self.assertEqual(ie._download_webpage.call_args.kwargs['query']['id'], '257914')
        self.assertEqual(result['formats'], [{'format_id': 'hls'}])

    def test_registration_does_not_replace_legacy_or_other_sources(self):
        ydl = Mock()
        for url in ['https://www.toongoggles.com/shows/217143/bernard', 'https://example.com/shows/a/season/1/episode/1']:
            self.assertEqual(register_episode(ydl, url, 'Existing'), 'Existing')
        ydl.add_info_extractor.assert_not_called()
