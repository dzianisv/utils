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
mtpinv -storage 65537 pull /DCIM/Camera/PXL_x.jpg /out/dir   # one-shot: {pulled,dest,files,bytes}
mtpinv -storage 65537 -all inventory /DCIM          # include hidden/dot files
mtpinv -storage 65537 serve                         # persistent single-session pull loop (NDJSON)
```

Global flags (`-storage`, `-all`, `-debug`) MUST precede the subcommand — Go's
stdlib `flag` stops at the first non-flag token.

### `serve` — persistent single-session transfer protocol

`serve` opens the MTP device **once** and then reads newline-delimited JSON
requests on stdin, streaming newline-delimited JSON events on stdout. A whole
backup run costs one `Initialize`/`Dispose` instead of one per file (no session
churn), and every pull streams per-chunk progress. It writes each object to a
caller-provided absolute path and does **no** fsync/verification — the driver
(`swiftmtp-photo-backup.py`) owns the durability transaction (expected size,
SHA-256, fsync, atomic publish, manifest commit).

```
stdin  (requests) : {"cmd":"pull","remote":"/DCIM/Camera/x.jpg","dest":"/abs/local/file"}
                    {"cmd":"ping"}
                    {"cmd":"quit"}
stdout (events)   : {"type":"ready","storage":65537,"pid":1234}
                    {"type":"progress","remote":"...","sent":N,"total":N,"pct":P}
                    {"type":"complete","remote":"...","dest":"...","bytes":N,"total":N}
                    {"type":"error","remote":"...","error":"...","fatal":true|false}
                    {"type":"pong"}   {"type":"bye"}
```

A path-resolution / not-a-file / local-create failure is a **non-fatal** error
(the session stays healthy and serving continues). A failure during the byte
stream is **fatal** (the MTP session is compromised): the helper exits so the
driver can reopen a fresh session and continue from the manifest without O(N)
session churn. The driver runs the helper in its own process group and kills only
that tree on a stall.

The helper is **read-only** with respect to the device (it never deletes,
renames, or writes to the phone). Hidden/dot files and directories are skipped
by default (use `-all` to include them).

