import os
import json
from contextlib import contextmanager, closing
import sqlite3
from pathlib import Path
from contextvars import ContextVar

current_user = ContextVar('anytube_user', default='')


def owner():
    return current_user.get()


def data_dir():
    return Path(os.environ.get('ANYTUBE_DATA', 'data')).resolve()


@contextmanager
def connect():
    data_dir().mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(data_dir() / 'anytube.db', timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize():
    path = data_dir() / 'anytube.db'
    if path.exists():
        with closing(sqlite3.connect(path)) as source:
            columns = {row[1] for row in source.execute('PRAGMA table_info(sources)')}
            backup = path.with_name('before-family.db')
            if columns and 'owner' not in columns and not backup.exists():
                with closing(sqlite3.connect(backup)) as target:
                    source.backup(target)
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)')
        db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        if 'connector' not in {row['name'] for row in db.execute('PRAGMA table_info(sources)')}:
            db.execute('ALTER TABLE sources ADD COLUMN connector TEXT')
        if not db.execute("SELECT 1 FROM settings WHERE key='initialized'").fetchone():
            db.executemany('INSERT OR IGNORE INTO sources(id,name) VALUES (?,?)', [('Youtube', 'YouTube'), ('Dailymotion', 'Dailymotion')])
            db.execute("INSERT INTO settings VALUES ('initialized','1')")
        if 'owner' not in {row['name'] for row in db.execute('PRAGMA table_info(sources)')}:
            db.execute('ALTER TABLE sources RENAME TO legacy_sources')
            db.execute("CREATE TABLE sources(id TEXT NOT NULL,name TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,connector TEXT,owner TEXT NOT NULL,PRIMARY KEY(owner,id))")
            db.execute("INSERT INTO sources SELECT id,name,enabled,connector,'' FROM legacy_sources")
            db.execute('DROP TABLE legacy_sources')
        db.execute('CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE COLLATE NOCASE,password TEXT NOT NULL,admin INTEGER NOT NULL DEFAULT 0,disabled INTEGER NOT NULL DEFAULT 0,quota INTEGER NOT NULL DEFAULT 21474836480,prefs TEXT NOT NULL DEFAULT \'{}\')')
        db.execute('CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,owner TEXT NOT NULL,expires REAL NOT NULL,created REAL NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS invitations(token TEXT PRIMARY KEY,expires REAL NOT NULL,created REAL NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,until REAL NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY,owner TEXT NOT NULL,payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS personal(owner TEXT NOT NULL,url TEXT NOT NULL,title TEXT NOT NULL DEFAULT \'\',favorite INTEGER NOT NULL DEFAULT 0,position REAL NOT NULL DEFAULT 0,updated REAL NOT NULL,PRIMARY KEY(owner,url))')
        db.execute('CREATE TABLE IF NOT EXISTS verifications(owner TEXT NOT NULL,signature TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(owner,signature))')
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        db.execute('CREATE TABLE IF NOT EXISTS credentials(owner TEXT NOT NULL,id TEXT NOT NULL,name TEXT NOT NULL,kind TEXT NOT NULL,encrypted TEXT NOT NULL,revision TEXT NOT NULL,updated REAL NOT NULL,version INTEGER NOT NULL,PRIMARY KEY(owner,id))')
        db.execute('CREATE TABLE IF NOT EXISTS feature_evidence(id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,revision TEXT NOT NULL,feature TEXT NOT NULL,payload TEXT NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS feature_evidence_owner ON feature_evidence(owner,revision)')
        db.execute('INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)')


def saved_sources():
    from app.connectors import default_connector
    with connect() as db:
        items = [dict(row) for row in db.execute('SELECT * FROM sources WHERE owner=? ORDER BY name COLLATE NOCASE', (owner(),))]
    for item in items:
        item['connector'] = json.loads(item['connector']) if item['connector'] else default_connector(item['id'])
    return items
