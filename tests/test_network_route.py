import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError

from app.network_settings import NetworkSettings
from app.network_route import connection, resolve, tunnel
from app.vpn_config import validate_openvpn


class NetworkConfigurationTests(unittest.TestCase):
    def test_direct_default_and_proxy_bootstrap(self):
        self.assertEqual(NetworkSettings().mode, 'direct')
        self.assertEqual(NetworkSettings(mode='proxy', proxy_url='http://192.168.0.5:8888').mode, 'proxy')
        for url in ('http://proxy.example:8080', 'socks5://192.168.0.5:1080', 'http://user:pass@192.168.0.5:8080', 'http://192.168.0.5/other'):
            with self.assertRaises(ValidationError): NetworkSettings(mode='proxy', proxy_url=url)
        value = NetworkSettings(username='user', password='secret').model_dump()
        self.assertNotIn('password', value)
        self.assertNotIn('username', value)

    def test_openvpn_scripts_plugins_and_file_references(self):
        base = 'client\ndev tun\nproto udp\nremote 192.0.2.10 1194\n'
        self.assertEqual(validate_openvpn(base), base)
        for directive in ('up /tmp/run', 'down /tmp/run', 'plugin /tmp/evil.so', 'script-security 2',
                          'config /tmp/other', 'ca /etc/passwd', 'ca /gluetun/custom/ca.crt',
                          'auth-user-pass /tmp/password', 'management 0.0.0.0 9999'):
            with self.assertRaises(ValueError): validate_openvpn(base + directive)
        with self.assertRaises(ValueError): validate_openvpn(base + '<ca>\nincomplete')


class NetworkRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_targets_before_connect(self):
        with patch('app.network_route.tunnel', new_callable=AsyncMock) as proxy:
            for host in ('127.0.0.1', '192.168.0.5', '::1', '::ffff:127.0.0.1'):
                with self.assertRaises(ValueError): await connection({}, host, 443)
            proxy.assert_not_called()

    async def test_no_direct_fallback(self):
        with patch('app.network_route.resolve', new_callable=AsyncMock, return_value=['93.184.216.34']), \
             patch('app.network_route.tunnel', new_callable=AsyncMock, side_effect=OSError('proxy down')), \
             patch('app.egress.public_connection', new_callable=AsyncMock) as direct:
            with self.assertRaises(OSError): await connection({}, 'example.org', 443)
            direct.assert_not_called()

    async def test_numeric_target_does_not_resolve_locally(self):
        with patch('socket.getaddrinfo', side_effect=AssertionError('DNS leak')):
            self.assertEqual(await resolve({}, '93.184.216.34'), ['93.184.216.34'])

    async def test_proxy_connect_is_pinned_and_authenticated(self):
        reader = asyncio.StreamReader(); reader.feed_data(b'HTTP/1.1 200 Connection established\r\n\r\n')
        writer = unittest.mock.Mock(); writer.drain = AsyncMock()
        config = {'proxy_url':'http://192.168.0.5:8888','username':'test','password':'secret'}
        with patch.dict(os.environ, {'ANYTUBE_SERVICE_MODE':'1'}), \
             patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(reader, writer)) as open_connection:
            await tunnel(config, '93.184.216.34', 443)
        self.assertEqual(open_connection.call_args.args, ('192.168.0.5', 8888))
        request = writer.write.call_args.args[0]
        self.assertIn(b'CONNECT 93.184.216.34:443', request)
        self.assertIn(b'Proxy-Authorization: Basic ', request)
        self.assertNotIn(b'example.org', request)
