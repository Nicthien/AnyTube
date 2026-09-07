"""Owner-based firewall and unprivileged services in one Docker network namespace."""
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import secrets
import sqlite3


def rule(binary, *args):
    subprocess.run([binary, '-w', *args], check=True)


def firewall(binary, ipv6=False):
    rule(binary, '-P', 'OUTPUT', 'DROP')
    rule(binary, '-F', 'OUTPUT')
    rule(binary, '-A', 'OUTPUT', '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT')
    # Only the authenticated administrator-service proxy can reach LAN services.
    rule(binary, '-A', 'OUTPUT', '-m', 'owner', '--uid-owner', '10004', '-p', 'tcp', '-j', 'ACCEPT')
    rule(binary, '-A', 'OUTPUT', '-m', 'owner', '--uid-owner', '10004', '-p', 'udp', '--dport', '53', '-j', 'ACCEPT')
    if ipv6:
        return
    for uid, port in (('10001', '3128'), ('10001', '3129'), ('10003', '8000')):
        rule(binary, '-A', 'OUTPUT', '-m', 'owner', '--uid-owner', uid, '-d', '127.0.0.1', '-p', 'tcp', '--dport', port, '-j', 'ACCEPT')
    # Embedded Docker DNS has a random destination port after DNAT.
    rule(binary, '-A', 'OUTPUT', '-m', 'owner', '--uid-owner', '10002', '-d', '127.0.0.11', '-p', 'udp', '-j', 'ACCEPT')
    rule(binary, '-A', 'OUTPUT', '-m', 'owner', '--uid-owner', '10004', '-d', '127.0.0.11', '-p', 'udp', '-j', 'ACCEPT')
    for network in ('0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24', '192.168.0.0/16', '198.18.0.0/15', '198.51.100.0/24', '203.0.113.0/24', '224.0.0.0/4', '240.0.0.0/4'):
        rule(binary, '-A', 'OUTPUT', '-d', network, '-j', 'REJECT')
    rule(binary, '-A', 'OUTPUT', '-m', 'owner', '--uid-owner', '10002', '-p', 'tcp', '-m', 'multiport', '--dports', '80,443', '-j', 'ACCEPT')


def spawn(module, *args, uid=10001, env=None):
    return subprocess.Popen(['setpriv', '--reuid', str(uid), '--regid', str(uid), '--clear-groups', '--bounding-set=-all', '--inh-caps=-all', '--ambient-caps=-all', '--no-new-privs', sys.executable, '-m', module, *args], env=env)


def main():
    if os.getuid() != 0:
        raise RuntimeError('Use the supplied single-container Compose configuration.')
    for folder in ('/data', '/media', '/backups', '/secrets'):
        Path(folder).mkdir(parents=True, exist_ok=True)
        os.chown(folder, 10001, 10001)
        os.chmod(folder, 0o700)
    key_path = Path(os.environ.get('ANYTUBE_VAULT_KEY_FILE', '/secrets/vault.key'))
    if not key_path.exists():
        database = Path('/data/anytube.db')
        if database.exists():
            with sqlite3.connect(database.as_uri()+'?mode=ro', uri=True) as db:
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='credentials'").fetchone()
                if exists and db.execute('SELECT count(*) FROM credentials').fetchone()[0]:
                    raise RuntimeError('Restore the vault key: existing credentials must not receive a new key.')
        with key_path.open('xb') as target:
            target.write(secrets.token_bytes(32))
    if key_path.stat().st_size != 32:
        raise RuntimeError('Invalid vault key. Restore the original 32-byte key.')
    os.chown(key_path, 10001, 10001)
    os.chmod(key_path, 0o400)
    os.environ['ANYTUBE_VAULT_KEY_FILE'] = str(key_path)
    firewall('iptables')
    if Path('/proc/net/if_inet6').exists():
        firewall('ip6tables', ipv6=True)
    os.environ.update(ANYTUBE_PROXY='http://127.0.0.1:3128', HTTP_PROXY='http://127.0.0.1:3128', HTTPS_PROXY='http://127.0.0.1:3128', NO_PROXY='localhost,127.0.0.1', ANYTUBE_EGRESS_BIND='127.0.0.1')
    children = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        children.append(spawn('app.egress', uid=10002))
        os.environ.update(ANYTUBE_SERVICE_PROXY='http://127.0.0.1:3129', ANYTUBE_SERVICE_TOKEN=secrets.token_hex(32))
        children.append(spawn('app.egress', uid=10004, env={**os.environ, 'ANYTUBE_SERVICE_MODE':'1', 'ANYTUBE_EGRESS_PORT':'3129'}))
        children.append(spawn('uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000', '--no-proxy-headers'))
        children.append(spawn('app.backups', '--daily'))
        # Only CAP_KILL remains in the supervisor, to stop both service UIDs.
        class Header(ctypes.Structure):
            _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]
        class Caps(ctypes.Structure):
            _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32), ('inheritable', ctypes.c_uint32)]
        caps = (Caps * 2)()
        caps[0].effective = caps[0].permitted = 1 << 5
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.capset(ctypes.byref(Header(0x20080522, 0)), caps) != 0:
            raise OSError(ctypes.get_errno(), 'capset')
        while not stopping and all(child.poll() is None for child in children):
            time.sleep(0.25)
        if not stopping:
            raise RuntimeError('An AnyTube service stopped; restart the container.')
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        deadline = time.monotonic() + 20
        for child in children:
            try:
                child.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    main()
