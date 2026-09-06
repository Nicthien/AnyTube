#!/bin/bash
set -euo pipefail
cd /boot/config/plugins/compose.manager/projects/anytube
docker compose exec -u 10001:10001 anytube python -m app.backups
docker tag anytube:family anytube:family-previous
docker compose build anytube
docker compose up -d --no-build --wait
docker compose exec -u 10001:10001 anytube python -m app.backups
docker image inspect anytube:family --format '{{.Id}}' > /mnt/user/appdata/anytube/deploy/image-id.txt
docker compose ps
