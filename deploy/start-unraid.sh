#!/bin/bash
set -euo pipefail
release=/mnt/user/appdata/anytube/releases/single-preview
project=/boot/config/plugins/compose.manager/projects/anytube
test -f "$project/docker-compose.yml"
if test -f "$release/anytube-family.tar"; then
  docker load -i "$release/anytube-family.tar"
fi
docker build -t anytube:family "$release"
cd "$project"
docker compose config --quiet
docker compose up -d --no-build --wait
docker compose ps
