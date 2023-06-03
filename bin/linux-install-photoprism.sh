#!/bin/bash


if ! command -v podman; then
    apt install -yq podman
fi

podman run -d \
  --name photoprism \
  --privileged \
  --security-opt seccomp=unconfined \
  --security-opt apparmor=unconfined \
  -p 2342:2342 \
  -e PHOTOPRISM_UPLOAD_NSFW="true" \
  -e PHOTOPRISM_ADMIN_PASSWORD="insecure" \
  -v /photoprism/storage \
  -v /mnt:/photoprism/originals \
  photoprism/photoprism
