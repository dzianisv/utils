#!/usr/bin/env bash
# Offloads inactive Claude sessions to external drive and purges safe local caches.
# Safe to run when drive is absent — session offload skips gracefully.

set -euo pipefail

log() { echo "$(date -Iseconds) [claude-offload] $*"; }

# ── 1. Purge safe local caches (always, drive not required) ──────────────────

purge_cache() {
    local path="$1" label="$2"
    if [[ -e "$path" ]]; then
        rm -rf "$path"
        log "purged $label"
    fi
}

purge_cache ~/Library/Caches/ms-playwright                          "playwright"
purge_cache ~/Library/Caches/com.microsoft.VSCode.ShipIt           "vscode-shipit"
purge_cache ~/Library/Caches/claude-cli-nodejs                     "claude-cli-nodejs"
purge_cache "$HOME/Library/Application Support/Claude/Cache"        "claude-app-cache"
purge_cache "$HOME/Library/Application Support/Claude/Code Cache"   "claude-code-cache"
purge_cache "$HOME/Library/Application Support/Claude/vm_bundles/warm" "claude-vm-warm"
purge_cache ~/.npm                                                  "npm"

# ── 2. Offload ~/.claude/projects/ dirs inactive >24h ────────────────────────

DEST="/Volumes/Dzianis-3/macbook2020/claude-sessions"
SRC="$HOME/.claude/projects"
CUTOFF=$(( $(date +%s) - 86400 ))
MOVED=0
SKIPPED=0

if [[ ! -d "/Volumes/Dzianis-3" ]]; then
    log "Drive not mounted — skipping session offload." >&2
else
    mkdir -p "$DEST"

    while IFS= read -r -d '' dir; do
        mtime=$(stat -f %m "$dir")
        if [[ "$mtime" -ge "$CUTOFF" ]]; then
            continue
        fi

        name=$(basename "$dir")
        target="$DEST/$name"

        if [[ -L "$dir" ]]; then
            if [[ ! -d "$target" ]]; then
                log "Dangling symlink $name, removing." >&2
                rm "$dir"
            fi
            continue
        fi

        if [[ -d "$target" ]]; then
            log "Conflict: $name already on drive, skipping." >&2
            (( SKIPPED++ )) || true
            continue
        fi

        mv "$dir" "$target"
        ln -s "$target" "$dir"
        log "Moved $name"
        (( MOVED++ )) || true
    done < <(find "$SRC" -maxdepth 1 -mindepth 1 -type d -print0)
fi

log "Done. Moved=$MOVED Skipped=$SKIPPED"
log "Disk: $(df -h / | awk 'NR==2{print $4" free ("$5" used)"}')"
