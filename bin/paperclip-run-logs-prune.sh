#!/usr/bin/env bash
# Prunes Paperclip agent run-logs so they stop filling the boot volume.
#
# Run-logs (~/.paperclip/instances/<id>/data/run-logs/**/<run-id>.ndjson) grow at
# roughly 1.5-2 GB/day on a busy fleet and nothing rotates them, which is how the
# host hit ENOSPC (agent runs died mid-write).
#
# Policy:
#   * .ndjson files older than RETENTION_DAYS are tar.gz'd into ARCHIVE_DIR, then deleted.
#     Compression is ~20x, so history stays recoverable (`tar -xzf`) for cheap.
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
#   RUN_LOGS_DIR             default ~/.paperclip/instances/default/data/run-logs
#   ARCHIVE_DIR              default <run-logs>/../run-logs-archive
#   RETENTION_DAYS           default 2
#   ARCHIVE_RETENTION_DAYS   default 14

set -euo pipefail

RUN_LOGS_DIR="${RUN_LOGS_DIR:-$HOME/.paperclip/instances/default/data/run-logs}"
ARCHIVE_DIR="${ARCHIVE_DIR:-$(dirname "$RUN_LOGS_DIR")/run-logs-archive}"
RETENTION_DAYS="${RETENTION_DAYS:-2}"
ARCHIVE_RETENTION_DAYS="${ARCHIVE_RETENTION_DAYS:-14}"

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

log() { echo "$(date -Iseconds) [run-logs-prune] $*"; }
free_space() { df -h / | awk 'NR==2{print $4" free ("$5" used)"}'; }

if [[ ! -d "$RUN_LOGS_DIR" ]]; then
    log "no run-logs dir at $RUN_LOGS_DIR — nothing to do"
    exit 0
fi

log "start: $(free_space); retention=${RETENTION_DAYS}d archive_retention=${ARCHIVE_RETENTION_DAYS}d dry_run=$DRY_RUN"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
LIST="$WORK/old.txt"

cd "$RUN_LOGS_DIR"
find . -type f -name '*.ndjson' -mtime "+${RETENTION_DAYS}d" > "$LIST" || true
COUNT=$(wc -l < "$LIST" | tr -d ' ')

if [[ "$COUNT" -eq 0 ]]; then
    log "no .ndjson older than ${RETENTION_DAYS}d"
else
    BYTES=$(tr '\n' '\0' < "$LIST" | xargs -0 stat -f '%z' 2>/dev/null | awk '{s+=$1} END{printf "%.0f", s}')
    log "found $COUNT file(s), $((BYTES / 1024 / 1024)) MB older than ${RETENTION_DAYS}d"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        log "dry-run: would archive to $ARCHIVE_DIR and delete originals"
    else
        mkdir -p "$ARCHIVE_DIR"
        ARCHIVE="$ARCHIVE_DIR/run-logs-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
        tar -czf "$ARCHIVE" -T "$LIST"

        # Verify the archive holds every file before deleting anything.
        ARCHIVED=$(tar -tzf "$ARCHIVE" | wc -l | tr -d ' ')
        if [[ "$ARCHIVED" -ne "$COUNT" ]]; then
            log "ERROR: archive holds $ARCHIVED of $COUNT files — keeping originals" >&2
            exit 1
        fi

        tr '\n' '\0' < "$LIST" | xargs -0 rm -f
        log "archived $COUNT file(s) to $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1)) and removed originals"
    fi
fi

# Drop stale archives.
if [[ -d "$ARCHIVE_DIR" ]]; then
    OLD_ARCHIVES=$(find "$ARCHIVE_DIR" -type f -name 'run-logs-*.tar.gz' -mtime "+${ARCHIVE_RETENTION_DAYS}d" | wc -l | tr -d ' ')
    if [[ "$OLD_ARCHIVES" -gt 0 ]]; then
        if [[ "$DRY_RUN" -eq 1 ]]; then
            log "dry-run: would delete $OLD_ARCHIVES archive(s) older than ${ARCHIVE_RETENTION_DAYS}d"
        else
            find "$ARCHIVE_DIR" -type f -name 'run-logs-*.tar.gz' -mtime "+${ARCHIVE_RETENTION_DAYS}d" -delete
            log "deleted $OLD_ARCHIVES archive(s) older than ${ARCHIVE_RETENTION_DAYS}d"
        fi
    fi
fi

# Empty per-agent dirs left behind by deleted logs.
[[ "$DRY_RUN" -eq 0 ]] && find "$RUN_LOGS_DIR" -type d -empty -delete 2>/dev/null || true

log "done: $(free_space)"
