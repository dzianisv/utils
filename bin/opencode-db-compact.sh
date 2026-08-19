#!/usr/bin/env bash
# Compacts ~/.local/share/opencode/opencode.db via VACUUM INTO + a guarded
# atomic swap, recovering unreclaimed SQLite freelist pages without deleting
# any rows.
#
# Background: opencode never vacuums its own db (auto_vacuum=0). AGE-507
# found ~58.6% of the file was reclaimable freelist pages; a VACUUM INTO test
# took a backup copy from 3.91G -> 1.54G with integrity_check: ok and zero
# row-count drift. Design/decision record: AGE-517. Implementation ticket:
# AGE-518.
#
# The one hard problem: this file has exactly one live writer today, and
# it's the founder's interactive `opencode` CLI session, not a service we
# control the lifecycle of. VACUUM INTO is a read-only snapshot and is safe
# to run concurrently, but the atomic *swap* afterward is not: if opencode
# still holds the old file open when we swap, its next write goes to an
# orphaned inode and is silently lost. So the swap step refuses to run
# whenever a live opencode process holds the db open — it skips cleanly
# (exit 0) rather than forcing/prompting the human to close their terminal.
#
# Explicitly out of scope (see AGE-518):
#   - any row-level deletion / `opencode session delete` automation
#   - any scheduling/cron/routine wiring (this script is invoked manually
#     until a follow-up ticket wires up a schedule)
#   - running this script against the live file as part of shipping it
#     (dry-run against the live file is fine and is how you check status)
#
# Usage:
#   opencode-db-compact.sh              # compact (or skip) for real
#   opencode-db-compact.sh --check      # dry-run: report only, no writes
#   opencode-db-compact.sh --dry-run    # alias for --check
#
# Env overrides:
#   OPENCODE_DB_PATH          default: ~/.local/share/opencode/opencode.db
#   OPENCODE_DB_BACKUP_DIR    default: <db dir>/opencode-db-backups
#                             (kept on the same filesystem as the db so the
#                             pre-swap backup is an instant rename, not a copy)
#   OPENCODE_DB_KEEP_BACKUPS  default: 5 (pre-swap backup sets to retain)
#
# Exit codes:
#   0   compacted, or cleanly skipped (opencode running, or check mode)
#   !=0 aborted: missing db/tooling, or the compacted copy failed
#       verification (integrity_check or row-count mismatch) — nothing is
#       swapped and the temp file is removed

set -euo pipefail

DB_PATH="${OPENCODE_DB_PATH:-$HOME/.local/share/opencode/opencode.db}"
BACKUP_DIR="${OPENCODE_DB_BACKUP_DIR:-$(dirname "$DB_PATH")/opencode-db-backups}"
KEEP_BACKUPS="${OPENCODE_DB_KEEP_BACKUPS:-5}"

MODE="run"
case "${1:-}" in
    --check | --dry-run) MODE="check" ;;
    -h | --help)
        sed -n '2,40p' "$0"
        exit 0
        ;;
    "") ;;
    *)
        echo "unknown argument: $1 (use --check/--dry-run)" >&2
        exit 2
        ;;
esac

log() { echo "$(date -Iseconds) [opencode-db-compact] $*"; }

file_size() {
    stat -f '%z' "$1" 2>/dev/null || stat -c '%s' "$1"
}

