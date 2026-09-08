"""Validate custom OpenVPN inputs before installation; never run their commands."""
import shlex
import configparser
import os
from pathlib import Path

# Certificate material must be inline: the Compose validator mounts one input only.
FLAGS = {'client', 'nobind', 'persist-key', 'persist-tun', 'remote-random', 'auth-nocache',
         'pull', 'tls-client', 'float', 'mute-replay-warnings'}
OPTIONS = {'dev', 'proto', 'remote', 'resolv-retry', 'remote-cert-tls', 'cipher', 'data-ciphers',
           'data-ciphers-fallback', 'auth', 'verb', 'mute', 'reneg-sec', 'tun-mtu', 'mssfix',
           'keepalive', 'ping', 'ping-restart', 'connect-timeout', 'connect-retry', 'tls-version-min',
           'verify-x509-name', 'key-direction'}
INLINE = {'ca', 'cert', 'key', 'tls-auth', 'tls-crypt'}


def validate_openvpn(text):
    if len(text.encode()) > 256 * 1024 or '\x00' in text:
        raise ValueError('Configuration OpenVPN trop volumineuse ou invalide.')
    block = None
    remote = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if block:
            if line == '</' + block + '>':
                block = None
            elif line.startswith('<'):
                raise ValueError('Bloc OpenVPN imbriqué interdit.')
            continue
        if line.startswith('<'):
            name = line[1:-1] if line.endswith('>') else ''
            if name not in INLINE:
                raise ValueError('Bloc OpenVPN non autorisé.')
            block = name
            continue
        fields = shlex.split(line, comments=True)
        name = fields[0].removeprefix('--')
        if name in FLAGS:
            if len(fields) != 1:
                raise ValueError('Option OpenVPN invalide.')
        elif name in OPTIONS:
            if len(fields) < 2 or any(';' in arg or '\n' in arg for arg in fields[1:]):
                raise ValueError('Option OpenVPN invalide.')
            if name == 'remote':
                remote = True
        else:
            raise ValueError('Directive OpenVPN non autorisée : ' + name)
    if block or not remote:
        raise ValueError('Configuration OpenVPN incomplète.')
    return text


def validate_wireguard(text):
    if len(text.encode()) > 65536 or '\x00' in text:
        raise ValueError('Configuration WireGuard invalide.')
    parsed = configparser.ConfigParser(interpolation=None, strict=True)
    parsed.read_string(text)
    if set(parsed.sections()) != {'Interface', 'Peer'}:
        raise ValueError('Une interface et un pair WireGuard sont requis.')
    allowed = {'Interface': {'privatekey', 'address', 'dns', 'mtu'},
               'Peer': {'publickey', 'presharedkey', 'endpoint', 'allowedips', 'persistentkeepalive'}}
    for section in parsed.sections():
        if set(parsed[section]) - allowed[section]:
            raise ValueError('Directive WireGuard non autorisée.')
    if not parsed['Interface'].get('privatekey') or not parsed['Peer'].get('publickey') or not parsed['Peer'].get('endpoint'):
        raise ValueError('Configuration WireGuard incomplète.')
    return text


if __name__ == '__main__':
    protocol = os.environ.get('VPN_TYPE', 'wireguard')
    text = Path('/input/vpn.conf').read_text(encoding='utf-8')
    if protocol == 'wireguard':
        value = validate_wireguard(text)
        target = Path('/output/wireguard/wg0.conf')
    elif protocol == 'openvpn':
        value = validate_openvpn(text)
        target = Path('/output/custom.conf')
    else:
        raise ValueError('Protocole VPN inconnu.')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value, encoding='utf-8')
    os.chmod(target, 0o600)
    print('Configuration VPN validée. Aucun secret affiché.')
