#!/usr/bin/env bash
# Prunes Paperclip agent run-logs so they stop filling the boot volume.
#
# Run-logs (~/.paperclip*/instances/*/data/run-logs/**/<run-id>.ndjson) grow at
# roughly 1.5-2 GB/day on a busy fleet and nothing rotates them, which is how the
# host hit ENOSPC (agent runs died mid-write).
#
# Policy:
#   * .ndjson files older than RETENTION_DAYS are tar.gz'd into <instance>/data/run-logs-archive,
#     then deleted. Compression is ~20x, so history stays recoverable (`tar -xzf`) for cheap.
#   * archives older than ARCHIVE_RETENTION_DAYS are deleted.
#
# Live runs are never touched: an in-flight run appends to its .ndjson continuously,
# so its mtime is always "now" and it can never match an mtime-based age filter of
# >= 1 day. Nothing is deleted until the archive has been written and verified.
#
# Usage:
#   paperclip-run-logs-prune.sh [--dry-run]
#
# Env overrides:
#   RUN_LOGS_DIR             default: every ~/.paperclip*/instances/*/data/run-logs
#   ARCHIVE_DIR              default <run-logs>/../run-logs-archive
#   RETENTION_DAYS           default 2
#   ARCHIVE_RETENTION_DAYS   default 14

set -euo pipefail

RETENTION_DAYS="${RETENTION_DAYS:-2}"
ARCHIVE_RETENTION_DAYS="${ARCHIVE_RETENTION_DAYS:-14}"
ARCHIVE_DIR_OVERRIDE="${ARCHIVE_DIR:-}"

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

log() { echo "$(date -Iseconds) [run-logs-prune] $*"; }
free_space() { df -h / | awk 'NR==2{print $4" free ("$5" used)"}'; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
LIST="$WORK/old.txt"

prune_dir() {
    local run_logs_dir="$1"
    local archive_dir="${ARCHIVE_DIR_OVERRIDE:-$(dirname "$run_logs_dir")/run-logs-archive}"
    local count bytes archive archived old_archives

    log "dir: $run_logs_dir"
    cd "$run_logs_dir"

    find . -type f -name '*.ndjson' -mtime "+${RETENTION_DAYS}d" > "$LIST" || true
    count=$(wc -l < "$LIST" | tr -d ' ')

    if [[ "$count" -eq 0 ]]; then
        log "  no .ndjson older than ${RETENTION_DAYS}d"
    else
        bytes=$(tr '\n' '\0' < "$LIST" | xargs -0 stat -f '%z' 2>/dev/null | awk '{s+=$1} END{printf "%.0f", s}')
        log "  found $count file(s), $((bytes / 1024 / 1024)) MB older than ${RETENTION_DAYS}d"

        if [[ "$DRY_RUN" -eq 1 ]]; then
            log "  dry-run: would archive to $archive_dir and delete originals"
        else
            mkdir -p "$archive_dir"
            archive="$archive_dir/run-logs-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
            tar -czf "$archive" -T "$LIST"

            # Verify the archive holds every file before deleting anything.
            archived=$(tar -tzf "$archive" | wc -l | tr -d ' ')
            if [[ "$archived" -ne "$count" ]]; then
                log "  ERROR: archive holds $archived of $count files — keeping originals" >&2
                return 1
            fi

            tr '\n' '\0' < "$LIST" | xargs -0 rm -f
            log "  archived $count file(s) to $archive ($(du -h "$archive" | cut -f1)) and removed originals"
        fi
    fi

    # Drop stale archives.
    if [[ -d "$archive_dir" ]]; then
        old_archives=$(find "$archive_dir" -type f -name 'run-logs-*.tar.gz' -mtime "+${ARCHIVE_RETENTION_DAYS}d" | wc -l | tr -d ' ')
        if [[ "$old_archives" -gt 0 ]]; then
            if [[ "$DRY_RUN" -eq 1 ]]; then
                log "  dry-run: would delete $old_archives archive(s) older than ${ARCHIVE_RETENTION_DAYS}d"
            else
                find "$archive_dir" -type f -name 'run-logs-*.tar.gz' -mtime "+${ARCHIVE_RETENTION_DAYS}d" -delete
                log "  deleted $old_archives archive(s) older than ${ARCHIVE_RETENTION_DAYS}d"
            fi
        fi
    fi

    # Empty per-agent dirs left behind by deleted logs (never the root itself).
    if [[ "$DRY_RUN" -eq 0 ]]; then
        find "$run_logs_dir" -mindepth 1 -type d -empty -delete 2>/dev/null || true
    fi
}

# One host can run several Paperclip instances (~/.paperclip, ~/.paperclip-tailnet, …).
DIRS=()
if [[ -n "${RUN_LOGS_DIR:-}" ]]; then
    DIRS=("$RUN_LOGS_DIR")
else
    while IFS= read -r d; do DIRS+=("$d"); done < <(ls -d "$HOME"/.paperclip*/instances/*/data/run-logs 2>/dev/null || true)
fi

if [[ "${#DIRS[@]}" -eq 0 ]]; then
    log "no run-logs dirs found — nothing to do"
    exit 0
fi

log "start: $(free_space); retention=${RETENTION_DAYS}d archive_retention=${ARCHIVE_RETENTION_DAYS}d dry_run=$DRY_RUN"

for dir in "${DIRS[@]}"; do
    [[ -d "$dir" ]] || continue
    prune_dir "$dir"
done

log "done: $(free_space)"