# Step 1 (and step 4, re-checked immediately before swap): refuses to
# proceed if a live opencode process holds the db open. Detection is
# deliberately OR'd across two independent signals (lsof on the db path,
# pgrep for the opencode binary) since either alone can miss edge cases
# (lsof missing/unprivileged, or a process holding the file without it
# showing as "opencode" in some exotic exec case).
has_live_holder() {
    if command -v lsof >/dev/null 2>&1 && lsof -- "$DB_PATH" >/dev/null 2>&1; then
        return 0
    fi
    if command -v pgrep >/dev/null 2>&1 && pgrep -x opencode >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

get_table_counts() {
    # Emits "table:count" for the tables we guarantee zero data loss on.
    # Reads all three in one connection/invocation to keep the snapshot as
    # tight as possible.
    local db="$1"
    sqlite3 "$db" <<'SQL'
.mode list
SELECT 'session:' || count(*) FROM session;
SELECT 'message:' || count(*) FROM message;
SELECT 'part:' || count(*) FROM part;
SQL
}

if ! command -v sqlite3 >/dev/null 2>&1; then
    log "ERROR: sqlite3 not found on PATH"
    exit 1
fi

if [[ ! -f "$DB_PATH" ]]; then
    log "ERROR: db not found at $DB_PATH"
    exit 1
fi

CURRENT_SIZE="$(file_size "$DB_PATH")"

if [[ "$MODE" == "check" ]]; then
    log "check: db=$DB_PATH current_size=${CURRENT_SIZE} bytes"
    if has_live_holder; then
        log "check: would SKIP — opencode running (holds $DB_PATH open)"
    else
        log "check: would COMPACT — no live opencode holder detected"
    fi

    # Three independent command substitutions rather than one `read` fed by
    # a piped/tr'd multi-line output: `read` returns non-zero when its input
    # doesn't end in a newline (which `tr '\n' ' '` produces), which under
    # `set -e` would silently kill the script right here.
    PAGE_SIZE="$(sqlite3 "$DB_PATH" "PRAGMA page_size;")"
    PAGE_COUNT="$(sqlite3 "$DB_PATH" "PRAGMA page_count;")"
    FREELIST_COUNT="$(sqlite3 "$DB_PATH" "PRAGMA freelist_count;")"
    PROJECTED_SIZE=$(((PAGE_COUNT - FREELIST_COUNT) * PAGE_SIZE))
    log "check: page_size=${PAGE_SIZE} page_count=${PAGE_COUNT} freelist_count=${FREELIST_COUNT}"
    log "check: projected size after compaction ~= ${PROJECTED_SIZE} bytes (no writes performed — dry-run only)"
    exit 0
fi

# --- real run ---

# Temp file must live on the same filesystem as DB_PATH so the eventual
# `mv` into place is an atomic rename, not a cross-device copy.
TMP_DB="$(dirname "$DB_PATH")/.opencode-db-compact.$$.tmp"
cleanup() { rm -f "$TMP_DB"; }
trap cleanup EXIT

log "start: db=$DB_PATH current_size=${CURRENT_SIZE} bytes"

# Step 1: pre-check before doing any work at all — avoids burning a VACUUM
# INTO pass (which reads the whole file) when we already know we can't swap.
if has_live_holder; then
    log "skipped: opencode running"
    exit 0
fi

# Step 2: VACUUM INTO a compacted copy. Read-only w.r.t. the source; safe to
# run concurrently with the live writer per SQLite's WAL semantics.
rm -f "$TMP_DB"
if ! sqlite3 "$DB_PATH" "VACUUM INTO '${TMP_DB}';"; then
    log "ERROR: VACUUM INTO failed — aborting, no swap"
    exit 1
fi

# Step 3: verify the compacted copy before trusting it with anything.
INTEGRITY="$(sqlite3 "$TMP_DB" "PRAGMA integrity_check;")"
if [[ "$INTEGRITY" != "ok" ]]; then
    log "ERROR: integrity_check on compacted copy returned '${INTEGRITY}' (expected 'ok') — aborting, no swap"
    exit 1
fi

SOURCE_COUNTS="$(get_table_counts "$DB_PATH")"
COMPACT_COUNTS="$(get_table_counts "$TMP_DB")"
if [[ "$SOURCE_COUNTS" != "$COMPACT_COUNTS" ]]; then
    log "ERROR: row-count mismatch between source and compacted copy — aborting, no swap"
    log "  source:   $(echo "$SOURCE_COUNTS" | tr '\n' ' ')"
    log "  compact:  $(echo "$COMPACT_COUNTS" | tr '\n' ' ')"
    exit 1
fi
log "verify: integrity_check=ok, row counts match ($(echo "$SOURCE_COUNTS" | tr '\n' ' '))"

# Step 4: re-check for a live holder immediately before swapping. This is
# the load-bearing safety check, not a formality — VACUUM INTO above may
# have taken noticeable wall-clock time, and opencode could have started
# since step 1's check.
if has_live_holder; then
    log "skipped: opencode running"
    exit 0
fi

# Step 5: atomic swap. Move the pre-vacuum file (and its -wal/-shm, if any)
# into the backup dir via rename — same filesystem, so this is instant and
# gives us a fully restorable point-in-time backup set (main db + any
# pending WAL frames), not just the compacted file.
mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
for ext in "" "-wal" "-shm"; do
    if [[ -f "${DB_PATH}${ext}" ]]; then
        mv "${DB_PATH}${ext}" "${BACKUP_DIR}/opencode-${STAMP}.db${ext}"
    fi
done

mv "$TMP_DB" "$DB_PATH"

# Defensive cleanup: no -wal/-shm should exist for the freshly-swapped file
# (VACUUM INTO produces a plain, non-WAL file), but remove any stragglers so
# nothing stale gets picked up on the next open.
rm -f "${DB_PATH}-wal" "${DB_PATH}-shm"

NEW_SIZE="$(file_size "$DB_PATH")"
log "compacted: ${CURRENT_SIZE} -> ${NEW_SIZE} bytes"
log "backup: ${BACKUP_DIR}/opencode-${STAMP}.db{,-wal,-shm}"

# Step 6: prune backups, keeping only the last KEEP_BACKUPS sets. Backups
# are grouped by their shared "opencode-<timestamp>" prefix so a set's main
# file, -wal, and -shm are pruned together.
# (No `mapfile` here — this must run under macOS's stock bash 3.2, which
# predates it.)
STAMPS=()
while IFS= read -r stamp; do
    [[ -n "$stamp" ]] && STAMPS+=("$stamp")
done < <(
    find "$BACKUP_DIR" -maxdepth 1 -type f -name 'opencode-*.db' \
        -exec basename {} \; |
        sed -E 's/^opencode-(.*)\.db$/\1/' |
        sort -r
)
if [[ "${#STAMPS[@]}" -gt "$KEEP_BACKUPS" ]]; then
    for ((i = KEEP_BACKUPS; i < ${#STAMPS[@]}; i++)); do
        old="${STAMPS[$i]}"
        rm -f "${BACKUP_DIR}/opencode-${old}.db" "${BACKUP_DIR}/opencode-${old}.db-wal" "${BACKUP_DIR}/opencode-${old}.db-shm"
        log "pruned old backup: opencode-${old}.db{,-wal,-shm}"
    done
fi

log "done: $(file_size "$DB_PATH") bytes, $(find "$BACKUP_DIR" -maxdepth 1 -name 'opencode-*.db' | wc -l | tr -d ' ') backup set(s) kept"
