#!/usr/bin/env python3
"""Production-safe incremental Android (MTP) photo backup using SwiftMTP's stock CLI.

This tool pulls photos/videos from an MTP device (e.g. a Pixel) into a local
destination volume, using only the read/list/pull capabilities of
``swiftmtp-cli`` (SwiftMTP.app). It maintains an authoritative SQLite manifest so
runs are incremental and resumable.

Safety contract
---------------
* Read-only with respect to the device. This script ONLY ever invokes the
  ``devices``, ``storages``, ``ls`` and ``pull`` subcommands of swiftmtp-cli. It
  never deletes, moves, renames, or pushes anything on the phone.
* A file is only marked "completed" after: the CLI reported the exact
  ``Pull complete.`` success line (its exit status is unreliable and can be 0 on
  failure), the pulled output was discovered, its byte size matched the
  device-reported size, its SHA-256 was computed, the bytes were fsync'd, and the
  file was atomically renamed into place on the same volume.
* Default mode is a dry run. Transfers only happen with ``--run``.
* ``--dry-run`` and ``--verify`` are side-effect free with respect to production
  state: they never create the destination directory, the SQLite manifest, log
  files, or the lock. Dry-run reads the device plus an existing manifest (if any);
  verify needs neither the phone nor the CLI and, when the destination or manifest
  is absent, exits 0 with a "nothing to verify" message and no filesystem changes.
  (An existing manifest is opened normally so verify can record its usual
  requeue/status and log output.)

Parsing the stock ``ls`` output (known limitations)
---------------------------------------------------
``swiftmtp-cli`` exposes no machine-readable listing; the only option is ``ls``,
whose rows are fixed-width HUMAN columns produced by
``print("\\(type) \\(paddedSize)  \\(dateStr)  \\(file.name)")`` in main.swift:
a 5-char type, a min-width-12 size, a date padded/truncated to 20 *UTF-16* code
units (verified empirically against Foundation's ``String.padding``), then the
raw, UNQUOTED file name. This format is inherently ambiguous for arbitrary
inputs, and this tool does NOT pretend otherwise:

* a file name containing a newline is split across output lines;
* the date is opaque and may be truncated, so it is used only as an opaque
  per-file stability token and is never interpreted as a real timestamp;
* the date column width is counted in UTF-16 units while this parser indexes by
  Unicode scalar, so a non-BMP character inside a fixed column shifts offsets.

Rather than guess, ``parse_ls_line`` enforces the exact structural invariants
(notably the redundant two-space separator that must follow the 20-unit date).
Any non-empty ``ls`` line that fails them is treated as ambiguous and the whole
directory listing FAILS LOUDLY (``LsParseError``) instead of silently dropping
or mis-attributing files. Rows that satisfy the invariants preserve their spaces
and (BMP) Unicode exactly.

Why not call the bundled ``gomtp`` ABI directly (it returns clean JSON)? Because
MTP/USB access is gated on SwiftMTP.app's ``com.apple.security.device.usb``
entitlement; an unentitled Python process loading ``gomtp.dylib`` cannot reach
the device. Shelling out to the entitled ``swiftmtp-cli`` is therefore the only
workable stdlib-only path, so the conservative parser is retained and fails
closed.

Live-device checks still to be confirmed on real hardware (do not block static
use; the phone was disconnected during development): (1) single-file ``pull``
destination semantics — expected to be "destination is a directory, output =
destination/basename", which ``discover_pulled_file`` already tolerates; and
(2) that real ``dateModified`` values stay ASCII within the 20-unit date column.

Upstream reference: Neighbor-Z/SwiftMTP @ eff9a952a4f77eacde58037e0ec88b3b0bec856d
(swiftmtp-cli/main.swift, swiftmtp-cli/CLI_USAGE.md).

Requires: Python 3.10+, standard library only. macOS.
"""

import argparse
import errno
import fcntl
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone

# --- Constants ---------------------------------------------------------------

DEFAULT_DEST = "/Volumes/Dzianis-3/Photos"
DEFAULT_CLI = "/Applications/SwiftMTP.app/Contents/MacOS/swiftmtp-cli"
DEFAULT_SOURCES = ["/DCIM", "/Pictures"]
DEFAULT_MIN_FREE_GIB = 10.0

BACKUP_DIRNAME = ".swiftmtp-backup"
GIB = 1024 ** 3

# Media extensions we back up (case-insensitive), per requirements.
MEDIA_EXTS = {
    "jpg", "jpeg", "heic", "heif", "png", "webp", "gif",
    "dng", "raw", "mp4", "mov", "3gp", "xmp",
}

# The only device-side CLI verbs this tool is ever allowed to run. Read-only.
ALLOWED_CLI_VERBS = {"devices", "storages", "ls", "pull"}

# Exit codes.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PREFLIGHT = 3
EXIT_DEVICE = 4
EXIT_TRANSFER = 5
EXIT_LOCK = 6
EXIT_SPACE = 7
EXIT_INTERRUPT = 130

log = logging.getLogger("swiftmtp-photo-backup")


# --- Errors ------------------------------------------------------------------

class PreflightError(Exception):
    pass


class DeviceError(Exception):
    """The device connection/session failed (as opposed to a single dir)."""


class DirListError(Exception):
    """A single directory could not be listed (e.g. missing optional root)."""


class InventoryError(Exception):
    """The whole inventory failed."""


class LsParseError(InventoryError):
    """An `ls` listing produced output that could not be unambiguously parsed.

    Raised (fail-closed) rather than silently dropping or mis-attributing a row,
    e.g. a file name containing a newline, undecodable bytes, or non-BMP text in
    a fixed-width column. Treated as an inventory failure (non-zero exit).
    """


# --- Logging & secret redaction ---------------------------------------------

_SECRETS: set[str] = set()


def register_secret(value: str) -> None:
    """Register a string (full device id / serial) to be scrubbed from all logs."""
    if value and len(value) >= 3:
        _SECRETS.add(value)


