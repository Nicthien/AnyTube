"""Audit checkpoints must preserve observed dates and invalidate changed inputs."""
import asyncio
import json
from argparse import Namespace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from scripts.audit_lot import probe


class AuditResumeTests(unittest.IsolatedAsyncioTestCase):
    def test_published_checks_use_recomputed_summary_status(self):
        from scripts.audit_lot import update_checks
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'app').mkdir()
            checks_path = root / 'app' / 'template_checks.json'
            checks_path.write_text(json.dumps({'yt_dlp': 'test', 'entries': {
                'Other': {'status': 'empty', 'date': 'old'}}}), encoding='utf-8')
            (root / 'Example.json').write_text(json.dumps({'status': 'empty',
                'date': 'observed-date', 'search': {'query': {'pages': [{'count': 3}]}}}), encoding='utf-8')
            summary = {'yt_dlp': 'test', 'results': {'Example': {'search': 'results_received'}},
                       'batch': 'all', 'generated_at': 'now', 'connector_version': 'engine',
                       'environment': 'local'}
            with patch('scripts.audit_lot.__file__', str(root / 'scripts' / 'audit_lot.py')), patch('builtins.print'):
                update_checks(root, summary)
            checks = json.loads(checks_path.read_text(encoding='utf-8'))['entries']
            self.assertEqual(checks['Example'], {'status': 'results_received', 'count': 3,
                             'date': 'observed-date', 'batch': 'all'})
            self.assertEqual(checks['Other'], {'status': 'empty', 'date': 'old'})

    async def test_summary_only_does_not_report_old_execution_counts_as_new_work(self):
        from scripts.audit_lot import main, environment
        response = {'status': 'empty', 'pages': [], 'distinct_urls_over_two_pages': 0}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch('scripts.audit_lot.two_pages', new_callable=AsyncMock, return_value=response):
                entry = await probe('ArchiveOrg')
            entry = {**environment(), **entry}
            entry['scenarios_executed'] = 123
            entry['scenarios_reused'] = 456
            (root / 'ArchiveOrg.json').write_text(json.dumps(entry), encoding='utf-8')
            args = Namespace(instance=None, output=root, concurrency=2, timeout=30,
                             template=['ArchiveOrg'], batch='all', summarize_only=True,
                             update_checks=False, resume=False)
            with patch('builtins.print'), patch('scripts.audit_lot.two_pages', new_callable=AsyncMock) as network:
                await main(args)
            network.assert_not_awaited()
            summary = json.loads((root / 'summary-selection.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['execution'], {'mode': 'summarize_only',
                'scenarios_executed': 0, 'scenarios_reused': 0, 'proofs_aggregated': 1})
            self.assertFalse((root / 'summary-selection-network.json').exists())

    async def test_summary_rejects_missing_or_mixed_proofs_without_rewriting_files(self):
        from scripts.audit_lot import main
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = root / 'ArchiveOrg.json'
            first.write_text(json.dumps({'connector_version': 'old'}), encoding='utf-8')
            original = first.read_bytes()
            args = Namespace(instance=None, output=root, concurrency=2, timeout=30,
                             template=['ArchiveOrg', 'Youtube'], batch='all',
                             summarize_only=True, update_checks=False, resume=False)
            with self.assertRaisesRegex(SystemExit, 'Preuve manquante'):
                await main(args)
            (root / 'Youtube.json').write_text(json.dumps({'connector_version': 'new'}), encoding='utf-8')
            with self.assertRaisesRegex(SystemExit, 'environnements différents'):
                await main(args)
            self.assertEqual(first.read_bytes(), original)
            self.assertFalse((root / 'summary-selection.json').exists())

    def test_provider_budget_groups_aliases_and_separates_instances(self):
        from app.main import worker_platform
        from app.connectors import default_connector
        self.assertEqual(worker_platform(default_connector('Youtube')),
                         worker_platform(default_connector('YoutubeSearchURL')))
        self.assertEqual(worker_platform(default_connector('Niconico')),
                         worker_platform(default_connector('NicovideoSearch')))
        self.assertNotEqual(worker_platform(default_connector('PeerTube', 'tilvids.com')),
                            worker_platform(default_connector('PeerTube', 'framatube.org')))

    async def test_resume_skips_completed_scenarios_but_rechecks_changed_revision(self):
        response = {'status': 'results_received', 'pages': [{'count': 3}],
                    'distinct_urls_over_two_pages': 3}
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / 'checkpoint.json'
            with patch('scripts.audit_lot.revision', return_value='one'), patch(
                    'scripts.audit_lot.two_pages', new_callable=AsyncMock, return_value=response) as run:
                first = await probe('ArchiveOrg', checkpoint=checkpoint)
                calls = run.await_count
                second = await probe('ArchiveOrg', checkpoint=checkpoint, resume=True)
                self.assertEqual(run.await_count, calls)
                self.assertEqual(first['search'], second['search'])
            with patch('scripts.audit_lot.revision', return_value='two'), patch(
                    'scripts.audit_lot.two_pages', new_callable=AsyncMock, return_value=response) as run:
                await probe('ArchiveOrg', checkpoint=checkpoint, resume=True)
                self.assertEqual(run.await_count, calls)

    async def test_interruption_retains_finished_scenarios(self):
        response = {'status': 'empty', 'pages': [], 'distinct_urls_over_two_pages': 0}
        with tempfile.TemporaryDirectory() as folder:
            checkpoint = Path(folder) / 'checkpoint.json'
            with patch('scripts.audit_lot.revision', return_value='one'), patch(
                    'scripts.audit_lot.two_pages', new_callable=AsyncMock,
                    side_effect=[response, asyncio.CancelledError()]):
                with self.assertRaises(asyncio.CancelledError):
                    await probe('ArchiveOrg', checkpoint=checkpoint)
            with patch('scripts.audit_lot.revision', return_value='one'), patch(
                    'scripts.audit_lot.two_pages', new_callable=AsyncMock, return_value=response) as run:
                await probe('ArchiveOrg', checkpoint=checkpoint, resume=True)
                self.assertNotEqual(run.await_args_list[0].args[1], 'nature')
