#!/bin/bash
set -euo pipefail

if ! command -v podman; then
    apt install -yq podman
fi

if [[ -z "${PASSWORD:-}" ]]; then
  echo -n "Type admin password: "
  read -s PASSWORD
fi

podman run -d \
  --name photoprism \
  --privileged \
  --security-opt seccomp=unconfined \
  --security-opt apparmor=unconfined \
  -p 2342:2342 \
  -e PHOTOPRISM_UPLOAD_NSFW="true" \
  -e PHOTOPRISM_ADMIN_PASSWORD="$PASSWORD" \
  -v /photoprism/storage \
  -v /media/$USER/:/photoprism/originals \
  docker.io/photoprism/photoprism

podman generate systemd --name photoprism --new > /etc/systemd/system/photoprism.service
systemctl daemon-reload
systemctl enable photoprism
systemctl start photoprism