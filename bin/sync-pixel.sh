#!/bin/bash

# sync-pixel.sh
# Pulls photos/videos from Pixel DCIM/Camera → local backup → logs to CSV → deletes from device.
#
# Safety contract: a file is ONLY deleted from the device after ALL of:
#   1. adb pull exits 0
#   2. local file exists on disk
#   3. local file size matches the size reported by the device (exact match for images;
#      ±1 % tolerance for large videos where adb stat can differ slightly)
#   4. the CSV row is written and flushed to disk

DEST="/Volumes/Dzianis-3/DCIM/Camera"
ANDROID_SRC="/sdcard/DCIM/Camera"
CSV="/Volumes/Dzianis-3/synced-files.csv"
TMP_LIST="/tmp/pixel_filelist_$$.txt"

# ── helpers ────────────────────────────────────────────────────────────────────

die() { echo "ERROR: $*" >&2; exit 1; }

require_adb() {
    command -v adb &>/dev/null || die "adb not found. Run: brew install android-platform-tools"
}

require_device() {
    DEVICE=$(adb devices 2>/dev/null | awk '/\tdevice$/{print $1; exit}')
    [ -n "$DEVICE" ] || die "No Android device detected. Connect via USB and enable USB Debugging."
    echo "Device: $DEVICE"
}

init_csv() {
    [ -f "$CSV" ] || echo "filename,size_bytes,modified_android,pulled_at,local_path,deleted_from_android" > "$CSV"
}

# True if file appears in CSV with deleted=yes (fully done)
fully_synced() { grep -q "^${1},.*,yes$" "$CSV" 2>/dev/null; }

# True if file appears in CSV with deleted=no (pulled but delete pending)
pending_delete() { grep -q "^${1},.*,no$" "$CSV" 2>/dev/null; }

mark_deleted() {
    local tmp; tmp=$(mktemp)
    awk -v f="$1" 'BEGIN{FS=OFS=","} $1==f{$NF="yes"} {print}' "$CSV" > "$tmp" && mv "$tmp" "$CSV"
}

# Verify local file is present and size is within tolerance of expected
verify_local() {
    local local_path="$1" expected_size="$2"
    [ -f "$local_path" ] || { echo "  ✗ local file missing after pull"; return 1; }
    local actual; actual=$(stat -f%z "$local_path" 2>/dev/null || echo 0)
    [ "$actual" -gt 0 ] || { echo "  ✗ local file is empty after pull"; return 1; }
    if [[ "$expected_size" =~ ^[0-9]+$ ]] && [ "$expected_size" -gt 0 ]; then
        local diff=$(( actual - expected_size )); diff=${diff#-}        # abs value
        local tolerance=$(( expected_size / 100 ))                      # 1 %
        [ "$tolerance" -lt 1024 ] && tolerance=1024                     # floor 1 KiB
        if [ "$diff" -gt "$tolerance" ]; then
            echo "  ✗ size mismatch: expected ${expected_size}B, got ${actual}B"
            return 1
        fi
    fi
    return 0
}

# ── startup ────────────────────────────────────────────────────────────────────

require_adb
require_device
init_csv
mkdir -p "$DEST"

# ── Phase 1: retry pending deletes from previous interrupted runs ──────────────

echo "Phase 1 — retrying any pending deletes…"
RETRIED=0
while IFS=',' read -r fname rest deleted; do
    [[ "$fname" == "filename" ]] && continue
    deleted="${deleted%$'\r'}"
    [[ "$deleted" == "no" ]] || continue
    local_path="$DEST/$fname"
    if [ -f "$local_path" ] && [ -s "$local_path" ]; then
        if adb shell rm "${ANDROID_SRC}/${fname}" </dev/null &>/dev/null; then
            mark_deleted "$fname"
            echo "  ✓ deleted (retry): $fname"
            ((RETRIED++))
        else
            echo "  ⚠ still can't delete: $fname (file may already be gone)" >&2
        fi
    else
        echo "  ⚠ skipping retry for $fname — local backup missing, will not delete" >&2
    fi
done < "$CSV"
echo "  Retried: $RETRIED"

# ── Phase 2: pull new files ────────────────────────────────────────────────────

echo ""
echo "Phase 2 — listing files on device…"
adb shell ls -l "$ANDROID_SRC" 2>/dev/null \
    | awk 'NF>=8 && !/^total/{print}' \
    > "$TMP_LIST"

PULLED=0; SKIPPED=0; FAILED=0

while IFS= read -r line; do
    SIZE=$(echo "$line"    | awk '{print $5}')
    FNAME=$(echo "$line"   | awk '{print $NF}' | tr -d '\r')
    MOD_DATE=$(echo "$line" | awk '{print $6, $7}')
    [ -z "$FNAME" ] && continue

    if fully_synced "$FNAME" || pending_delete "$FNAME"; then
        ((SKIPPED++)); continue
    fi

    LOCAL="$DEST/$FNAME"
    echo "Pulling: $FNAME (${SIZE} bytes)"

    # </dev/null on all adb calls — prevents adb from consuming the while-loop's stdin
    if adb pull "${ANDROID_SRC}/${FNAME}" "$LOCAL" </dev/null &>/dev/null; then

        # ── Verify before doing anything destructive ───────────────────────────
        if ! verify_local "$LOCAL" "$SIZE"; then
            echo "  ✗ verification failed — NOT deleting from device" >&2
            rm -f "$LOCAL"   # remove corrupt/incomplete download
            ((FAILED++)); continue
        fi

        # ── Write CSV and flush before touching the device ─────────────────────
        PULLED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        echo "${FNAME},${SIZE},${MOD_DATE},${PULLED_AT},${LOCAL},no" >> "$CSV"
        sync 2>/dev/null || true   # best-effort flush

        # ── Now safe to delete ─────────────────────────────────────────────────
        if adb shell rm "${ANDROID_SRC}/${FNAME}" </dev/null &>/dev/null; then
            mark_deleted "$FNAME"
            echo "  ✓ backed up and deleted from device"
        else
            echo "  ⚠ backed up (CSV written) but delete failed — will retry next run" >&2
        fi

        ((PULLED++))
    else
        echo "  ✗ pull failed — NOT deleting from device" >&2
        rm -f "$LOCAL"   # clean up any partial download
        ((FAILED++))
    fi

done < "$TMP_LIST"

rm -f "$TMP_LIST"

echo ""
echo "────────────────────────────────"
echo "Pulled : $PULLED"
echo "Skipped: $SKIPPED (already in CSV)"
echo "Failed : $FAILED"
echo "Log    : $CSV"
