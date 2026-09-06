"""Read-only deployed-container checks. Does not create a family account."""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from app.connectors import default_connector
from app.verification import engine_version
from yt_dlp.version import __version__

result = {'yt_dlp': __version__, 'connector_version': engine_version(), 'searches': []}
for query in ('chat', 'nature'):
    payload = {'mode':'search', 'source':'Dailymotion', 'connector':default_connector('Dailymotion'), 'query':query, 'limit':10}
    process = subprocess.run([sys.executable, '-m', 'app.worker'], input=json.dumps(payload), capture_output=True, text=True, timeout=65)
    response = json.loads(process.stdout)
    result['searches'].append({'source':'Dailymotion', 'query':query, 'count':len(response.get('items',[])), 'ok':process.returncode == 0})
for label, url in (('private_proxy', 'http://192.168.0.5/'), ('metadata_proxy', 'http://169.254.169.254/')):
    try:
        urllib.request.urlopen(url, timeout=5).close()
        result[label] = 'unexpectedly_allowed'
    except urllib.error.HTTPError as exc:
        result[label] = exc.code
try:
    socket.create_connection(('192.168.0.5',80),timeout=3).close()
    result['private_direct'] = 'unexpectedly_allowed'
except OSError:
    result['private_direct'] = 'blocked'
with sqlite3.connect(Path(os.environ['ANYTUBE_DATA'])/'anytube.db') as db:
    result['integrity'] = db.execute('PRAGMA integrity_check').fetchone()[0]
    result['source_count'] = db.execute('SELECT COUNT(*) FROM sources').fetchone()[0]
    result['account_count'] = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
print(json.dumps(result, ensure_ascii=False, indent=2))
