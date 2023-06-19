#!/bin/bash
set -eu

host=${1:?first argument is not set to the remote host}
script=${2:?second argument is not set to the script path}
name=$(uuidgen)

ssh-copy-id "$host"
scp "${script}" "${host}":/tmp/$name
ssh "${host}" sh -c "bash /tmp/$name; rm /tmp/$name"