def _redact(text: str) -> str:
    out = text
    for secret in _SECRETS:
        if secret and secret in out:
            out = out.replace(secret, "<redacted>")
    return out


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        red = _redact(msg)
        if red != msg:
            record.msg = red
            record.args = ()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": _redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = _redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_console_logging(verbose: bool) -> None:
    log.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    handler.addFilter(_RedactFilter())
    log.addHandler(handler)


def setup_file_logging(dest: str) -> str | None:
    log_dir = os.path.join(dest, BACKUP_DIRNAME, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as exc:
        log.warning("could not create log dir %s: %s", log_dir, exc)
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(log_dir, f"run-{ts}-{os.getpid()}.jsonl")
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_RedactFilter())
    log.addHandler(handler)
    return path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- swiftmtp-cli invocation -------------------------------------------------

class CLI:
    def __init__(self, path: str, list_timeout: int):
        self.path = path
        self.list_timeout = list_timeout

    def run(self, verb: str, args: list[str], timeout: int | None) -> tuple[int, str, str]:
        if verb not in ALLOWED_CLI_VERBS:
            # Hard guard: this tool must never issue a mutating device command.
            raise AssertionError(f"refusing to run non-read-only CLI verb: {verb!r}")
        cmd = [self.path, verb, *args]
        redacted = " ".join(_redact(c) for c in cmd)
        log.debug("exec: %s (timeout=%s)", redacted, timeout)
        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            raise DeviceError(f"swiftmtp-cli {verb} timed out after {timeout}s")
        return proc.returncode, proc.stdout or "", proc.stderr or ""


# --- Device / storage discovery ---------------------------------------------

_DEVICE_LINE = re.compile(r"^(?P<id>[^\t]+)\tdevice\t(?P<desc>.*)$")


def parse_devices(stdout: str) -> list[tuple[str, str, str]]:
    """Return [(device_id, model, manufacturer)] from `devices` output."""
    devices = []
    for line in stdout.splitlines():
        m = _DEVICE_LINE.match(line.rstrip("\r"))
        if not m:
            continue
        dev_id = m.group("id")
        desc = m.group("desc")
        model, manufacturer = desc, ""
        mm = re.match(r"^(?P<model>.*?) \((?P<manu>.*)\)\s*$", desc)
        if mm:
            model = mm.group("model")
            manufacturer = mm.group("manu")
        devices.append((dev_id, model.strip() or "device", manufacturer.strip()))
    return devices


def parse_storages(stdout: str) -> list[tuple[str, str]]:
    """Return [(storage_id, name)] from `storages` output."""
    storages = []
    for line in stdout.splitlines():
        line = line.rstrip("\r")
        if "\t" not in line:
            continue
        sid, _, rest = line.partition("\t")
        sid = sid.strip()
        if not sid.isdigit():
            continue
        storages.append((sid, rest.strip()))
    return storages


def device_fingerprint(device_id: str) -> str:
    return hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:12]


def discover_devices(cli: CLI) -> list[tuple[str, str, str]]:
    rc, out, err = cli.run("devices", [], cli.list_timeout)
    if "Error initializing device" in out:
        raise DeviceError("device initialization failed")
    if rc != 0 and not out.strip():
        raise DeviceError(f"`devices` failed (rc={rc}): {err.strip()}")
    return parse_devices(out)


def resolve_device(cli: CLI, requested: str | None) -> tuple[str, str]:
    """Return (full_device_id, model). Auto-selects only when unambiguous."""
    devices = discover_devices(cli)
    if not devices:
        raise DeviceError(
            "No MTP device detected. Connect the phone via USB, unlock it, and "
            "set the USB mode to 'File Transfer' (MTP)."
        )
    if requested:
        matches = []
        for dev_id, model, _manu in devices:
            parts = dev_id.split("|")
            if requested == dev_id or requested in parts:
                matches.append((dev_id, model))
        if not matches:
            # Fall back to substring match on the non-secret parts.
            for dev_id, model, _manu in devices:
                head = "|".join(dev_id.split("|")[:2])
                if requested in head:
                    matches.append((dev_id, model))
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise DeviceError(f"--device {requested!r} did not match any connected device")
        raise DeviceError(f"--device {requested!r} is ambiguous ({len(matches)} matches)")
    if len(devices) == 1:
        return devices[0][0], devices[0][1]
    # Ambiguous: describe choices WITHOUT leaking full serials.
    lines = []
    for dev_id, model, manu in devices:
        parts = dev_id.split("|")
        head = "|".join(parts[:2]) if len(parts) >= 2 else parts[0]
        lines.append(f"  vendor|product={head} model={model} ({manu}) fp={device_fingerprint(dev_id)}")
    raise DeviceError(
        "Multiple MTP devices detected; select one with --device <vendorId|productId>:\n"
        + "\n".join(lines)
    )


def resolve_storage(cli: CLI, device_id: str, requested: str | None) -> str:
    rc, out, err = cli.run("storages", [device_id], cli.list_timeout)
    if "Error initializing device" in out or "Failed to fetch storages" in out:
        raise DeviceError(f"could not fetch storages: {out.strip() or err.strip()}")
    if rc != 0 and not out.strip():
        raise DeviceError(f"`storages` failed (rc={rc}): {err.strip()}")
    storages = parse_storages(out)
    if not storages:
        raise DeviceError("device reported no usable storage")
    if requested:
        for sid, _name in storages:
            if sid == requested:
                return sid
        raise DeviceError(f"--storage {requested!r} not found on device")
    if len(storages) == 1:
        return storages[0][0]
    listing = "\n".join(f"  {sid}  {name}" for sid, name in storages)
    raise DeviceError("Multiple storages found; select one with --storage <id>:\n" + listing)


