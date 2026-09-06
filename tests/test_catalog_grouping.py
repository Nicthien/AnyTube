import unittest

from app.catalog import catalog, source_catalog, SOURCE_FAMILIES


class CatalogGroupingTests(unittest.TestCase):
    def test_every_extractor_remains_accessible_exactly_once(self):
        original = {entry['id'] for entry in catalog()}
        expanded = [variant['id'] for entry in source_catalog()
                    for variant in entry.get('variants', [entry])]
        self.assertEqual(set(expanded), original)
        self.assertEqual(len(expanded), len(original))

    def test_niconico_has_one_entry_with_all_search_modes(self):
        entries = [entry for entry in source_catalog() if entry['platform_id'] == 'niconico']
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['id'], 'Niconico')
        self.assertTrue({'Niconico', 'NicovideoSearch', 'NicovideoSearchDate', 'NicovideoSearchURL'}
                        <= {item['id'] for item in entries[0]['variants']})

    def test_reviewed_families_group_without_mutating_raw_catalog(self):
        grouped = source_catalog()
        for platform, primary in SOURCE_FAMILIES.items():
            self.assertEqual([entry['id'] for entry in grouped if entry['platform_id'] == platform], [primary])
        self.assertTrue(all('variants' not in entry for entry in catalog()))
        youtube = next(entry for entry in grouped if entry['id'] == 'Youtube')
        self.assertIn('YoutubeMusicSearchURL', youtube['search_terms'])
