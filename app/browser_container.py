"""Network confinement for the integrated Chromium image (not Browserless)."""
import os
import signal
import socket
import subprocess
import sys
from urllib.parse import urlsplit


def main():
    if os.getuid() != 0:
        raise RuntimeError('Utilisez le service Chromium Compose fourni.')
    proxy = urlsplit(os.environ['ANYTUBE_PROXY'])
    addresses = {info[4][0] for info in socket.getaddrinfo(proxy.hostname, proxy.port, type=socket.SOCK_STREAM)}
    if not addresses or not os.environ.get('ANYTUBE_PUBLIC_PROXY_TOKEN'):
        raise RuntimeError('Passerelle authentifiée requise.')
    # Resolve only this administrator-configured Docker service before locking
    # the namespace. Browser and worker processes get a numeric bootstrap and
    # cannot ask Docker's resolver to resolve public names as a side channel.
    address = sorted(addresses, key=lambda value: ':' in value)[0]
    authority = '[' + address + ']' if ':' in address else address
    os.environ['ANYTUBE_PROXY'] = f'{proxy.scheme}://{authority}:{proxy.port}'
    for binary, family in (('iptables', socket.AF_INET), ('ip6tables', socket.AF_INET6)):
        def rule(*args):
            subprocess.run([binary, '-w', *args], check=True)
        rule('-P', 'OUTPUT', 'DROP')
        rule('-F', 'OUTPUT')
        rule('-A', 'OUTPUT', '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT')
        for address in addresses:
            if (':' in address) != (family == socket.AF_INET6):
                continue
            rule('-A', 'OUTPUT', '-d', address, '-p', 'tcp', '--dport', str(proxy.port), '-j', 'ACCEPT')
        # CDP pipe is used locally. No DNS, listening debugger or egress loopback.
    child = subprocess.Popen(['setpriv', '--reuid', '10003', '--regid', '10003', '--clear-groups',
                              '--bounding-set=-all', '--no-new-privs', sys.executable, '-m', 'uvicorn',
                              'app.assistant_browser:app', '--host', '0.0.0.0', '--port', '8010', '--no-access-log'])
    def stop(*_):
        child.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    sys.exit(child.wait())


if __name__ == '__main__':
    main()
