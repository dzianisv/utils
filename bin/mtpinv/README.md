# mtpinv — reliable MTP inventory/pull helper

A tiny JSON-emitting helper that `swiftmtp-photo-backup.py` uses to enumerate
(and, if needed, pull) files from an Android/MTP device.

## Why

The stock `swiftmtp-cli ls` (bundled in SwiftMTP.app) returns **empty output for
every directory** on some devices — even directories that demonstrably contain
photos — while `cd`, path resolution, and `pull` all work. The defect is in the
CLI's own stale-generation walk wrapper, not in the underlying MTP library
(`github.com/ganeshrvel/go-mtpx`). Because the backup script's inventory was
`ls`-based, it silently found 0 files on a phone full of photos.

`mtpinv` links `go-mtpx` directly (the same library, without the buggy wrapper)
and enumerates via a normal recursive `Walk`, which works reliably.

## Build

Requires Go (>=1.23) and libusb-1.0:

```sh
brew install libusb   # if not already present
./build.sh            # produces ./mtpinv (git-ignored)
```

`swiftmtp-photo-backup.py` auto-discovers the binary at `bin/mtpinv/mtpinv`
(next to its source), or via `--mtp-helper PATH` / `$SWIFTMTP_MTPINV`, or on
`$PATH`.

## Usage

```sh
mtpinv storages
mtpinv -storage 65537 inventory /DCIM /Pictures     # JSON: {files:[{path,name,size,mtime,object_id}],dirs,errors}
mtpinv -storage 65537 pull /DCIM/Camera/PXL_x.jpg /tmp/out   # JSON: {pulled,dest,bytes}
mtpinv -storage 65537 -all inventory /DCIM          # include hidden/dot files
```

The helper is **read-only** with respect to the device (it never deletes,
renames, or writes to the phone). Hidden/dot files and directories are skipped
by default (use `-all` to include them).
