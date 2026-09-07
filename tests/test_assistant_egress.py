import asyncio
import os
import unittest
from unittest.mock import patch
from app.egress import client, public_connection


class ServiceProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_proxy_rejects_private_destination(self):
        with self.assertRaises(ValueError):
            await public_connection('127.0.0.1', 80)

    async def test_service_proxy_requires_token_and_strips_it(self):
        seen = []
        async def target(reader, writer):
            seen.append(await reader.readuntil(b'\r\n\r\n'))
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK')
            await writer.drain()
            writer.close()
        upstream = await asyncio.start_server(target, '127.0.0.1', 0)
        port = upstream.sockets[0].getsockname()[1]
        proxy = await asyncio.start_server(client, '127.0.0.1', 0)
        proxy_port = proxy.sockets[0].getsockname()[1]
        try:
            with patch.dict(os.environ, ANYTUBE_SERVICE_MODE='1', ANYTUBE_SERVICE_TOKEN='test-only-token'):
                for credential, expected in [('', b'403'), ('Bearer wrong', b'403'), ('Bearer test-only-token', b'200')]:
                    reader, writer = await asyncio.open_connection('127.0.0.1', proxy_port)
                    header = f'Proxy-Authorization: {credential}\r\n' if credential else ''
                    writer.write(f'GET http://127.0.0.1:{port}/test HTTP/1.1\r\n{header}\r\n'.encode())
                    await writer.drain()
                    response = await asyncio.wait_for(reader.read(), 3)
                    self.assertIn(expected, response.split(b'\r\n')[0])
                    writer.close()
                    await writer.wait_closed()
            self.assertEqual(len(seen), 1)
            self.assertNotIn(b'test-only-token', seen[0])
            self.assertNotIn(b'Proxy-Authorization', seen[0])
            self.assertIn(f'Host: 127.0.0.1:{port}'.encode(), seen[0])
        finally:
            proxy.close()
            upstream.close()
            await proxy.wait_closed()
            await upstream.wait_closed()
