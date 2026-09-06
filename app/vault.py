"""Account-owned encrypted credentials. The encryption key is never stored in SQLite."""
import base64
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from Cryptodome.Cipher import AES
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.store import connect, owner

router = APIRouter()


def key():
    path = os.environ.get('ANYTUBE_VAULT_KEY_FILE')
    if not path:
        raise HTTPException(503, 'Le coffre nécessite une clé externe. Configurez ANYTUBE_VAULT_KEY_FILE sur le serveur.')
    try:
        value = Path(path).read_bytes()
        if len(value) != 32:
            raise ValueError()
        return value
    except (OSError, ValueError):
        raise HTTPException(503, 'La clé du coffre est absente ou invalide. Restaurez la clé avant de modifier les accès.')


class Credential(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    kind: Literal['bearer', 'api_key', 'cookies']
    domains: list[str] = Field(min_length=1, max_length=20)
    value: str = Field(min_length=1, max_length=131072)
    username: str = Field(default='', max_length=300)
    header: str = Field(default='X-API-Key', max_length=80)

    @model_validator(mode='after')
    def validate_access(self):
        from app.connectors import public_url
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('Donnez un nom à cet accès.')
        normalized = []
        for domain in self.domains:
            domain = domain.strip().lower().encode('idna').decode()
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', domain) or '.' not in domain:
                raise ValueError('Indiquez des domaines exacts, sans URL ni joker.')
            public_url('https://' + domain)
            normalized.append(domain)
        self.domains = sorted(set(normalized))
        if self.kind == 'api_key' and (not re.fullmatch(r'[A-Za-z0-9-]+', self.header) or self.header.lower() in
                ('host', 'cookie', 'connection', 'content-length', 'transfer-encoding', 'proxy-authorization', 'forwarded')):
            raise ValueError('En-tête de clé API interdit.')
        if self.kind != 'cookies' and any(c in self.value for c in ('\r', '\n', '\x00')):
            raise ValueError('Cet identifiant doit tenir sur une seule ligne.')
        if self.kind == 'cookies':
            cookie_records(self.value, self.domains)
        return self


def cookie_records(text, domains):
    """Accept only explicitly scoped Netscape records, including HttpOnly cookies."""
    lines = text.splitlines()
    if not lines or lines[0].strip() not in ('# HTTP Cookie File', '# Netscape HTTP Cookie File'):
        raise ValueError('Importez un fichier de cookies au format Netscape.')
    records = []
    for line in lines[1:]:
        if line.startswith('#HttpOnly_'):
            line = line[len('#HttpOnly_'):]
        elif not line.strip() or line.startswith('#'):
            continue
        fields = line.split('\t')
        if len(fields) != 7:
            raise ValueError('Ligne de cookies invalide.')
        domain, include, path, secure, expiry, name, value = fields
        if domain.lstrip('.').lower() not in domains:
            raise ValueError('Le fichier contient des cookies hors des domaines autorisés. Exportez seulement les cookies de la source.')
        if include not in ('TRUE', 'FALSE') or secure not in ('TRUE', 'FALSE') or not expiry.isdigit() or not path.startswith('/') or not name:
            raise ValueError('Cookie invalide.')
        records.append(fields)
    if not records:
        raise ValueError('Aucun cookie dans ce fichier.')
    return records


def encrypt(identifier, value):
    nonce = secrets.token_bytes(12)
    cipher = AES.new(key(), AES.MODE_GCM, nonce=nonce)
    cipher.update(f'anytube:1:{owner()}:{identifier}'.encode())
    encrypted, tag = cipher.encrypt_and_digest(json.dumps(value).encode())
    return base64.b64encode(nonce + tag + encrypted).decode()


def row(identifier):
    with connect() as db:
        entry = db.execute('SELECT * FROM credentials WHERE owner=? AND id=?', (owner(), identifier)).fetchone()
    if not entry:
        raise HTTPException(404, 'Accès introuvable dans votre compte.')
    return dict(entry)


def reveal(identifier):
    entry = row(identifier)
    try:
        raw = base64.b64decode(entry['encrypted'], validate=True)
        cipher = AES.new(key(), AES.MODE_GCM, nonce=raw[:12])
        cipher.update(f'anytube:1:{owner()}:{identifier}'.encode())
        return json.loads(cipher.decrypt_and_verify(raw[28:], raw[12:28]))
    except (ValueError, KeyError):
        raise HTTPException(503, 'Cet accès ne peut pas être déchiffré. Vérifiez la clé du coffre.')


def credential_revision(config):
    def one(identifier):
        if not identifier:
            return ''
        try:
            return row(identifier)['revision']
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            return 'revoked'
    identifier = config.get('credential_id')
    primary = one(identifier)
    media = one(config.get('media_credential_id'))
    return primary + ('|'+media if media else '')


def metadata(entry):
    return {k: entry[k] for k in ('id', 'name', 'kind', 'revision', 'updated')}


@router.get('/api/credentials')
def listing():
    with connect() as db:
        entries = [metadata(dict(r)) for r in db.execute('SELECT * FROM credentials WHERE owner=? ORDER BY name', (owner(),))]
    try:
        key()
        ready = True
    except HTTPException:
        ready = False
    return {'items': entries, 'ready': ready}


def save(body, identifier):
    encrypted = encrypt(identifier, body.model_dump())
    with connect() as db:
        db.execute('INSERT INTO credentials VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(owner,id) DO UPDATE SET name=excluded.name,kind=excluded.kind,encrypted=excluded.encrypted,revision=excluded.revision,updated=excluded.updated',
                   (owner(), identifier, body.name, body.kind, encrypted, secrets.token_hex(16), time.time(), 1))
    return metadata(row(identifier))


@router.post('/api/credentials', status_code=201)
def create(body: Credential):
    with connect() as db:
        if db.execute('SELECT count(*) FROM credentials WHERE owner=?', (owner(),)).fetchone()[0] >= 100:
            raise HTTPException(400, 'Limite de 100 accès atteinte.')
    return save(body, secrets.token_hex(16))


@router.put('/api/credentials/{identifier}')
def replace(identifier: str, body: Credential):
    row(identifier)
    return save(body, identifier)


@router.delete('/api/credentials/{identifier}')
def delete(identifier: str):
    row(identifier)
    with connect() as db:
        db.execute('DELETE FROM credentials WHERE owner=? AND id=?', (owner(), identifier))
    return {'ok': True}


def scoped_headers(credential, url):
    """Only exact HTTPS domains receive headers, including after every redirect."""
    if not credential:
        return {}
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in credential['domains']:
        return {}
    if credential['kind'] == 'bearer':
        return {'Authorization': 'Bearer ' + credential['value']}
    if credential['kind'] == 'api_key':
        return {credential['header']: credential['value']}
    if credential['kind'] == 'cookies':
        cookies = []
        for domain, include, path, secure, expiry, name, value in cookie_records(credential['value'], credential['domains']):
            matches = parts.hostname == domain.lstrip('.') or include == 'TRUE' and parts.hostname.endswith('.'+domain.lstrip('.'))
            if (matches and (not int(expiry) or int(expiry) > time.time())
                    and (parts.path == path or parts.path.startswith(path.rstrip('/') + '/'))):
                cookies.append(name + '=' + value)
        return {'Cookie': '; '.join(cookies)} if cookies else {}
    return {}