# --- ls output parsing (strict, grounded in upstream source) -----------------
# Upstream (swiftmtp-cli/main.swift) prints each entry as:
#   "\(type) \(paddedSize)  \(dateStr)  \(file.name)"
# where:
#   type      = "<DIR>" (folders) or 5 spaces (files)          -> exactly 5 chars
#   " "       = single separator space
#   paddedSize= right-justified, min width 12, "-" for folders, decimal bytes
#   "  "      = two-space separator
#   dateStr   = date padded/truncated to EXACTLY 20 UTF-16 units (opaque token)
#   "  "      = two-space separator
#   name      = raw, UNQUOTED file name (may contain spaces / Unicode)
# This human format is NOT unambiguous for arbitrary names (see module docstring).
# We parse by the fixed structure (never by whitespace splitting) and rely on the
# redundant post-date two-space separator as a self-check: if the assumed widths
# do not hold (e.g. non-BMP text shifting the UTF-16-counted date column), the
# separator check fails and the row is rejected rather than mis-parsed. Callers
# escalate any rejected non-empty line to a loud LsParseError (fail closed).

class LsEntry:
    __slots__ = ("is_folder", "size", "modified", "name")

    def __init__(self, is_folder: bool, size: int | None, modified: str, name: str):
        self.is_folder = is_folder
        self.size = size
        self.modified = modified
        self.name = name


def parse_ls_line(line: str) -> LsEntry | None:
    """Parse one strict `ls` row, or return None if it is not an unambiguous row.

    Returning None means "this line does not satisfy the exact upstream structure";
    callers treat a non-empty None line as ambiguous and fail closed. Names that
    parse are returned with spaces/Unicode preserved. The stored `modified` value
    is the opaque 20-unit date token (rstripped), not a real timestamp.
    """
    line = line.rstrip("\r\n")
    if len(line) < 6:
        return None
    type_field = line[:5]
    if type_field == "<DIR>":
        is_folder = True
    elif type_field == "     ":  # five spaces
        is_folder = False
    else:
        return None
    if line[5] != " ":
        return None
    rest = line[6:]  # paddedSize + "  " + date(20) + "  " + name
    stripped = rest.lstrip(" ")
    sp = stripped.find(" ")
    if sp <= 0:
        return None
    size_token = stripped[:sp]
    after = stripped[sp:]  # "  " + date(20) + "  " + name
    if not after.startswith("  "):
        return None
    body = after[2:]
    if len(body) < 22:  # 20-char date + 2-space separator (name may be non-empty)
        return None
    date_field = body[:20]
    tail = body[20:]
    if not tail.startswith("  "):  # redundant separator: also guards width drift
        return None
    name = tail[2:]
    if not name:
        return None
    if "\ufffd" in name or "\ufffd" in date_field:
        # U+FFFD means the CLI's stdout was not valid UTF-8 here: the name cannot
        # be represented faithfully, so refuse to guess a local path for it.
        return None
    if "\x00" in name or "/" in name:  # never trust a name that could break paths
        return None
    if is_folder:
        size: int | None = None
    else:
        if not size_token.isdigit():
            return None
        size = int(size_token)
    return LsEntry(is_folder, size, date_field.rstrip(), name)


def join_remote(parent: str, name: str) -> str:
    return parent.rstrip("/") + "/" + name


def is_media(name: str) -> bool:
    dot = name.rfind(".")
    if dot < 0:
        return False
    return name[dot + 1:].lower() in MEDIA_EXTS


# --- Inventory ---------------------------------------------------------------

class MediaFile:
    __slots__ = ("remote_path", "name", "size", "modified", "root")

    def __init__(self, remote_path: str, name: str, size: int, modified: str, root: str):
        self.remote_path = remote_path
        self.name = name
        self.size = size
        self.modified = modified
        self.root = root


def list_dir(cli: CLI, device_id: str, storage_id: str, path: str) -> list[LsEntry]:
    rc, out, err = cli.run("ls", [device_id, storage_id, path], cli.list_timeout)
    if "Error initializing device" in out:
        raise DeviceError("device connection lost during inventory")
    if "Error listing directory" in out or rc != 0:
        detail = out.strip() or err.strip() or f"rc={rc}"
        raise DirListError(detail)
    entries = []
    bad_lines = []
    for line in out.split("\n"):
        if not line:
            continue
        entry = parse_ls_line(line)
        if entry is None:
            bad_lines.append(line)
            continue
        entries.append(entry)
    if bad_lines:
        # A successful ls (rc==0, no error string) whose every non-empty line is
        # expected to be a valid entry. Any line that is not is ambiguous — it may
        # be a newline within a file name (which also corrupts the adjacent parsed
        # row), undecodable bytes, or unexpected output. Fail closed for this
        # directory rather than trust a possibly-corrupted listing.
        sample = _redact(bad_lines[0])
        if len(sample) > 120:
            sample = sample[:120] + "…"
        raise LsParseError(
            f"refusing to trust `ls` of {path}: {len(bad_lines)} line(s) did not match the "
            f"strict swiftmtp-cli format (a file name may contain a newline or undecodable "
            f"bytes, or a fixed column held non-BMP text). Not importing this listing to avoid "
            f"mis-attributing files. First offending line: {sample!r}"
        )
    return entries


def walk_root(cli: CLI, device_id: str, storage_id: str, root: str,
              out: list[MediaFile], max_depth: int) -> None:
    visited: set[str] = set()
    stack: list[tuple[str, int]] = [(root, 0)]
    while stack:
        path, depth = stack.pop()
        norm = path.rstrip("/") or "/"
        if norm in visited:
            continue
        visited.add(norm)
        entries = list_dir(cli, device_id, storage_id, path)
        for entry in entries:
            child = join_remote(path, entry.name)
            if entry.is_folder:
                if depth + 1 <= max_depth:
                    stack.append((child, depth + 1))
                else:
                    log.warning("max depth reached, not descending into %s", child)
            elif is_media(entry.name) and entry.size is not None:
                out.append(MediaFile(child, entry.name, entry.size, entry.modified, root))


def inventory(cli: CLI, device_id: str, storage_id: str, roots: list[str],
              max_depth: int) -> tuple[list[MediaFile], list[tuple[str, str]]]:
    media: list[MediaFile] = []
    warnings: list[tuple[str, str]] = []
    ok_roots = 0
    for root in roots:
        try:
            walk_root(cli, device_id, storage_id, root, media, max_depth)
            ok_roots += 1
            log.info("inventoried %s", root)
        except DirListError as exc:
            warnings.append((root, str(exc)))
            log.warning("source root %s unavailable (skipping): %s", root, exc)
        # DeviceError propagates: a lost connection is a hard failure.
    if ok_roots == 0:
        raise InventoryError("no source root could be inventoried")
    return media, warnings


