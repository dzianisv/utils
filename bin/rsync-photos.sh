#!/bin/bash
set -eu
SSH_HOST=${SSH_HOST:-root@rpi4.local}
exec rsync --progress -rtl --remove-source-files -e "ssh -c chacha20-poly1305@openssh.com" ~/Desktop/PhotoDump/ $HOST:/media/External5TB/Photography/