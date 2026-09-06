"""Run inside the single container as UID 10001; no real user data mutation."""
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from app.connectors import default_connector

os.environ.update(ANYTUBE_PROXY='http://127.0.0.1:3128', HTTPS_PROXY='http://127.0.0.1:3128', HTTP_PROXY='http://127.0.0.1:3128')
result = {}
for label, address in [('lan', ('192.168.0.5',80)), ('metadata', ('169.254.169.254',80)), ('public_direct', ('1.1.1.1',443)), ('local_api', ('127.0.0.1',8000))]:
    try:
        socket.create_connection(address, timeout=2).close()
        result[label] = 'ALLOWED'
    except OSError:
        result[label] = 'blocked'
    assert result[label] == 'blocked', result
for name, url in [('private_proxy','http://192.168.0.5/'),('ipv6_proxy','http://[::1]/'),('metadata_proxy','http://169.254.169.254/')]:
    try:
        urllib.request.urlopen(url,timeout=10).close()
        raise AssertionError(name)
    except urllib.error.HTTPError as exc:
        assert exc.code == 403, exc.code
        result[name] = exc.code
with urllib.request.urlopen('https://api.dailymotion.com/videos?limit=1', timeout=30) as response:
    result['public_https'] = response.status
payload = {'mode':'search','source':'Dailymotion','connector':default_connector('Dailymotion'),'query':'chat','limit':10}
job = subprocess.run([sys.executable,'-m','app.worker'],input=json.dumps(payload),capture_output=True,text=True,timeout=90)
assert job.returncode == 0, job.stderr
result['search_count'] = len(json.loads(job.stdout).get('items',[]))
assert result['search_count'] > 0
for line in open('/proc/self/status'):
    if line.startswith(('Uid:', 'CapEff:', 'CapBnd:', 'NoNewPrivs:')):
        result[line.split(':')[0]] = line.split(':')[1].strip()
assert int(result['CapEff'],16) == 0
assert int(result['CapBnd'],16) == 0
print(json.dumps(result,indent=2))
