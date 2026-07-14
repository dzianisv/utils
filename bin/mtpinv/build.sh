#!/usr/bin/env bash
# Build the `mtpinv` MTP inventory/pull helper used by swiftmtp-photo-backup.py.
#
# Why this exists: the stock `swiftmtp-cli ls` (SwiftMTP.app) returns EMPTY
# directory listings on some devices — a bug in the CLI's stale-generation
# wrapper, not in the underlying go-mtpx library. This helper links go-mtpx
# directly and enumerates/pulls reliably, emitting JSON.
#
# Requirements: Go (>=1.23) and libusb-1.0 (Homebrew: `brew install libusb`).
set -euo pipefail

cd "$(dirname "$0")"

# Locate libusb-1.0 pkg-config (Homebrew on Apple Silicon or Intel).
for p in /opt/homebrew/opt/libusb/lib/pkgconfig /usr/local/opt/libusb/lib/pkgconfig; do
  if [ -d "$p" ]; then
    export PKG_CONFIG_PATH="$p:${PKG_CONFIG_PATH:-}"
  fi
done

if ! pkg-config --exists libusb-1.0 2>/dev/null; then
  echo "error: libusb-1.0 not found. Install it (e.g. 'brew install libusb') and retry." >&2
  exit 1
fi

export CGO_ENABLED=1
go build -trimpath -o mtpinv .
echo "built: $(pwd)/mtpinv"
./mtpinv storages >/dev/null 2>&1 || true  # smoke (no device required to build)
