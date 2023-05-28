#!/bin/sh

# This shell script is designed to automate the process the openwrt configuration backup
# by initializing a Git repository,
# committing and pushing the initial configuration files to the repository,
# and setting up a cron job to periodically update the repository with any changes made to the configuration files.

if [[ -z "${URL:-}" ]]; then
    echo -n "Type in a git remote URL: "
    read URL
fi

if ! command -v git; then
    opkg update
    opkg install git-http ca-bundle
fi

cd /etc/config
if [[ ! -d .git ]]; then
    git init --initial-branch=main
    git config user.name $(uci get system.@system[0].hostname)
    git config user.email "$USER@$(uci get system.@system[0].hostname)"
    git remote add origin "$URL"
    git add --all
    git commit -am 'Initial commit'
    git push origin HEAD
fi

# Create the cron job
echo "0 * * * * sh -c 'cd /etc/config && git commit -am 'Update configs $(date)'; git push origin HEAD; git pull origin main" >> /etc/crontabs/root

# Restart the cron service
/etc/init.d/cron restart