# --- Path sanitization (ExFAT-safe, deterministic) ---------------------------

_EXFAT_INVALID = set('"*/:<>?\\|')


def sanitize_component(name: str) -> str:
    out_chars = []
    for ch in name:
        o = ord(ch)
        if ch in _EXFAT_INVALID or o < 0x20 or o == 0x7F:
            out_chars.append("_")
        else:
            out_chars.append(ch)
    out = "".join(out_chars).rstrip(" .")
    if out in ("", ".", ".."):
        out = "_"
    if len(out) > 200:
        stem, ext = os.path.splitext(out)
        out = stem[: max(1, 200 - len(ext))] + ext
    return out


def build_final_path(dest: str, device_dir: str, storage_id: str, remote_path: str) -> str:
    components = [c for c in remote_path.split("/") if c not in ("", ".", "..")]
    safe = [sanitize_component(c) for c in components]
    parts = [dest, device_dir, sanitize_component(storage_id), *safe]
    final = os.path.join(*parts)
    dest_root = os.path.realpath(dest)
    # Traversal guard: the final path must resolve under dest.
    resolved_parent = os.path.realpath(os.path.dirname(final))
    if not (resolved_parent == dest_root or resolved_parent.startswith(dest_root + os.sep)):
        raise ValueError(f"refusing path outside destination: {final}")
    return final


# --- Hashing & fsync ---------------------------------------------------------

