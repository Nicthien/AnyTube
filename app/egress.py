"""HTTP forward proxy. Pin connections to DNS addresses validated as public."""
import asyncio
import ipaddress
import socket
import os
from urllib.parse import urlsplit


def is_public(value):
    address=ipaddress.ip_address(value.split('%')[0])
    mapped=getattr(address,'ipv4_mapped',None)
    return address.is_global and (mapped is None or mapped.is_global)


async def public_connection(host,port):
    addresses=await asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM)
    if not addresses or any(not is_public(info[4][0]) for info in addresses):
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
    upstream=None
    streams=[]
    try:
        header=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),10)
        if len(header)>16384:raise ValueError()
        lines=header.decode('iso-8859-1').split('\r\n')
        method,target,version=lines[0].split(' ')
        if version not in ('HTTP/1.0','HTTP/1.1'):raise ValueError()
        if method=='CONNECT':
            parts=urlsplit('//'+target)
            if parts.port!=443 or parts.username or parts.password or parts.path:raise ValueError()
            remote,upstream=await public_connection(parts.hostname,443)
            writer.write(b'HTTP/1.1 200 Connection established\r\n\r\n');await writer.drain()
        else:
            parts=urlsplit(target)
            if method not in ('GET','HEAD','POST') or parts.scheme!='http' or (parts.port or 80)!=80 or parts.username or parts.password:raise ValueError()
            remote,upstream=await public_connection(parts.hostname,80)
            path=parts.path or '/'
            if parts.query:path+='?'+parts.query
            forwarded=[line for line in lines[1:] if line and line.split(':',1)[0].lower() not in ('proxy-authorization','proxy-connection','connection','host')]
            host=parts.hostname
            forwarded.extend([f'Host: {host}','Connection: close'])
            upstream.write((f'{method} {path} {version}\r\n'+'\r\n'.join(forwarded)+'\r\n\r\n').encode('iso-8859-1'))
            await upstream.drain()
        streams=[asyncio.create_task(pipe(reader,upstream)),asyncio.create_task(pipe(remote,writer))]
        await asyncio.wait(streams,return_when=asyncio.FIRST_COMPLETED)
    except (ValueError,OSError,TimeoutError,asyncio.IncompleteReadError,asyncio.LimitOverrunError):
        if upstream is None:
            writer.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
    finally:
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
    server=await asyncio.start_server(bounded,os.environ.get('ANYTUBE_EGRESS_BIND','0.0.0.0'),3128,limit=16384)
    async with server:await server.serve_forever()


if __name__=='__main__':asyncio.run(main())
