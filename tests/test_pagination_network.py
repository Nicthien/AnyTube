import asyncio
from contextlib import closing
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import patch,AsyncMock
from support import TestClient
from app.main import app
from app.store import current_user
from app.pagination import encode,decode,search_config
from app.connectors import default_connector
from app.egress import is_public,public_connection
from app.backups import backup


class PaginationTests(unittest.TestCase):
    def test_cursor_is_bound_and_search_preserves_partial_results(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'ANYTUBE_DATA':folder}),TestClient(app) as client:
            async def worker(payload):
                return {'items':[{'url':f'https://example.org/{payload["source"]}/{i}','title':str(i)} for i in range(payload['limit'])]}
            headers={'X-AnyTube':'1'}
            with patch('app.main.run_worker',side_effect=worker):
                first=client.post('/api/search',json={'query':'nature','limit':2},headers=headers).json()
                second=client.post('/api/search',json={'query':'nature','limit':2,'cursors':first['next_cursors']},headers=headers).json()
                self.assertFalse({i['url'] for i in first['items']}&{i['url'] for i in second['items']})
                self.assertEqual(len(second['items']),4)
                self.assertEqual(client.post('/api/search',json={'query':'different','cursors':first['next_cursors']},headers=headers).status_code,400)
                cursor=encode(10,{'a':1});self.assertEqual(decode(cursor,{'a':1}),10)
                context=current_user.set('another-user')
                try:
                    with self.assertRaises(Exception):decode(cursor,{'a':1})
                finally:current_user.reset(context)
                with self.assertRaises(Exception):decode(cursor+'x',{'a':1})
                with patch('app.pagination.time.time',return_value=10**12):
                    with self.assertRaises(Exception):decode(cursor,{'a':1})

    def test_filters_are_platform_capabilities(self):
        config=search_config(default_connector('Dailymotion'),'views','short',7)
        self.assertIn('shorter_than=4',config['search_url'])
        self.assertIn('sort=visited',config['search_url'])
        with self.assertRaises(Exception):search_config(default_connector('Youtube'),'default','short',0)

    def test_proxy_rejects_mixed_dns_and_pins_public_address(self):
        for address in ('127.0.0.1','10.0.0.1','192.168.0.5','169.254.169.254','::1','fe80::1','::ffff:192.168.1.1','100.64.0.1'):
            self.assertFalse(is_public(address),address)
        async def exercise():
            loop=asyncio.get_running_loop()
            public=(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))
            private=(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))
            with patch.object(loop,'getaddrinfo',new=AsyncMock(return_value=[public,private])),patch('app.egress.asyncio.open_connection',new=AsyncMock()) as opened:
                with self.assertRaises(ValueError):await public_connection('example.org',443)
                opened.assert_not_called()
            with patch.object(loop,'getaddrinfo',new=AsyncMock(return_value=[public])),patch('app.egress.asyncio.open_connection',new=AsyncMock(return_value=('reader','writer'))) as opened:
                await public_connection('example.org',443)
                opened.assert_awaited_once_with('8.8.8.8',443,family=socket.AF_INET)
        asyncio.run(exercise())

    def test_database_backup_is_restorable(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.db'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE data(value TEXT)');db.execute("INSERT INTO data VALUES ('preserved')");db.commit()
            result=backup(path,Path(folder)/'backups')
            with closing(sqlite3.connect(result)) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(db.execute('SELECT value FROM data').fetchone()[0],'preserved')

    def test_configuration_is_saved_with_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            config=root/'configuration';config.mkdir()
            (config/'.env').write_bytes(b'ANYTUBE_PORT=8088\n')
            database=root/'source.db'
            with closing(sqlite3.connect(database)) as db:
                db.execute('CREATE TABLE example(value TEXT)');db.commit()
            with patch.dict('os.environ',{'ANYTUBE_CONFIG':str(config)}):
                result=backup(database,root/'backups')
            with zipfile.ZipFile(result.with_suffix('.config.zip')) as archive:
                self.assertEqual(archive.read('.env'),b'ANYTUBE_PORT=8088\n')
