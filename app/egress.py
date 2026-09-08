"""HTTP forward proxy. Pin connections to DNS addresses validated as public."""
import asyncio
import ipaddress
import socket
import os
import hmac
import json
import time
from urllib.parse import urlsplit

route = None
route_updated = 0
route_lock = asyncio.Lock()
connections = set()


async def route_settings():
    global route, route_updated
    endpoint = os.environ.get('ANYTUBE_ROUTE_CONTROL')
    if not endpoint:
        return {'mode': 'direct', 'revision': 'direct'}
    async with route_lock:
        if route and time.monotonic() - route_updated < 1:
            return route
        from app.network_route import read_response
        target = urlsplit(endpoint)
        reader, writer = await asyncio.wait_for(asyncio.open_connection(target.hostname, target.port or 80), 3)
        try:
            writer.write(f'GET {target.path} HTTP/1.1\r\nHost: {target.netloc}\r\nAuthorization: Bearer {os.environ["ANYTUBE_SERVICE_TOKEN"]}\r\nConnection: close\r\n\r\n'.encode())
            await writer.drain()
            updated = json.loads(await read_response(reader))
            if route and route['revision'] != updated['revision']:
                for task in list(connections):
                    if task is not asyncio.current_task():
                        task.cancel()
            route, route_updated = updated, time.monotonic()
            return route
        finally:
            writer.close()


async def routed_connection(host, port, trusted=False):
    config = await route_settings()
    if config['mode'] == 'direct':
        return await public_connection(host, port, trusted)
    proxy = urlsplit(config['proxy_url'])
    if trusted and (host in config.get('internal_hosts', []) or
                    (host == proxy.hostname and port == (proxy.port or (443 if proxy.scheme == 'https' else 80)))):
        return await public_connection(host, port, True)
    from app.network_route import connection
    return await connection(config, host, port)


async def watch_route():
    while True:
        await asyncio.sleep(1)
        try:
            await route_settings()
        except Exception:
            # Existing public tunnels must also stop if control is unavailable.
            for task in list(connections):
                task.cancel()


def is_public(value):
    address=ipaddress.ip_address(value.split('%')[0])
    mapped=getattr(address,'ipv4_mapped',None)
    return address.is_global and (mapped is None or mapped.is_global)


async def public_connection(host,port, trusted=False):
    addresses=await asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM)
    if not addresses or (not trusted and any(not is_public(info[4][0]) for info in addresses)):
        raise ValueError('Adresse réseau interdite')
    for family,_,_,_,address in addresses:
        try:
            # Numeric address prevents a second DNS resolution / rebinding.
            return await asyncio.wait_for(asyncio.open_connection(address[0],port,family=family),15)
        except OSError:
            continue
    raise OSError('Destination indisponible')


async def pipe(reader,writer):
    while chunk:=await asyncio.wait_for(reader.read(65536),90):
        writer.write(chunk)
        await writer.drain()


async def client(reader,writer):
    connections.add(asyncio.current_task())
    upstream=None
    streams=[]
    try:
        header=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),10)
        if len(header)>16384:raise ValueError()
        lines=header.decode('iso-8859-1').split('\r\n')
        trusted = os.environ.get('ANYTUBE_SERVICE_MODE') == '1'
        public_token = os.environ.get('ANYTUBE_EGRESS_AUTH_TOKEN')
        if trusted or public_token:
            credentials = [line.split(':',1)[1].strip() for line in lines[1:] if line.lower().startswith('proxy-authorization:')]
            expected = 'Bearer ' + (public_token or os.environ['ANYTUBE_SERVICE_TOKEN'])
            if len(credentials) != 1 or not hmac.compare_digest(credentials[0], expected):
                raise ValueError('Service authentication required')
        method,target,version=lines[0].split(' ')
        if version not in ('HTTP/1.0','HTTP/1.1'):raise ValueError()
        if method=='CONNECT':
            parts=urlsplit('//'+target)
            if (not trusted and parts.port!=443) or not parts.port or parts.username or parts.password or parts.path:raise ValueError()
            remote,upstream=await routed_connection(parts.hostname,parts.port,trusted)
            writer.write(b'HTTP/1.1 200 Connection established\r\n\r\n');await writer.drain()
        else:
            parts=urlsplit(target)
            methods = ('GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS') if trusted else ('GET','HEAD','POST')
            if method not in methods or parts.scheme!='http' or (not trusted and (parts.port or 80)!=80) or parts.username or parts.password:raise ValueError()
            remote,upstream=await routed_connection(parts.hostname,parts.port or 80,trusted)
            path=parts.path or '/'
            if parts.query:path+='?'+parts.query
            forwarded=[line for line in lines[1:] if line and line.split(':',1)[0].lower() not in ('proxy-authorization','proxy-connection','connection','host')]
            host=parts.netloc
            forwarded.extend([f'Host: {host}','Connection: close'])
            upstream.write((f'{method} {path} {version}\r\n'+'\r\n'.join(forwarded)+'\r\n\r\n').encode('iso-8859-1'))
            await upstream.drain()
        streams=[asyncio.create_task(pipe(reader,upstream)),asyncio.create_task(pipe(remote,writer))]
        await asyncio.wait(streams,return_when=asyncio.FIRST_COMPLETED)
    except (ValueError,OSError,TimeoutError,asyncio.IncompleteReadError,asyncio.LimitOverrunError):
        if upstream is None:
            writer.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
    finally:
        connections.discard(asyncio.current_task())
        for task in streams:task.cancel()
        await asyncio.gather(*streams,return_exceptions=True)
        if upstream:upstream.close()
        writer.close()
        try:await writer.wait_closed()
        except OSError:pass


async def main():
    gate=asyncio.Semaphore(64)
    async def bounded(reader,writer):
        if gate.locked():writer.close();return
        async with gate:await client(reader,writer)
    server=await asyncio.start_server(bounded,os.environ.get('ANYTUBE_EGRESS_BIND','0.0.0.0'),int(os.environ.get('ANYTUBE_EGRESS_PORT','3128')),limit=16384)
    watcher=asyncio.create_task(watch_route()) if os.environ.get('ANYTUBE_ROUTE_CONTROL') else None
    try:
        async with server:await server.serve_forever()
    finally:
        if watcher:
            watcher.cancel()
            await asyncio.gather(watcher,return_exceptions=True)


if __name__=='__main__':asyncio.run(main())
