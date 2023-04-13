#!/bin/bash
set -eu

host=${1:-bananapi.local}
user=root
ssh-copy-id "${user}@$host"

scp $(dirname $0)/armbian-bootstrap-local.sh "${user}@${host}":/tmp/bootstrap.sh
ssh "${user}@${host}" sh -c "/tmp/boostrap.sh; rm /tmp/boostrap.sh"
