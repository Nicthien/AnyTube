"""Versioned connector evidence; a successful search never certifies playback."""
import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from yt_dlp.version import __version__
from app.store import connect, owner
from app.pagination import signature
from app.vault import credential_revision
from app.registry import FEATURES
import os


@lru_cache(maxsize=1)
def engine_version():
    # Line endings are normalised: the same code must yield the same revision on any
    # checkout, otherwise a Windows clone would declare every stored proof obsolete.
    root = Path(__file__).parent
    return hashlib.sha256(b''.join((root / name).read_bytes().replace(b'\r\n', b'\n') for name in
        ('connectors.py', 'worker.py', 'catalog.py', 'pagination.py', 'verification.py', 'registry.py', 'vault.py', 'failures.py', 'adapters.py', 'access.py', 'discovery.py', 'relay.py', 'playback.py', 'main.py', 'library.py', 'egress.py', 'static/playback.js', 'static/vendor/shaka-player.js'))).hexdigest()[:16]


def revision(config):
    return signature([config, engine_version(), __version__, credential_revision(config)])


def record(config, query, status, count=0, detail='', *, feature='search', environment=None):
    if feature not in FEATURES:
        raise ValueError('Fonction de vérification inconnue.')
    value = {'date': datetime.now(timezone.utc).isoformat(), 'yt_dlp': __version__,
             'connector_version': engine_version(), 'configuration_revision': signature(config),
             'credential_revision': credential_revision(config),
             'environment': environment or os.environ.get('ANYTUBE_ENVIRONMENT', 'local'),
             'feature': feature, 'query': query, 'status': status, 'count': count, 'detail': detail}
    with connect() as db:
        db.execute('INSERT INTO feature_evidence(owner,revision,feature,payload) VALUES (?,?,?,?)',
                   (owner(), revision(config), feature, json.dumps(value)))
    return value


def evidence(config):
    with connect() as db:
        rows = db.execute('SELECT payload FROM feature_evidence WHERE owner=? AND revision=? ORDER BY id DESC LIMIT 100', (owner(), revision(config))).fetchall()
    return [json.loads(row['payload']) for row in reversed(rows)]


def history(config):
    current = revision(config)
    config_signature = signature(config)
    with connect() as db:
        rows = db.execute('SELECT revision,payload FROM feature_evidence WHERE owner=? ORDER BY id DESC LIMIT 2000', (owner(),)).fetchall()
        legacy = db.execute('SELECT payload FROM verifications WHERE owner=?', (owner(),)).fetchall()
    results = [{**json.loads(row['payload']), 'obsolete': row['revision'] != current} for row in rows
               if json.loads(row['payload']).get('configuration_revision') == config_signature]
    for row in legacy:
        data = json.loads(row['payload'])
        results.extend({**value, 'obsolete': True, 'legacy': True} for value in data if isinstance(value, dict)
                       and value.get('configuration_revision') == config_signature)
    return results[:200]


def differences(current, delivered, prefix=''):
    result = []
    for key in sorted(set(current) | set(delivered)):
        before, after = current.get(key), delivered.get(key)
        name = f'{prefix}{key}'
        if isinstance(before, dict) and isinstance(after, dict):
            result.extend(differences(before, after, name + '.'))
        elif before != after:
            result.append({'field': name, 'current': before, 'delivered': after})
    return result