def sha256_file(path: str, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def fsync_path(path: str) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_dir(path: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass  # not supported on all filesystems (e.g. some ExFAT)
    finally:
        os.close(fd)


# --- Manifest (authoritative SQLite store) -----------------------------------

class Manifest:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    device_fingerprint TEXT,
                    storage_id TEXT,
                    dest TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    notes TEXT
                );
                CREATE TABLE IF NOT EXISTS source_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    device_fingerprint TEXT NOT NULL,
                    storage_id TEXT NOT NULL,
                    root TEXT NOT NULL,
                    remote_path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    modified TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                CREATE TABLE IF NOT EXISTS imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_fingerprint TEXT NOT NULL,
                    storage_id TEXT NOT NULL,
                    remote_path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    modified TEXT NOT NULL,
                    sha256 TEXT,
                    local_relpath TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    run_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(device_fingerprint, storage_id, remote_path, size, modified)
                );
                CREATE INDEX IF NOT EXISTS idx_imports_identity
                    ON imports(device_fingerprint, storage_id, status);
                """
            )

    def close(self) -> None:
        self.conn.close()

    # -- runs --
    def start_run(self, mode: str, fp: str | None, storage: str | None, dest: str) -> str:
        run_id = str(uuid.uuid4())
        with self.conn:
            self.conn.execute(
                "INSERT INTO runs(id, mode, device_fingerprint, storage_id, dest, started_at, status) "
                "VALUES (?,?,?,?,?,?,?)",
                (run_id, mode, fp, storage, dest, now_iso(), "running"),
            )
        return run_id

    def finish_run(self, run_id: str, status: str, notes: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE runs SET finished_at=?, status=?, notes=? WHERE id=?",
                (now_iso(), status, notes, run_id),
            )

    # -- observations --
    def record_observations(self, run_id: str, fp: str, storage: str, files: list[MediaFile]) -> None:
        ts = now_iso()
        rows = [
            (run_id, fp, storage, f.root, f.remote_path, f.name, f.size, f.modified, ts)
            for f in files
        ]
        with self.conn:
            self.conn.executemany(
                "INSERT INTO source_observations"
                "(run_id, device_fingerprint, storage_id, root, remote_path, name, size, modified, observed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                rows,
            )

    # -- imports --
    def get_import(self, fp: str, storage: str, remote_path: str, size: int, modified: str):
        return self.conn.execute(
            "SELECT * FROM imports WHERE device_fingerprint=? AND storage_id=? AND remote_path=? "
            "AND size=? AND modified=?",
            (fp, storage, remote_path, size, modified),
        ).fetchone()

    def is_completed(self, fp: str, storage: str, remote_path: str, size: int, modified: str) -> bool:
        row = self.get_import(fp, storage, remote_path, size, modified)
        return bool(row and row["status"] == "completed")

    def upsert_completed(self, fp: str, storage: str, f: MediaFile, sha256: str,
                         local_relpath: str, run_id: str) -> None:
        ts = now_iso()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO imports
                (device_fingerprint, storage_id, remote_path, size, modified, sha256,
                 local_relpath, status, error, run_id, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,'completed',NULL,?,?,?)
                ON CONFLICT(device_fingerprint, storage_id, remote_path, size, modified)
                DO UPDATE SET sha256=excluded.sha256, local_relpath=excluded.local_relpath,
                    status='completed', error=NULL, run_id=excluded.run_id, updated_at=excluded.updated_at
                """,
                (fp, storage, f.remote_path, f.size, f.modified, sha256,
                 local_relpath, run_id, ts, ts),
            )

    def mark_status(self, fp: str, storage: str, f: MediaFile, status: str,
                    error: str | None, run_id: str) -> None:
        ts = now_iso()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO imports
                (device_fingerprint, storage_id, remote_path, size, modified, sha256,
                 local_relpath, status, error, run_id, created_at, updated_at)
                VALUES (?,?,?,?,?,NULL,NULL,?,?,?,?,?)
                ON CONFLICT(device_fingerprint, storage_id, remote_path, size, modified)
                DO UPDATE SET status=excluded.status, error=excluded.error,
                    run_id=excluded.run_id, updated_at=excluded.updated_at
                """,
                (fp, storage, f.remote_path, f.size, f.modified, status,
                 error, run_id, ts, ts),
            )

    def requeue_import_row(self, row_id: int, error: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE imports SET status='pending', error=?, updated_at=? WHERE id=?",
                (error, now_iso(), row_id),
            )

    def completed_rows(self, fp: str | None = None, storage: str | None = None):
        if fp is not None and storage is not None:
            return self.conn.execute(
                "SELECT * FROM imports WHERE status='completed' AND device_fingerprint=? AND storage_id=?",
                (fp, storage),
            ).fetchall()
        return self.conn.execute("SELECT * FROM imports WHERE status='completed'").fetchall()


# --- Reconcile ---------------------------------------------------------------

def reconcile(manifest: Manifest, dest: str, fp: str, storage: str) -> int:
    """Requeue completed rows whose local file is missing or the wrong size."""
    requeued = 0
    for row in manifest.completed_rows(fp, storage):
        relpath = row["local_relpath"]
        if not relpath:
            manifest.requeue_import_row(row["id"], "reconcile: missing local_relpath")
            requeued += 1
            continue
        local = os.path.join(dest, relpath)
        if not os.path.isfile(local):
            manifest.requeue_import_row(row["id"], "reconcile: local file missing")
            requeued += 1
        elif os.path.getsize(local) != row["size"]:
            manifest.requeue_import_row(row["id"], "reconcile: local size mismatch")
            requeued += 1
    if requeued:
        log.warning("reconcile requeued %d import(s) with missing/mismatched local files", requeued)
    return requeued


# --- Pull success detection --------------------------------------------------

_ANSI_CLEAR = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def pull_reported_success(stdout: str) -> bool:
    """swiftmtp-cli can exit 0 even on failure, so gate on the exact success line.

    stdout may contain carriage-return progress bars and an ANSI clear sequence;
    normalize by splitting on CR/LF and stripping ANSI, then require an exact
    'Pull complete.' token and no failure markers.
    """
    if "Pull failed." in stdout or "Error downloading:" in stdout:
        return False
    for token in re.split(r"[\r\n]", stdout):
        token = _ANSI_CLEAR.sub("", token).strip()
        if token == "Pull complete.":
            return True
    return False


def discover_pulled_file(incoming_sub: str, remote_basename: str) -> str | None:
    files = []
    for base, _dirs, names in os.walk(incoming_sub):
        for n in names:
            p = os.path.join(base, n)
            if os.path.isfile(p):
                files.append(p)
    if not files:
        return None
    for p in files:
        if os.path.basename(p) == remote_basename:
            return p
    if len(files) == 1:
        return files[0]
    return None


# --- Preflight ---------------------------------------------------------------

def check_cli(cli_path: str) -> None:
    if not os.path.isfile(cli_path):
        raise PreflightError(
            f"swiftmtp-cli not found at {cli_path}. Install SwiftMTP.app or pass --cli."
        )
    if not os.access(cli_path, os.X_OK):
        raise PreflightError(f"swiftmtp-cli at {cli_path} is not executable")


def check_android_file_transfer() -> None:
    """The macOS 'Android File Transfer' app + its agent grab the MTP device."""
    try:
        proc = subprocess.run(
            ["/bin/ps", "-Axo", "comm"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return  # best-effort; don't block if ps is unavailable
    for line in proc.stdout.splitlines():
        if "Android File Transfer" in line:
            raise PreflightError(
                "Android File Transfer (or its 'Android File Transfer Agent') is running "
                "and will hold the MTP device, blocking swiftmtp-cli. Quit Android File "
                "Transfer and terminate its agent, then retry."
            )


def check_mount(mount: str, allow_unmounted: bool) -> None:
    """Verify the destination volume is mounted. Read-only: creates nothing."""
    if not os.path.isdir(mount):
        raise PreflightError(
            f"destination volume {mount} is not mounted (directory missing). "
            "Plug in / mount the backup drive."
        )
    if not allow_unmounted and not os.path.ismount(mount):
        raise PreflightError(
            f"{mount} exists but is NOT a mounted volume — refusing to write to an "
            "ordinary directory accidentally created under /Volumes. Mount the real "
            "volume (or pass --allow-unmounted-dest for testing)."
        )


def ensure_destination(dest: str, mount: str) -> None:
    """Create DEST under the (already-checked) mount and prove it is writable and
    contained. Only for modes that actually write backups (i.e. --run)."""
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as exc:
        raise PreflightError(f"cannot create destination {dest}: {exc}")
    mount_root = os.path.realpath(mount)
    dest_root = os.path.realpath(dest)
    if not (dest_root == mount_root or dest_root.startswith(mount_root + os.sep)):
        raise PreflightError(
            f"destination {dest} does not resolve under configured mount {mount}"
        )
    # Writability probe.
    probe = os.path.join(dest, f".swiftmtp-write-test-{os.getpid()}")
    try:
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
    except OSError as exc:
        raise PreflightError(f"destination {dest} is not writable: {exc}")


def free_bytes(path: str) -> int:
    st = os.statvfs(path)
    return st.f_frsize * st.f_bavail


def free_bytes_for(dest: str, mount: str) -> int:
    """Free bytes on the destination volume without requiring DEST itself to exist."""
    return free_bytes(dest if os.path.isdir(dest) else mount)


def acquire_lock(dest: str):
    lock_dir = os.path.join(dest, BACKUP_DIRNAME)
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, "swiftmtp-photo-backup.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            raise PreflightError("another swiftmtp-photo-backup run holds the lock")
        raise
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()} {now_iso()}\n".encode())
    return fd  # keep open for the process lifetime to hold the lock


# --- Human formatting --------------------------------------------------------

def human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.2f} TiB"


# --- Modes -------------------------------------------------------------------

def partition_pending(manifest: Manifest, fp: str, storage: str,
                      files: list[MediaFile]) -> tuple[list[MediaFile], int, int]:
    pending, done_bytes, pending_bytes = [], 0, 0
    for f in files:
        if manifest.is_completed(fp, storage, f.remote_path, f.size, f.modified):
            done_bytes += f.size
        else:
            pending.append(f)
            pending_bytes += f.size
    return pending, done_bytes, pending_bytes


def load_completed_map(db_path: str, fp: str, storage: str) -> dict:
    """Read {(remote_path,size,modified): local_relpath} for completed imports.

    Read-only and side-effect free for dry runs: returns {} (and creates nothing)
    when the manifest file is absent, unreadable, or has no imports table yet.
    """
    result: dict = {}
    if not os.path.isfile(db_path):
        return result
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error:
        return result
    try:
        cur = conn.execute(
            "SELECT remote_path, size, modified, local_relpath FROM imports "
            "WHERE status='completed' AND device_fingerprint=? AND storage_id=?",
            (fp, storage),
        )
        for rp, sz, mod, rel in cur.fetchall():
            result[(rp, sz, mod)] = rel
    except sqlite3.Error:
        pass  # missing/older schema -> treat as nothing completed
    finally:
        conn.close()
    return result


def do_dry_run(cli: CLI, dest: str, mount: str, device_id: str, model: str,
               fp: str, storage: str, roots: list[str], max_depth: int,
               min_free_gib: float, completed: dict) -> int:
    """Preview only. Reads the device and an EXISTING manifest; writes nothing and
    never creates the destination, manifest, logs, or lock."""
    files, warnings = inventory(cli, device_id, storage, roots, max_depth)
    device_dir = f"{sanitize_component(model)}-{fp}"
    pending, done_bytes, pending_bytes = [], 0, 0
    for f in files:
        rel = completed.get((f.remote_path, f.size, f.modified))
        backed_up = False
        if rel:  # read-only reconcile: only "done" if the local file is really there
            local = os.path.join(dest, rel)
            if os.path.isfile(local) and os.path.getsize(local) == f.size:
                backed_up = True
        if backed_up:
            done_bytes += f.size
        else:
            pending.append(f)
            pending_bytes += f.size
    avail = free_bytes_for(dest, mount)
    reserve = int(min_free_gib * GIB)
    usable = avail - reserve
    dest_note = "" if os.path.isdir(dest) else "  (would be created on --run)"

    print("── swiftmtp-photo-backup (DRY RUN — no changes written) ────────")
    print(f"device fp     : {fp}  model: {model}")
    print(f"storage       : {storage}")
    print(f"destination   : {dest}{dest_note}")
    print(f"sources       : {', '.join(roots)}")
    print(f"media found   : {len(files)} files, {human_bytes(done_bytes + pending_bytes)}")
    print(f"already backed: {len(files) - len(pending)} files, {human_bytes(done_bytes)}")
    print(f"pending       : {len(pending)} files, {human_bytes(pending_bytes)}")
    print(f"free space    : {human_bytes(avail)} (reserve {human_bytes(reserve)})")
    print(f"usable        : {human_bytes(max(0, usable))}")
    if warnings:
        for root, msg in warnings:
            print(f"  ! source {root} skipped: {msg}")
    for f in pending[:20]:
        final = build_final_path(dest, device_dir, storage, f.remote_path)
        print(f"  + {f.remote_path} -> {os.path.relpath(final, dest)} ({human_bytes(f.size)})")
    if len(pending) > 20:
        print(f"  … and {len(pending) - 20} more")
    if pending_bytes > usable:
        print("RESULT: pending bytes EXCEED usable space; --run would be refused.")
    else:
        print("RESULT: OK — re-run with --run to transfer.")
    return EXIT_OK


def do_run(manifest: Manifest, cli: CLI, dest: str, device_id: str, model: str,
           fp: str, storage: str, roots: list[str], max_depth: int,
           min_free_gib: float, pull_timeout: int) -> int:
    run_id = manifest.start_run("run", fp, storage, dest)
    incoming_dir = os.path.join(dest, BACKUP_DIRNAME, "incoming", run_id)
    quarantine_dir = os.path.join(dest, BACKUP_DIRNAME, "quarantine", run_id)
    os.makedirs(incoming_dir, exist_ok=True)
    device_dir = f"{sanitize_component(model)}-{fp}"
    transferred = failed = skipped = 0
    try:
        files, warnings = inventory(cli, device_id, storage, roots, max_depth)
        manifest.record_observations(run_id, fp, storage, files)
        reconcile(manifest, dest, fp, storage)
        pending, done_bytes, pending_bytes = partition_pending(manifest, fp, storage, files)

        avail = free_bytes(dest)
        reserve = int(min_free_gib * GIB)
        if pending_bytes > avail - reserve:
            msg = (f"insufficient space: pending {human_bytes(pending_bytes)} > usable "
                   f"{human_bytes(max(0, avail - reserve))} (free {human_bytes(avail)} - "
                   f"reserve {human_bytes(reserve)})")
            manifest.finish_run(run_id, "refused", msg)
            log.error(msg)
            return EXIT_SPACE

        log.info("run: %d pending file(s), %s", len(pending), human_bytes(pending_bytes))
        for i, f in enumerate(pending, 1):
            log.info("[%d/%d] %s (%s)", i, len(pending), f.remote_path, human_bytes(f.size))
            try:
                result = transfer_one(cli, manifest, dest, device_id, device_dir, fp, storage, f,
                                      incoming_dir, quarantine_dir, run_id, pull_timeout)
            except DeviceError:
                manifest.mark_status(fp, storage, f, "failed", "device connection lost", run_id)
                failed += 1
                log.error("device connection lost; aborting remaining transfers")
                break
            if result == "transferred":
                transferred += 1
            elif result == "skipped":
                skipped += 1
            else:
                failed += 1

        _cleanup_dir(incoming_dir)
        status = "ok" if failed == 0 else "partial"
        notes = f"transferred={transferred} skipped={skipped} failed={failed}"
        manifest.finish_run(run_id, status, notes)
        print(f"Done. transferred={transferred} skipped={skipped} failed={failed}")
        if warnings:
            for root, msg in warnings:
                print(f"  ! source {root} skipped: {msg}")
        return EXIT_OK if failed == 0 else EXIT_TRANSFER
    except Exception as exc:
        manifest.finish_run(run_id, "error", str(exc))
        raise


def transfer_one(cli: CLI, manifest: Manifest, dest: str, device_id: str, device_dir: str,
                 fp: str, storage: str, f: MediaFile, incoming_dir: str, quarantine_dir: str,
                 run_id: str, pull_timeout: int) -> str:
    identity = f"{fp}|{storage}|{f.remote_path}|{f.size}|{f.modified}"
    id_hash = hashlib.sha256(identity.encode()).hexdigest()[:8]
    final_default = build_final_path(dest, device_dir, storage, f.remote_path)

    incoming_sub = os.path.join(incoming_dir, uuid.uuid4().hex)
    os.makedirs(incoming_sub, exist_ok=True)
    timeout = pull_timeout if pull_timeout > 0 else max(600, int(f.size / (150 * 1024)) + 600)

    rc, out, err = cli.run("pull", [device_id, storage, f.remote_path, incoming_sub], timeout)
    if rc != 0 or not pull_reported_success(out):
        _cleanup_dir(incoming_sub)
        manifest.mark_status(fp, storage, f, "failed",
                             f"pull did not report success (rc={rc})", run_id)
        log.error("pull failed for %s", f.remote_path)
        return "failed"

    produced = discover_pulled_file(incoming_sub, os.path.basename(f.remote_path))
    if produced is None:
        _cleanup_dir(incoming_sub)
        manifest.mark_status(fp, storage, f, "failed", "pulled output not found", run_id)
        log.error("pulled output not discovered for %s", f.remote_path)
        return "failed"

    # Move to a unique .partial on the same volume before verifying.
    partial = os.path.join(incoming_dir, f"{uuid.uuid4().hex}.partial")
    os.replace(produced, partial)
    _cleanup_dir(incoming_sub)

    actual_size = os.path.getsize(partial)
    if actual_size != f.size:
        _quarantine(partial, quarantine_dir, f, id_hash)
        manifest.mark_status(fp, storage, f, "quarantined",
                             f"size mismatch: expected {f.size}, got {actual_size}", run_id)
        log.error("size mismatch for %s (expected %d, got %d)", f.remote_path, f.size, actual_size)
        return "failed"

    sha = sha256_file(partial)
    fsync_path(partial)

    kind, target = resolve_target(final_default, id_hash, f.size, sha)
    if kind == "exists":
        # Identical content already present at `target` — idempotent completion.
        os.remove(partial)
        manifest.upsert_completed(fp, storage, f, sha, os.path.relpath(target, dest), run_id)
        log.info("already present (identical) %s -> %s", f.remote_path, os.path.relpath(target, dest))
        return "skipped"

    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.replace(partial, target)  # atomic on same volume
    fsync_dir(os.path.dirname(target))
    manifest.upsert_completed(fp, storage, f, sha, os.path.relpath(target, dest), run_id)
    log.info("backed up %s -> %s", f.remote_path, os.path.relpath(target, dest))
    return "transferred"


def resolve_target(final_default: str, id_hash: str, size: int, sha: str) -> tuple[str, str]:
    """Choose a collision-safe destination, never overwriting different content.

    Returns ``(kind, path)`` where:
      * ``("new", path)``    -> nothing is at ``path``; write the pulled file there.
      * ``("exists", path)`` -> an identical (size + SHA-256) file already sits at
                                ``path``; do not overwrite, record ``path`` as-is.

    A candidate that exists but cannot be stat'd/read (OSError) is skipped rather
    than assumed identical, so a verified pulled copy is never discarded.
    """
    stem, ext = os.path.splitext(final_default)
    candidates = [final_default, f"{stem}~{id_hash}{ext}"]
    candidates += [f"{stem}~{id_hash}-{n}{ext}" for n in range(1, 1000)]
    for cand in candidates:
        if not os.path.exists(cand):
            return "new", cand
        try:
            same = os.path.getsize(cand) == size and sha256_file(cand) == sha
        except OSError:
            continue  # cannot verify this candidate; try the next slot
        if same:
            return "exists", cand
        # different content at this candidate -> try the next name
    raise RuntimeError(f"could not find a non-colliding destination for {final_default}")


def _quarantine(path: str, quarantine_dir: str, f: MediaFile, id_hash: str) -> None:
    try:
        os.makedirs(quarantine_dir, exist_ok=True)
        name = sanitize_component(f"{id_hash}-{os.path.basename(f.remote_path)}.partial")
        os.replace(path, os.path.join(quarantine_dir, name))
    except OSError as exc:
        log.warning("could not quarantine %s: %s", path, exc)
        try:
            os.remove(path)
        except OSError:
            pass


def _cleanup_dir(path: str) -> None:
    if not os.path.isdir(path):
        return
    for base, dirs, names in os.walk(path, topdown=False):
        for n in names:
            try:
                os.remove(os.path.join(base, n))
            except OSError:
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(base, d))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def do_verify(manifest: Manifest, dest: str) -> int:
    rows = manifest.completed_rows()
    ok = missing = mismatch = 0
    for row in rows:
        relpath = row["local_relpath"]
        local = os.path.join(dest, relpath) if relpath else None
        if not local or not os.path.isfile(local):
            missing += 1
            manifest.requeue_import_row(row["id"], "verify: local file missing")
            log.warning("MISSING %s", relpath)
            continue
        if os.path.getsize(local) != row["size"]:
            mismatch += 1
            manifest.requeue_import_row(row["id"], "verify: size mismatch")
            log.warning("SIZE MISMATCH %s", relpath)
            continue
        if row["sha256"]:
            if sha256_file(local) != row["sha256"]:
                mismatch += 1
                manifest.requeue_import_row(row["id"], "verify: sha256 mismatch")
                log.warning("SHA256 MISMATCH %s", relpath)
                continue
        ok += 1
    print(f"verify: ok={ok} missing={missing} mismatch={mismatch} (total {len(rows)})")
    return EXIT_OK if (missing == 0 and mismatch == 0) else EXIT_TRANSFER


# --- Argument parsing & main -------------------------------------------------

def derive_mount(dest: str) -> str:
    parts = os.path.normpath(dest).split(os.sep)
    # /Volumes/<name>/... -> /Volumes/<name>
    if len(parts) >= 3 and parts[1] == "Volumes":
        return os.sep + os.path.join("Volumes", parts[2])
    return dest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="swiftmtp-photo-backup.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Incremental, resumable, read-only photo/video backup from an Android/MTP\n"
            "device using SwiftMTP's stock swiftmtp-cli. Never modifies the device."
        ),
        epilog=(
            "Examples:\n"
            "  # Preview what would be backed up (default):\n"
            "  swiftmtp-photo-backup.py\n\n"
            "  # Actually transfer pending files:\n"
            "  swiftmtp-photo-backup.py --run\n\n"
            "  # Also back up /Movies and verify existing local copies:\n"
            "  swiftmtp-photo-backup.py --source /DCIM --source /Pictures --source /Movies --run\n"
            "  swiftmtp-photo-backup.py --verify\n"
        ),
    )
    p.add_argument("--dest", default=DEFAULT_DEST,
                   help=f"destination directory (default: {DEFAULT_DEST})")
    p.add_argument("--mount", default=None,
                   help="configured volume mount point (default: derived from --dest)")
    p.add_argument("--cli", default=DEFAULT_CLI,
                   help=f"path to swiftmtp-cli (default: {DEFAULT_CLI})")
    p.add_argument("--source", action="append", metavar="ROOT", dest="sources",
                   help=f"device source root, repeatable (default: {' '.join(DEFAULT_SOURCES)}). "
                        "Add /Movies to include videos folder.")
    p.add_argument("--device", default=None,
                   help="explicit device id or any pipe-separated part (vendor|product|serial)")
    p.add_argument("--storage", default=None, help="explicit storage id (e.g. 65537)")

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true", help="perform transfers (default is dry run)")
    mode.add_argument("--dry-run", action="store_true", help="preview only (default)")
    mode.add_argument("--verify", action="store_true",
                      help="recheck completed local files (size + SHA-256); no phone/CLI needed; "
                           "creates nothing if there is no destination/manifest yet")

    p.add_argument("--min-free-gib", type=float, default=DEFAULT_MIN_FREE_GIB,
                   help=f"free-space reserve on destination (default: {DEFAULT_MIN_FREE_GIB} GiB)")
    p.add_argument("--max-depth", type=int, default=40, help="max recursion depth (default: 40)")
    p.add_argument("--list-timeout", type=int, default=180,
                   help="timeout (s) for devices/storages/ls (default: 180)")
    p.add_argument("--pull-timeout", type=int, default=0,
                   help="timeout (s) per pull; 0 = auto by size (default: 0)")
    p.add_argument("--allow-unmounted-dest", action="store_true",
                   help="TEST ONLY: skip the real-volume mount-point check (does not weaken "
                        "writability/containment checks)")
    p.add_argument("--skip-aft-check", action="store_true",
                   help="skip the Android File Transfer conflict preflight (override only if you "
                        "know its agent won't grab the device)")
    p.add_argument("-v", "--verbose", action="store_true", help="verbose console output")
    return p


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    setup_console_logging(args.verbose)

    dest = os.path.abspath(os.path.expanduser(args.dest))
    mount = os.path.abspath(os.path.expanduser(args.mount)) if args.mount else derive_mount(dest)
    roots = args.sources if args.sources else list(DEFAULT_SOURCES)
    mode = "verify" if args.verify else ("run" if args.run else "dry-run")

    lock_fd = None
    manifest = None
    try:
        if mode == "verify":
            # Phone/CLI/AFT-independent and side-effect free when there is nothing
            # to verify: never create the destination or the manifest.
            if not os.path.isdir(dest):
                print(f"nothing to verify: destination {dest} does not exist (no local backups).")
                return EXIT_OK
            db_path = os.path.join(dest, BACKUP_DIRNAME, "manifest.sqlite3")
            if not os.path.isfile(db_path):
                print(f"nothing to verify: no manifest at {db_path} (nothing backed up here yet).")
                return EXIT_OK
            # Manifest exists: verify may write its normal status/logs.
            setup_file_logging(dest)
            lock_fd = acquire_lock(dest)
            manifest = Manifest(db_path)
            log.info("verify mode: rechecking completed local files under %s", dest)
            return do_verify(manifest, dest)

        # run / dry-run touch the device.
        check_cli(args.cli)
        if not args.skip_aft_check:
            check_android_file_transfer()
        check_mount(mount, args.allow_unmounted_dest)
        cli = CLI(args.cli, args.list_timeout)

        device_id, model = resolve_device(cli, args.device)
        register_secret(device_id)
        for part in device_id.split("|")[2:]:
            register_secret(part)  # serial number(s)
        fp = device_fingerprint(device_id)
        storage = resolve_storage(cli, device_id, args.storage)
        log.info("device fp=%s model=%s storage=%s", fp, model, storage)
        db_path = os.path.join(dest, BACKUP_DIRNAME, "manifest.sqlite3")

        if mode == "run":
            ensure_destination(dest, mount)
            setup_file_logging(dest)
            lock_fd = acquire_lock(dest)
            manifest = Manifest(db_path)
            return do_run(manifest, cli, dest, device_id, model, fp, storage,
                          roots, args.max_depth, args.min_free_gib, args.pull_timeout)

        # dry-run: read-only preview; creates no destination/manifest/logs/lock.
        completed = load_completed_map(db_path, fp, storage)
        return do_dry_run(cli, dest, mount, device_id, model, fp, storage,
                          roots, args.max_depth, args.min_free_gib, completed)

    except PreflightError as exc:
        log.error("preflight: %s", exc)
        return EXIT_PREFLIGHT
    except (DeviceError, InventoryError) as exc:
        log.error("%s", exc)
        return EXIT_DEVICE
    except KeyboardInterrupt:
        log.error("interrupted")
        return EXIT_INTERRUPT
    finally:
        if manifest is not None:
            manifest.close()
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
