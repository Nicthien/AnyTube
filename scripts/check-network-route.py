"""Probe the real pinned route, rejecting any attempt at local public DNS."""
import asyncio
import ipaddress
import os
import socket
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.network_route import connection


async def main():
    original = socket.getaddrinfo
    def numeric_only(host, *args, **kwargs):
        ipaddress.ip_address(host)  # A hostname here would be a DNS leak.
        return original(host, *args, **kwargs)
    socket.getaddrinfo = numeric_only
    config = {'proxy_url': os.environ['TEST_PROXY']}
    try:
        async with asyncio.timeout(45):
            reader, writer = await connection(config, 'example.org', 443)
            try:
                await writer.start_tls(ssl.create_default_context(), server_hostname='example.org')
                writer.write(b'GET / HTTP/1.1\r\nHost: example.org\r\nConnection: close\r\n\r\n')
                await writer.drain()
                header = await reader.readuntil(b'\r\n\r\n')
                assert header.startswith(b'HTTP/1.1 200'), header[:100]
            finally:
                writer.close()
        if '--expect-failure' in sys.argv:
            raise AssertionError('Route remained available after the VPN was stopped')
        print('PINNED_PROXY_ROUTE_AND_REMOTE_DNS_OK', flush=True)
    except (OSError, TimeoutError):
        if '--expect-failure' not in sys.argv:
            raise
        print('PINNED_PROXY_ROUTE_FAIL_CLOSED_OK', flush=True)


asyncio.run(main())
