#!/bin/bash
set -euo pipefail
test "$(docker inspect anytube-anytube-1 --format '{{.State.Health.Status}}')" = healthy
for network in anytube_private anytube_inbound anytube_outbound; do
  if docker network inspect "$network" >/dev/null 2>&1; then docker network rm "$network"; fi
done
docker ps -a --filter label=com.docker.compose.project=anytube --format '{{.Names}} {{.Status}}'
docker exec -u 10001:10001 anytube-anytube-1 python -c "import sqlite3; db=sqlite3.connect('/data/anytube.db'); print('database',db.execute('pragma integrity_check').fetchone()[0]); print('accounts',db.execute('select count(*) from users').fetchone()[0]); print('sources',db.execute('select count(*) from sources').fetchone()[0])"
docker image inspect anytube:family --format '{{.Id}}' > /mnt/user/appdata/anytube/deploy/image-id.txt
