"""Explicit one-time initialization; never replace a key needed by existing credentials."""
import argparse
import os
from pathlib import Path
import secrets

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    args.path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as target:
        target.write(secrets.token_bytes(32))
    print('Clé créée. Conservez une copie sécurisée séparée des sauvegardes SQLite.')
