#!/bin/bash
set -eu

cat << EOF > /etc/systemd/system/autorsync.service
[Unit]
Description=Auto Rsync
After=network.target

[Service]
User=root
EnvironmentFile=/etc/autorsync.conf
ExecStart=/usr/bin/bash -c 'while true; do /usr/local/bin/autorsync.sh; sleep 3600; done'
Restart=always

[Install]
WantedBy=multi-user.target
EOF

touch /etc/autorsync.conf

cat << 'EOF' > /usr/local/bin/autorsync.sh
#!/bin/bash
set -eu

/usr/local/bin/automount.sh || :


notify() {
    echo "$*"

    if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] && [[ -n "${TELEGRAM_CHAT_ID:-}" ]]; then
        TEXT=$(printf "%s" "$*" | jq -sRr @uri)
        curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage?chat_id=$TELEGRAM_CHAT_ID&text=$TEXT"
    fi
}

my_rsync() {

  rsync -r -t -l --progress -e "ssh -o Ciphers=chacha20-poly1305@openssh.com" "$@"
  return $?
}

if ! mount | grep "${AUTORSYNC_DST%/}" && ! mount | grep "${AUTORSYNC_SRC%/}"; then
  notify "[$(hostname)] $AUTORSYNC_SRC and $AUTORSYNC_DST are not mounted, skipping rsync"
  exit 0
fi

notify "[$(hostname)] rsync $@: started"
my_rsync $AUTORSYNC_SRC $AUTORSYNC_DST
notify "[$(hostname)] rsync $@ done: $?"

EOF

chmod a+x /usr/local/bin/autorsync.sh

cat << 'EOF' > /usr/local/bin/automount.sh
#!/bin/bash

lsblk -o PATH,MOUNTPOINT | while read -r device_path mountpoint; do
    if [ -z "$mountpoint" ]; then
        # Mount the device using udisksctl
        udisksctl mount -b "$device_path"
    fi
done
EOF

chmod a+x /usr/local/bin/automount.sh

systemctl daemon-reload
systemctl enable --now autorsync.service
journalctl -fu autorsync.service