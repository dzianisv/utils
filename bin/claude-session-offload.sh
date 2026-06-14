#!/usr/bin/env bash
# Moves ~/.claude/projects/ dirs inactive >24h to external drive and symlinks back.
# Safe to run when drive is absent — skips gracefully.

set -euo pipefail

DEST="/Volumes/Dzianis-3/macbook2020/claude-sessions"
SRC="$HOME/.claude/projects"
CUTOFF=$(( $(date +%s) - 86400 ))
MOVED=0
SKIPPED=0

if [[ ! -d "/Volumes/Dzianis-3" ]]; then
    echo "$(date -Iseconds) [claude-offload] Drive not mounted, skipping." >&2
    exit 0
fi

mkdir -p "$DEST"

while IFS= read -r -d '' dir; do
    mtime=$(stat -f %m "$dir")
    if [[ "$mtime" -ge "$CUTOFF" ]]; then
        continue
    fi

    name=$(basename "$dir")
    target="$DEST/$name"

    if [[ -L "$dir" ]]; then
        # Already a symlink — check if target still exists
        if [[ ! -d "$target" ]]; then
            echo "$(date -Iseconds) [claude-offload] Dangling symlink $name, removing." >&2
            rm "$dir"
        fi
        continue
    fi

    if [[ -d "$target" ]]; then
        echo "$(date -Iseconds) [claude-offload] Conflict: $name already on drive, skipping." >&2
        (( SKIPPED++ )) || true
        continue
    fi

    mv "$dir" "$target"
    ln -s "$target" "$dir"
    echo "$(date -Iseconds) [claude-offload] Moved $name"
    (( MOVED++ )) || true
done < <(find "$SRC" -maxdepth 1 -mindepth 1 -type d -print0)

echo "$(date -Iseconds) [claude-offload] Done. Moved=$MOVED Skipped=$SKIPPED"
