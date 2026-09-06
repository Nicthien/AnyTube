"""Consistent SQLite backups; media files remain on their persistent volume."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import os
from pathlib import Path
import sqlite3
import time
import zipfile


def backup(source,target):
    target.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    result=target/f'anytube-{stamp}.db'
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src, closing(sqlite3.connect(result)) as dest:
        src.backup(dest)
        if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Sauvegarde invalide')
    os.chmod(result,0o600)
    configuration = os.environ.get('ANYTUBE_CONFIG')
    if configuration:
        archive = result.with_suffix('.config.zip')
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as saved:
            for name in ('.env', 'compose.unraid.yaml', 'deploy/nginx.conf', 'requirements.lock'):
                source_file = Path(configuration) / name
                if source_file.is_file(): saved.write(source_file, name)
        os.chmod(archive, 0o600)
    for old in sorted(target.glob('anytube-*.db'))[:-7]:
        old.unlink()
        old.with_suffix('.config.zip').unlink(missing_ok=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--daily',action='store_true');parser.add_argument('--output',default='/backups');args=parser.parse_args()
    while True:
        source=Path(os.environ.get('ANYTUBE_DATA','data')).resolve()/'anytube.db'
        if source.exists():
            print(backup(source,Path(args.output).resolve()),flush=True)
        if not args.daily:break
        time.sleep(86400 if source.exists() else 60)
