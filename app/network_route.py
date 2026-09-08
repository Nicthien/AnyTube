"""Pinned public connections through an upstream proxy, including public DNS.

No function in this module falls back to direct networking after a proxy failure.
The administrator supplies the proxy's numeric address (a bootstrap trust anchor).
"""
import asyncio
import base64
import ipaddress
import json
import os
import ssl
from urllib.parse import urlencode, urlsplit


async def tunnel(config, address, port):
    target = ipaddress.ip_address(address)
    proxy = urlsplit(config['proxy_url'])
    ipaddress.ip_address(proxy.hostname)
    context = ssl.create_default_context() if proxy.scheme == 'https' else None
    port_proxy = proxy.port or (443 if context else 80)
    bridge = os.environ.get('ANYTUBE_SERVICE_PROXY') if os.environ.get('ANYTUBE_SERVICE_MODE') != '1' else None
    if bridge:
        bridge_url = urlsplit(bridge)
        reader, writer = await asyncio.wait_for(asyncio.open_connection(bridge_url.hostname, bridge_url.port), 15)
        authority = f'[{proxy.hostname}]:{port_proxy}' if ':' in proxy.hostname else f'{proxy.hostname}:{port_proxy}'
        writer.write(f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\nProxy-Authorization: Bearer {os.environ["ANYTUBE_SERVICE_TOKEN"]}\r\n\r\n'.encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 15)
        if response.split(b'\r\n', 1)[0].split(b' ')[1:2] != [b'200']:
            writer.close()
            raise OSError('Passerelle interne indisponible.')
        if context:
            await writer.start_tls(context, server_hostname=config.get('tls_name') or proxy.hostname)
    else:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(
            proxy.hostname, port_proxy, ssl=context,
            server_hostname=(config.get('tls_name') or proxy.hostname) if context else None), 15)
    try:
        authority = f'[{target}]:{port}' if target.version == 6 else f'{target}:{port}'
        headers = [f'CONNECT {authority} HTTP/1.1', f'Host: {authority}']
        if config.get('username') or config.get('password'):
            encoded = base64.b64encode((config.get('username', '') + ':' + config.get('password', '')).encode()).decode()
            headers.append('Proxy-Authorization: Basic ' + encoded)
        writer.write(('\r\n'.join(headers) + '\r\n\r\n').encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 15)
        if len(response) > 16384 or response.split(b'\r\n', 1)[0].split(b' ')[1:2] != [b'200']:
            raise OSError('Le proxy a refusé la connexion.')
        return reader, writer
    except BaseException:
        writer.close()
        raise


async def read_response(reader, limit=65536):
    header = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 15)
    if len(header) > 16384 or header.split(b'\r\n', 1)[0].split(b' ')[1:2] != [b'200']:
        raise OSError('Réponse réseau invalide.')
    headers = {}
    for line in header.split(b'\r\n')[1:]:
        if b':' in line:
            key, value = line.split(b':', 1)
            headers[key.strip().lower()] = value.strip().lower()
    if headers.get(b'transfer-encoding') == b'chunked':
        body = bytearray()
        while True:
            size = int((await reader.readline()).split(b';', 1)[0], 16)
            if size == 0:
                break
            if size < 0 or len(body) + size > limit:
                raise ValueError('Réponse trop volumineuse.')
            body.extend(await reader.readexactly(size))
            if await reader.readexactly(2) != b'\r\n':
                raise ValueError('Réponse fragmentée invalide.')
        return bytes(body)
    size = int(headers.get(b'content-length', b'-1'))
    if size < 0 or size > limit:
        raise ValueError('Taille de réponse non bornée.')
    return await asyncio.wait_for(reader.readexactly(size), 15)


async def resolve(config, host):
    from app.egress import is_public
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = []
        # Numeric bootstrap: this lookup itself cannot use the host DNS resolver.
        for kind in ('A', 'AAAA'):
            reader, writer = await tunnel(config, '1.1.1.1', 443)
            try:
                await writer.start_tls(ssl.create_default_context(), server_hostname='cloudflare-dns.com')
                path = '/dns-query?' + urlencode({'name': host, 'type': kind})
                writer.write(f'GET {path} HTTP/1.1\r\nHost: cloudflare-dns.com\r\nAccept: application/dns-json\r\nConnection: close\r\n\r\n'.encode())
                await writer.drain()
                data = json.loads(await read_response(reader))
                if data.get('Status') != 0:
                    raise OSError('Résolution publique indisponible.')
                for answer in data.get('Answer', [])[:100]:
                    if answer.get('type') in (1, 28):
                        addresses.append(str(ipaddress.ip_address(answer['data'])))
            finally:
                writer.close()
    if not addresses or any(not is_public(address) for address in addresses):
        raise ValueError('Destination privée ou indisponible.')
    return list(dict.fromkeys(addresses))


async def connection(config, host, port):
    if port not in (80, 443):
        raise ValueError('Port public interdit.')
    addresses = await resolve(config, host)
    for address in addresses:
        try:
            return await tunnel(config, address, port)
        except OSError:
            continue
    raise OSError('Trajet sortant indisponible. Aucun retour au réseau direct.')
