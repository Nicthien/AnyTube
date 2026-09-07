import unittest

from app.relay import media_mime


class RelayMimeTests(unittest.TestCase):
    def test_fragmented_mp4_with_generic_cdn_type(self):
        init = b'\x00\x00\x00\x20ftypisom\x00\x00\x02\x00iso6'
        self.assertEqual(media_mime(init, 'application/octet-stream'), 'video/mp4')
        self.assertEqual(media_mime(init, 'audio/mp4'), 'audio/mp4')
        self.assertEqual(media_mime(b'not an mp4', 'application/octet-stream'), 'application/octet-stream')
