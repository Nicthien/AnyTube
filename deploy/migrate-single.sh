#!/bin/bash
set -euo pipefail
release=/mnt/user/appdata/anytube/releases/single-preview
project=/boot/config/plugins/compose.manager/projects/anytube
deploy=/mnt/user/appdata/anytube/deploy
docker build -t anytube:single "$release"
docker exec anytube-backup-1 python -m app.backups
cp "$project/docker-compose.yml" "$deploy/before-single-compose.yml"
docker tag anytube:family anytube:family-multi-previous
rollback() {
  echo 'Migration failed: restoring previous AnyTube services.'
  docker compose -f "$project/docker-compose.yml" down --remove-orphans || true
  docker tag anytube:family-multi-previous anytube:family
  cp "$deploy/before-single-compose.yml" "$project/docker-compose.yml"
  docker compose -f "$project/docker-compose.yml" up -d --no-build
}
trap rollback ERR
docker compose -f "$project/docker-compose.yml" stop
docker tag anytube:single anytube:family
cat > "$project/docker-compose.yml" <<'YAML'
include:
  - path: /mnt/user/appdata/anytube/releases/single-preview/compose.unraid.yaml
    env_file: /mnt/user/appdata/anytube/releases/single-preview/.env
YAML
docker compose -f "$project/docker-compose.yml" up -d --no-build --remove-orphans --wait --wait-timeout 90
docker exec -e PYTHONPATH=/app anytube-anytube-1 setpriv --reuid 10001 --regid 10001 --clear-groups --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs python /configuration/deploy/check-single.py > "$deploy/single-verification.json"
docker exec -u 10001:10001 anytube-anytube-1 python -m app.backups
trap - ERR
docker ps -a --filter label=com.docker.compose.project=anytube --format '{{.Names}} {{.Status}}'
