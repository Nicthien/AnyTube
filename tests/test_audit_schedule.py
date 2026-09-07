import json
from pathlib import Path
import tempfile
import unittest

from scripts.audit_lot import schedule


class AuditScheduleTests(unittest.TestCase):
    def test_slow_sources_start_first_without_losing_unknown_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'performance.json').write_text(json.dumps({'connector_version':'current', 'templates':[
                {'template':'fast', 'observed_worker_seconds':1},
                {'template':'slow', 'observed_worker_seconds':100}]}), encoding='utf-8')
            selection = ['new', 'fast', 'slow']
            self.assertEqual(schedule(selection, root, 'current'), ['slow', 'fast', 'new'])
            self.assertEqual(schedule(selection, root, 'changed'), ['slow', 'fast', 'new'])
            self.assertEqual(selection, ['new', 'fast', 'slow'])

    def test_missing_or_invalid_report_does_not_block_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(schedule(['a'], root, 'v'), ['a'])
            (root / 'performance.json').write_text('{', encoding='utf-8')
            self.assertEqual(schedule(['a'], root, 'v'), ['a'])
