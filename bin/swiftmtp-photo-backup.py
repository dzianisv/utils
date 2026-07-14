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
import shlex
import sqlite3
import shutil
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

# Fail-closed guard against a silent false-empty backup. If the device storage
# reports at least this many bytes in use yet the inventory finds ZERO media in
# every (existing) source root, the empty listing is far more likely a stock
# `swiftmtp-cli ls` failure — it can return no output at all for directories that
# demonstrably exist on the device (path resolution and `pull` still work) — than a
# genuinely empty phone. Reporting "0 files, Done" in that state is dangerous for a
# backup tool, so we refuse it. A truly empty device can override with
# --allow-empty-inventory.
EMPTY_INVENTORY_USED_FLOOR = 1 * GIB

# The native MTP inventory helper (see bin/mtpinv/). It talks to the device with
# the same go-mtpx library SwiftMTP bundles, but WITHOUT the stock CLI's broken
# stale-generation `ls` wrapper, so it enumerates reliably and emits JSON. It is
# read-only with respect to the device. Discovered next to this script by default.
MTP_HELPER_DIRNAME = "mtpinv"
DEFAULT_HELPER_TIMEOUT = 900  # seconds for a full recursive metadata walk

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


class LockError(Exception):
    """Another run already holds the single-run lock."""


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


class AdbError(Exception):
    """An adb operation failed, timed out, or returned ambiguous output.

    Fail-closed marker for the device-side deletion path: any AdbError must be
    treated as "cannot safely proceed", never as success. Probes that merely find
    an unexpected/ambiguous result return None instead of raising; AdbError is
    reserved for transport-level failures (timeout, adb not runnable, unresolvable
    device) that abort the operation.
    """


class DeletionError(Exception):
    """A source-deletion precondition failed (e.g. an unmappable remote path).

    Raised to refuse deletion of a single file; the phone file is always kept.
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


# `storages` prints usage as "<name> (<free> free / <total> total)", e.g.
# "Internal shared storage (737.51 MB free / 109.47 GB total)". Parsed best-effort
# only to power the empty-inventory guard; any failure yields None so the guard
# simply does not engage (never a hard error on an unfamiliar format).
_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}
_STORAGE_USAGE_RE = re.compile(
    r"\(\s*([\d.]+)\s*([KMGT]?B)\s+free\s*/\s*([\d.]+)\s*([KMGT]?B)\s+total\s*\)"
)


def storage_used_bytes(name: str) -> int | None:
    """Best-effort used bytes (total - free) parsed from a `storages` display name.

    Returns None when the free/total pattern is absent or unparseable — the caller
    treats None as "unknown usage" and skips the guard rather than guessing.
    """
    m = _STORAGE_USAGE_RE.search(name)
    if not m:
        return None
    try:
        free = float(m.group(1)) * _SIZE_UNITS[m.group(2)]
        total = float(m.group(3)) * _SIZE_UNITS[m.group(4)]
    except (KeyError, ValueError):
        return None
    used = int(total - free)
    return used if used >= 0 else None


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


def resolve_storage(cli: CLI, device_id: str, requested: str | None) -> tuple[str, int | None]:
    """Return (storage_id, used_bytes_or_None) for the selected storage."""
    rc, out, err = cli.run("storages", [device_id], cli.list_timeout)
    if "Error initializing device" in out or "Failed to fetch storages" in out:
        raise DeviceError(f"could not fetch storages: {out.strip() or err.strip()}")
    if rc != 0 and not out.strip():
        raise DeviceError(f"`storages` failed (rc={rc}): {err.strip()}")
    storages = parse_storages(out)
    if not storages:
        raise DeviceError("device reported no usable storage")
    if requested:
        for sid, name in storages:
            if sid == requested:
                return sid, storage_used_bytes(name)
        raise DeviceError(f"--storage {requested!r} not found on device")
    if len(storages) == 1:
        return storages[0][0], storage_used_bytes(storages[0][1])
    listing = "\n".join(f"  {sid}  {name}" for sid, name in storages)
    raise DeviceError("Multiple storages found; select one with --storage <id>:\n" + listing)


# --- ADB (device-side verification + single-file deletion) -------------------
# SAFETY CONTRACT for this whole section:
#   * The Adb class performs ONLY read-only probes (stat, sha256sum, symlink and
#     existence tests, getprop) PLUS exactly one mutating operation:
#     `delete_regular_file`, which runs `rm -- <one shlex.quoted absolute path>`
#     and nothing else. There is deliberately NO recursive delete, NO directory
#     removal, NO wildcard, and NO generic command path. Removing a single,
#     independently re-verified regular file is the ONLY device mutation this
#     entire tool can perform.
#   * Every device command is handed as ONE pre-quoted argv element to
#     `adb -s <serial> shell <cmd>` with NO intervening host shell, so any shell
#     metacharacters in a path are treated literally (injection-safe: verified on
#     hardware against spaces, quotes, ;, $(), backticks, |, &, *, ?, tabs,
#     unicode, and leading-dash names).
#   * Any probe that is ambiguous or fails returns None (transport failures raise
#     AdbError); callers ALWAYS fail closed (keep the phone file) on None/raise.
DEFAULT_ADB = "/opt/homebrew/bin/adb"


class Adb:
    """Injection-safe adb wrapper: read-only probes plus single-file ``rm --``.

    ``delete_regular_file`` is the only mutating method; all others are read-only.
    Probes return None on any ambiguity so callers fail closed.
    """

    def __init__(self, adb_path: str, serial: str, timeout: int):
        self.adb_path = adb_path
        self.serial = serial
        self.timeout = timeout

    def _shell(self, cmd_str: str) -> tuple[int, str, str]:
        # Defense in depth: callers already reject these in path validation, but a
        # NUL/newline/CR here could split or truncate the single shell command line
        # we hand to adb, so refuse them unconditionally.
        if any(c in cmd_str for c in ("\x00", "\n", "\r")):
            raise AdbError("refusing adb shell command containing NUL/newline/CR")
        cmd = [self.adb_path, "-s", self.serial, "shell", cmd_str]
        log.debug("exec adb: %s", _redact(f"adb -s {self.serial} shell {cmd_str}"))
        try:
            proc = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise AdbError(f"adb shell timed out after {self.timeout}s")
        except OSError as exc:
            raise AdbError(f"could not run adb ({self.adb_path}): {exc}")
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def stat_type_size(self, path: str) -> tuple[str, int] | None:
        """Return (file_type, size_bytes) via ``stat -c '%F|%s'``, or None.

        None means the file is absent or the output did not match exactly; the
        caller must then disambiguate with ``exists`` and never assume a size.
        """
        rc, out, _err = self._shell("stat -c '%F|%s' -- " + shlex.quote(path))
        if rc != 0:
            return None
        parts = out.strip().rsplit("|", 1)
        if len(parts) != 2:
            return None
        type_str, size_str = parts
        if not type_str or not size_str.isdigit():
            return None
        return type_str, int(size_str)

    def is_symlink(self, path: str) -> bool | None:
        """True if the path is a symlink, False if not, None if ambiguous.

        Uses a stdout sentinel (not exit code) because the test-and-printf always
        exits 0. A None result must be treated as "do not delete".
        """
        rc, out, _err = self._shell(
            "[ -L " + shlex.quote(path) + " ] && printf SYMLINK || printf NOTLINK"
        )
        s = out.strip()
        if s == "SYMLINK":
            return True
        if s == "NOTLINK":
            return False
        return None

    def sha256(self, path: str) -> str | None:
        """Return the lowercase 64-hex SHA-256 of the on-device file, or None."""
        rc, out, _err = self._shell("sha256sum -- " + shlex.quote(path))
        if rc != 0:
            return None
        m = re.match(r"^([0-9a-f]{64})(?:\s|$)", out.strip())
        return m.group(1) if m else None

    def exists(self, path: str) -> bool | None:
        """True if the path exists, False if not, None if ambiguous (sentinel)."""
        rc, out, _err = self._shell(
            "[ -e " + shlex.quote(path) + " ] && printf PRESENT || printf ABSENT"
        )
        s = out.strip()
        if s == "PRESENT":
            return True
        if s == "ABSENT":
            return False
        return None

    def delete_regular_file(self, path: str) -> tuple[int, str, str]:
        """Run exactly ``rm -- <one quoted path>`` — the ONLY mutating command.

        Asserts the constructed command is precisely a single-file ``rm --`` (three
        tokens: ``rm``, ``--``, the path) so this method can never be repurposed
        into a recursive/wildcard/multi-target deletion.
        """
        cmd_str = "rm -- " + shlex.quote(path)
        # Load-bearing guard (NOT asserts — those are stripped under `python -O`):
        # prove the command is exactly the three tokens `rm`, `--`, <path> so this
        # method can never be repurposed into a recursive/wildcard/multi-target rm.
        if not cmd_str.startswith("rm -- ") or shlex.split(cmd_str) != ["rm", "--", path]:
            raise AdbError("refusing malformed delete command (not a single-file `rm -- <path>`)")
        return self._shell(cmd_str)

    def getprop_serialno(self) -> str | None:
        """Return the device's live ``ro.serialno`` (used for the identity gate)."""
        rc, out, _err = self._shell("getprop ro.serialno")
        if rc != 0:
            return None
        return out.strip() or None


def resolve_adb_device(adb_path: str, requested_serial: str | None) -> str:
    """Return the single authorized adb serial to operate on (fail closed).

    Parses ``adb devices`` (``SERIAL\\tSTATE``). Only STATE=="device" (authorized)
    is usable; "unauthorized"/"offline" serials are surfaced in errors but never
    selected. A requested serial must match exactly one authorized device; with no
    request we require exactly one authorized device and otherwise demand
    ``--adb-serial``. Full serials are secrets — only fingerprints are ever logged.
    """
    try:
        proc = subprocess.run(
            [adb_path, "devices"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise AdbError("`adb devices` timed out")
    except OSError as exc:
        raise AdbError(f"could not run adb ({adb_path}): {exc}")
    if proc.returncode != 0:
        raise AdbError(f"`adb devices` failed (rc={proc.returncode}): {proc.stderr.strip()}")

    authorized: list[str] = []
    unusable: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.rstrip("\r")
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        serial, state = parts[0].strip(), parts[1].strip()
        if not serial:
            continue
        if state == "device":
            authorized.append(serial)
        elif state in ("unauthorized", "offline"):
            unusable.append(f"{device_fingerprint(serial)}:{state}")
    hint = f" (unauthorized/offline: {', '.join(unusable)})" if unusable else ""

    if requested_serial:
        if requested_serial in authorized:
            return requested_serial
        raise AdbError("--adb-serial did not match an authorized adb device" + hint)
    if len(authorized) == 1:
        return authorized[0]
    if not authorized:
        raise AdbError(
            "no authorized adb device (connect + unlock the phone and accept the USB "
            "debugging prompt)" + hint
        )
    raise AdbError(
        f"multiple authorized adb devices ({len(authorized)}); select one with "
        "--adb-serial <serial>"
    )


def map_remote_to_android(remote_path: str, android_root: str) -> str:
    """Map an MTP remote path to its on-device Android filesystem path (fail closed).

    The MTP storage root corresponds to ``android_root`` (default /sdcard). We
    refuse anything that could escape that root or that the adb transport cannot
    represent unambiguously: non-absolute inputs, ``.``/``..`` components, empty
    paths, and NUL/newline/CR/control chars. Containment is enforced both
    structurally (must start with ``root + "/"``) and via ``os.path.normpath``.
    """
    if not isinstance(remote_path, str) or not remote_path.startswith("/"):
        raise DeletionError(f"remote path is not an absolute string: {remote_path!r}")
    for ch in remote_path:
        o = ord(ch)
        if ch == "\x00" or o < 0x20 or o == 0x7F:
            raise DeletionError("remote path contains a NUL/newline/control character")
    remote_components = [c for c in remote_path.split("/") if c != ""]
    if not remote_components:
        raise DeletionError("remote path has no components (cannot map a bare '/')")
    for c in remote_components:
        if c in (".", ".."):
            raise DeletionError(f"remote path contains a '.'/'..' component: {remote_path!r}")

    if not isinstance(android_root, str) or not android_root.startswith("/"):
        raise DeletionError(f"android root is not an absolute path: {android_root!r}")
    for ch in android_root:
        o = ord(ch)
        if ch == "\x00" or o < 0x20 or o == 0x7F:
            raise DeletionError("android root contains a NUL/newline/control character")
    root = android_root.rstrip("/")
    if not root:
        raise DeletionError("android root must not be the filesystem root '/'")
    for c in [c for c in root.split("/") if c != ""]:
        if c in (".", ".."):
            raise DeletionError(f"android root contains a '.'/'..' component: {android_root!r}")

    android_path = root + "/" + "/".join(remote_components)
    if not android_path.startswith(root + "/"):
        raise DeletionError("mapped path is not contained under the android root")
    if os.path.normpath(android_path) != android_path:
        raise DeletionError(f"mapped path is not normalized (traversal risk): {android_path!r}")
    return android_path


def _prepare_adb_for_delete(adb_path: str, requested_serial: str | None,
                            device_id: str, adb_timeout: int) -> "Adb":
    """Validate adb, resolve the target serial, and PROVE it is the same physical
    device we backed up before enabling deletion. Fails closed (raises) on any
    mismatch so we can never delete from a different phone than the one we imaged.

    Same-physical-device gate (all three must agree):
      1. the MTP device id has a serial component,
      2. the resolved adb serial equals one of those components, and
      3. the device's live ``getprop ro.serialno`` equals that adb serial.
    Full serials are treated as secrets; only fingerprints appear in errors/logs.
    """
    if not os.path.isfile(adb_path) or not os.access(adb_path, os.X_OK):
        raise PreflightError(
            f"adb not found or not executable at {adb_path}. Install platform-tools "
            "or pass --adb PATH."
        )
    adb_serial = resolve_adb_device(adb_path, requested_serial)
    register_secret(adb_serial)

    serial_parts = device_id.split("|")[2:]
    if not serial_parts:
        raise DeviceError(
            "cannot verify device identity for deletion: the MTP device id has no "
            "serial component; refusing --delete-after-verify"
        )
    if adb_serial not in serial_parts:
        raise DeviceError(
            "adb device does not match the MTP device (serial mismatch); refusing to "
            f"delete. adb fp={device_fingerprint(adb_serial)}"
        )
    adb = Adb(adb_path, adb_serial, adb_timeout)
    live = adb.getprop_serialno()
    if live is not None:
        register_secret(live)
    if live != adb_serial:
        raise DeviceError(
            "adb device did not confirm its serial (getprop ro.serialno mismatch or no "
            f"response); refusing to delete. adb fp={device_fingerprint(adb_serial)}"
        )
    log.info("delete-after-verify armed: adb device confirmed (fp=%s)",
             device_fingerprint(adb_serial))
    return adb


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


def resolve_mtp_helper(explicit: str | None) -> str | None:
    """Locate the native mtpinv helper binary, or None if unavailable.

    Search order: explicit --mtp-helper, $SWIFTMTP_MTPINV, bin/mtpinv/mtpinv next
    to this script, then $PATH. Returns an executable path or None.
    """
    candidates: list[str] = []
    if explicit:
        candidates.append(os.path.abspath(os.path.expanduser(explicit)))
    env = os.environ.get("SWIFTMTP_MTPINV")
    if env:
        candidates.append(os.path.abspath(os.path.expanduser(env)))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, MTP_HELPER_DIRNAME, "mtpinv"))
    on_path = shutil.which("mtpinv")
    if on_path:
        candidates.append(on_path)
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _root_for(remote_path: str, roots: list[str]) -> str | None:
    """Return the source root that contains remote_path, or None (containment)."""
    for root in roots:
        base = root.rstrip("/")
        if remote_path == base or remote_path.startswith(base + "/"):
            return root
    return None


def helper_inventory(helper_path: str, storage_id: str, roots: list[str],
                     timeout: int = DEFAULT_HELPER_TIMEOUT
                     ) -> tuple[list[MediaFile], list[tuple[str, str]]]:
    """Enumerate media via the native mtpinv helper (JSON). Read-only on device.

    JSON avoids the fixed-width `ls` ambiguity entirely: names/sizes/paths are
    delimited unambiguously. We still fail closed per entry — only well-formed
    media whose path is contained under a requested root is trusted.
    """
    cmd = [helper_path, "-storage", str(storage_id), "inventory", *roots]
    log.debug("exec helper: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout, text=True,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise DeviceError(f"mtp helper inventory timed out after {timeout}s")
    except OSError as exc:
        raise InventoryError(f"could not run mtp helper {helper_path}: {exc}")
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or f"rc={proc.returncode}").strip()
        raise InventoryError(f"mtp helper inventory failed: {detail}")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise InventoryError(f"mtp helper returned invalid JSON: {exc}")

    media: list[MediaFile] = []
    for entry in data.get("files", []):
        if not isinstance(entry, dict) or entry.get("is_dir"):
            continue
        name = entry.get("name") or ""
        path = entry.get("path") or ""
        size = entry.get("size")
        # Fail-closed hygiene: never trust a name that could break local paths,
        # a non-integer/negative size, a non-media file, or a path that escapes
        # the requested roots.
        if not name or not path or "\x00" in name or "/" in name:
            continue
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            continue
        if not is_media(name):
            continue
        root = _root_for(path, roots)
        if root is None:
            continue
        media.append(MediaFile(path, name, size, str(entry.get("mtime") or ""), root))

    warnings: list[tuple[str, str]] = []
    for e in data.get("errors", []):
        if isinstance(e, dict):
            warnings.append((str(e.get("root", "")), str(e.get("error", ""))))
    # Mirror the ls backend's "no source root could be inventoried" hard failure:
    # if every requested root errored (and nothing was found), fail closed
    # regardless of reported storage usage rather than returning a clean empty.
    errored_roots = {r for r, _ in warnings}
    if not media and set(roots) and errored_roots >= set(roots):
        detail = "; ".join(f"{r}: {e}" for r, e in warnings[:3])
        raise InventoryError(f"no source root could be inventoried: {detail}")
    log.info("inventoried %d media file(s) across %s via native mtp helper",
             len(media), ", ".join(roots))
    return media, warnings


def _ls_walk_inventory(cli: CLI, device_id: str, storage_id: str, roots: list[str],
                       max_depth: int) -> tuple[list[MediaFile], list[tuple[str, str]]]:
    media: list[MediaFile] = []
    warnings: list[tuple[str, str]] = []
    ok_roots = 0
    for root in roots:
        try:
            walk_root(cli, device_id, storage_id, root, media, max_depth)
            ok_roots += 1
            log.info("inventoried %s (swiftmtp-cli ls)", root)
        except DirListError as exc:
            warnings.append((root, str(exc)))
            log.warning("source root %s unavailable (skipping): %s", root, exc)
        # DeviceError propagates: a lost connection is a hard failure.
    if ok_roots == 0:
        raise InventoryError("no source root could be inventoried")
    return media, warnings


def inventory(cli: CLI, device_id: str, storage_id: str, roots: list[str],
              max_depth: int, storage_used: int | None = None,
              helper: str | None = None
              ) -> tuple[list[MediaFile], list[tuple[str, str]]]:
    if helper is not None:
        media, warnings = helper_inventory(helper, storage_id, roots)
    else:
        media, warnings = _ls_walk_inventory(cli, device_id, storage_id, roots, max_depth)
    # Fail closed on an implausible empty inventory: the enumeration backend
    # returned zero media while the device reports substantial storage in use.
    # That is the signature of a failed listing (e.g. the stock `swiftmtp-cli ls`
    # returning empty output for directories that actually exist) — not a
    # genuinely empty device — so refuse to report a false-empty backup.
    if (not media
            and storage_used is not None
            and storage_used > EMPTY_INVENTORY_USED_FLOOR):
        raise InventoryError(
            "no media found in any source root (" + ", ".join(roots) + "), but the "
            "device reports ~" + human_bytes(storage_used) + " of storage in use, so the "
            "empty inventory cannot be trusted. This usually means the enumeration backend "
            "failed (e.g. the stock `swiftmtp-cli ls` returns empty listings on this device; "
            "build the native helper at bin/mtpinv/ — see its README). Refusing to report an "
            "empty backup. If this device genuinely has no photos in these folders, re-run "
            "with --allow-empty-inventory."
        )
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
        self._migrate()

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

    def _migrate(self) -> None:
        """Idempotently add deletion-tracking columns/table to an existing manifest.

        Safe to run repeatedly and against the pre-existing production DB (which
        already holds completed + failed rows): each ALTER is guarded by a
        PRAGMA table_info presence check, and the events table uses
        CREATE TABLE IF NOT EXISTS. No existing row/column is ever rewritten.
        """
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(imports)")}
        additions = [
            ("deletion_status", "ALTER TABLE imports ADD COLUMN deletion_status TEXT"),
            ("deletion_error", "ALTER TABLE imports ADD COLUMN deletion_error TEXT"),
            ("source_deleted_at", "ALTER TABLE imports ADD COLUMN source_deleted_at TEXT"),
            ("delete_attempts",
             "ALTER TABLE imports ADD COLUMN delete_attempts INTEGER NOT NULL DEFAULT 0"),
        ]
        with self.conn:
            for col, ddl in additions:
                if col not in existing:
                    self.conn.execute(ddl)
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS deletion_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    import_id INTEGER,
                    device_fingerprint TEXT,
                    storage_id TEXT,
                    remote_path TEXT,
                    action TEXT NOT NULL,
                    result TEXT NOT NULL,
                    detail TEXT,
                    run_id TEXT,
                    created_at TEXT NOT NULL
                )
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

    # -- source deletion bookkeeping --
    def rows_pending_deletion(self, fp: str, storage: str):
        """Completed rows for this device/storage still eligible for source deletion.

        A row is eligible when it has never been processed (deletion_status IS NULL)
        or a prior attempt is retryable ('pending_delete' or 'delete_failed'). Rows
        already 'deleted' or 'source_absent' are excluded so they are never retried.
        """
        return self.conn.execute(
            "SELECT * FROM imports WHERE status='completed' AND device_fingerprint=? "
            "AND storage_id=? AND (deletion_status IS NULL OR deletion_status IN "
            "('pending_delete','delete_failed'))",
            (fp, storage),
        ).fetchall()

    def mark_deletion(self, import_id: int, status: str, error: str | None,
                      deleted_at: str | None = None) -> None:
        """Record the outcome of a deletion attempt for one import row.

        ``source_deleted_at`` is only set the first time it is supplied (COALESCE)
        so a later retry cannot clobber the original deletion timestamp;
        ``delete_attempts`` increments on every call.
        """
        with self.conn:
            self.conn.execute(
                "UPDATE imports SET deletion_status=?, deletion_error=?, "
                "source_deleted_at=COALESCE(?, source_deleted_at), "
                "delete_attempts=delete_attempts+1, updated_at=? WHERE id=?",
                (status, error, deleted_at, now_iso(), import_id),
            )

    def record_deletion_event(self, import_id: int | None, fp: str, storage: str,
                              remote_path: str, action: str, result: str,
                              detail: str | None, run_id: str | None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO deletion_events(import_id, device_fingerprint, storage_id, "
                "remote_path, action, result, detail, run_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (import_id, fp, storage, remote_path, action, result, detail, run_id, now_iso()),
            )


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


# --- Source deletion (device-side, single-file, fail closed) -----------------

def delete_source_for_row(adb: "Adb", manifest: Manifest, dest: str, row,
                          android_root: str, run_id: str) -> str:
    """Delete ONE phone file only after re-proving the local backup is intact and
    the on-device file is byte-identical. Returns one of ``'deleted'``,
    ``'failed'``, ``'absent'``, or ``'skip'``.

    Every check must affirmatively pass. On ANY ambiguity or mismatch we fail
    closed: the row is marked ``delete_failed`` (retried next run) and the phone
    file is KEPT. The single ``rm --`` is only reached after the local copy is
    re-verified (size + SHA-256) AND the phone file is confirmed a non-symlink
    regular file whose size and SHA-256 match the manifest.

    Known limitation (inherent to adb, not a defect): the sequence "verify size +
    SHA-256" then "rm <path>" is not atomic — MTP/adb offer no device-side
    compare-and-delete. If the file at that exact path were replaced in the
    sub-second window between the SHA-256 probe and the ``rm``, ``rm`` would remove
    whatever now occupies the path. We accept this narrow window: deletion is only
    ever armed for a device we just imaged and each file is re-hashed immediately
    before removal, so it is far tighter than a size/mtime-only check.
    """
    remote_path = row["remote_path"]
    size = row["size"]
    sha = row["sha256"]
    relpath = row["local_relpath"]
    fp = row["device_fingerprint"]
    storage = row["storage_id"]
    import_id = row["id"]

    def fail(detail: str, action: str = "verify") -> str:
        manifest.mark_deletion(import_id, "delete_failed", detail)
        manifest.record_deletion_event(import_id, fp, storage, remote_path, action,
                                       "failed", detail, run_id)
        log.warning("keep (not deleting) %s: %s", os.path.basename(remote_path), detail)
        return "failed"

    # 1. We can only re-verify against durable local metadata.
    if sha is None or relpath is None:
        return fail("missing local metadata (sha/relpath)")

    # 2. Local re-verification (defense in depth; reconcile already requeued any
    #    missing/wrong-size local copy, so a still-'completed' row should pass).
    local = os.path.join(dest, relpath)
    if not os.path.isfile(local):
        return fail("local file missing")
    try:
        if os.path.getsize(local) != size:
            return fail("local size mismatch")
        if sha256_file(local) != sha:
            return fail("local sha mismatch")
    except OSError as exc:
        return fail(f"local read error: {exc}")

    # 3. Map to the on-device Android path (fails closed on any traversal risk).
    try:
        android = map_remote_to_android(remote_path, android_root)
    except DeletionError as exc:
        return fail(str(exc), action="map")

    # 4. Phone verification — every probe must affirmatively pass, else keep.
    symlink = adb.is_symlink(android)
    if symlink is not False:  # True (symlink) or None (ambiguous)
        return fail("phone path is a symlink or ambiguous")

    typesize = adb.stat_type_size(android)
    if typesize is None:
        present = adb.exists(android)
        if present is False:
            # The source is already gone (e.g. removed on a prior run before its
            # bookkeeping committed). Not a failure: record and move on.
            manifest.mark_deletion(import_id, "source_absent", None, deleted_at=now_iso())
            manifest.record_deletion_event(import_id, fp, storage, remote_path,
                                           "verify_absent", "absent", None, run_id)
            log.info("source already absent %s", os.path.basename(remote_path))
            return "absent"
        return fail("phone stat ambiguous")
    ftype, fsize = typesize
    if ftype != "regular file":
        return fail("phone path is not a regular file")
    if fsize != size:
        return fail("phone size mismatch (source changed)")

    phone_sha = adb.sha256(android)
    if phone_sha is None:
        return fail("phone sha ambiguous")
    if phone_sha != sha:
        return fail("phone sha mismatch (source changed)")

    # 5. Delete exactly this one, fully re-verified, regular file.
    try:
        adb.delete_regular_file(android)
    except AdbError as exc:
        return fail(f"rm failed: {exc}", action="delete")

    # 6. Prove absence before recording success.
    gone = adb.exists(android)
    if gone is False:
        manifest.mark_deletion(import_id, "deleted", None, deleted_at=now_iso())
        manifest.record_deletion_event(import_id, fp, storage, remote_path,
                                       "delete", "ok", None, run_id)
        log.info("deleted source %s", os.path.basename(remote_path))
        return "deleted"
    # Present or ambiguous after rm: keep, marked for retry on the next run.
    return fail("still present after rm", action="delete")


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
            raise LockError("another swiftmtp-photo-backup run holds the lock")
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
               min_free_gib: float, completed: dict,
               storage_used: int | None = None, helper: str | None = None) -> int:
    """Preview only. Reads the device and an EXISTING manifest; writes nothing and
    never creates the destination, manifest, logs, or lock."""
    files, warnings = inventory(cli, device_id, storage, roots, max_depth, storage_used, helper)
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
        try:
            final = build_final_path(dest, device_dir, storage, f.remote_path)
            print(f"  + {f.remote_path} -> {os.path.relpath(final, dest)} ({human_bytes(f.size)})")
        except ValueError as exc:
            print(f"  ! {f.remote_path} -> UNSAFE destination, would be skipped ({exc})")
    if len(pending) > 20:
        print(f"  … and {len(pending) - 20} more")
    if pending_bytes > usable:
        print("RESULT: pending bytes EXCEED usable space; --run would be refused.")
    else:
        print("RESULT: OK — re-run with --run to transfer.")
    return EXIT_OK


def do_run(manifest: Manifest, cli: CLI, dest: str, device_id: str, model: str,
           fp: str, storage: str, roots: list[str], max_depth: int,
           min_free_gib: float, pull_timeout: int,
           storage_used: int | None = None, helper: str | None = None,
           adb: "Adb | None" = None, android_root: str = "/sdcard",
           delete_after_verify: bool = False) -> int:
    run_id = manifest.start_run("run", fp, storage, dest)
    incoming_dir = os.path.join(dest, BACKUP_DIRNAME, "incoming", run_id)
    quarantine_dir = os.path.join(dest, BACKUP_DIRNAME, "quarantine", run_id)
    os.makedirs(incoming_dir, exist_ok=True)
    device_dir = f"{sanitize_component(model)}-{fp}"
    transferred = failed = skipped = 0
    try:
        files, warnings = inventory(cli, device_id, storage, roots, max_depth, storage_used, helper)
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
            except (OSError, RuntimeError, ValueError) as exc:
                # Local filesystem / collision / hashing / path-containment error for
                # THIS file: record and keep going rather than aborting with a traceback.
                manifest.mark_status(fp, storage, f, "failed",
                                     f"local error: {type(exc).__name__}: {exc}", run_id)
                failed += 1
                log.error("local error backing up %s: %s", f.remote_path, exc)
                continue
            if result == "transferred":
                transferred += 1
            elif result == "skipped":
                skipped += 1
            else:
                failed += 1

        # Source-deletion pass (only when explicitly armed). Runs AFTER transfers
        # and BEFORE finish_run so it covers both the rows already completed on a
        # prior run AND files transferred earlier in THIS run: upsert_completed
        # commits per file, and reconcile guarantees every still-'completed' row
        # has a present, correct-size local copy. Each file is independently
        # re-verified inside delete_source_for_row before its one `rm --`.
        deleted = delete_failed = already_absent = 0
        if delete_after_verify and adb is not None:
            pending_del = manifest.rows_pending_deletion(fp, storage)
            log.info("delete-after-verify: %d candidate source file(s)", len(pending_del))
            for row in pending_del:
                try:
                    outcome = delete_source_for_row(adb, manifest, dest, row,
                                                    android_root, run_id)
                except AdbError as exc:
                    # A transport-level adb failure (e.g. cable pulled): keep the
                    # file, mark it for retry, and stop the pass — the device is
                    # likely gone, so hammering it further is pointless and unsafe.
                    manifest.mark_deletion(row["id"], "delete_failed", f"adb error: {exc}")
                    manifest.record_deletion_event(row["id"], fp, storage,
                                                   row["remote_path"], "delete", "failed",
                                                   f"adb error: {exc}", run_id)
                    delete_failed += 1
                    log.error("adb error during deletion pass; aborting remaining "
                              "deletions: %s", exc)
                    break
                if outcome == "deleted":
                    deleted += 1
                elif outcome == "absent":
                    already_absent += 1
                elif outcome == "failed":
                    delete_failed += 1
                # 'skip' counts as neither success nor failure.

        run_failed = failed > 0 or delete_failed > 0
        status = "ok" if not run_failed else "partial"
        notes = (f"transferred={transferred} skipped={skipped} failed={failed} "
                 f"deleted={deleted} delete_failed={delete_failed} "
                 f"already_absent={already_absent}")
        manifest.finish_run(run_id, status, notes)
        print(f"Done. transferred={transferred} skipped={skipped} failed={failed} "
              f"deleted={deleted} delete_failed={delete_failed} "
              f"already_absent={already_absent}")
        if warnings:
            for root, msg in warnings:
                print(f"  ! source {root} skipped: {msg}")
        return EXIT_OK if not run_failed else EXIT_TRANSFER
    except Exception as exc:
        manifest.finish_run(run_id, "error", str(exc))
        raise
    finally:
        # Always remove this run's incoming staging area (any leftover .partial
        # files or per-file subdirs), even on early return or exception.
        _cleanup_dir(incoming_dir)


def transfer_one(cli: CLI, manifest: Manifest, dest: str, device_id: str, device_dir: str,
                 fp: str, storage: str, f: MediaFile, incoming_dir: str, quarantine_dir: str,
                 run_id: str, pull_timeout: int) -> str:
    """Pull one file and place it atomically. Raises only DeviceError; all local
    filesystem/collision errors are converted to a recorded failed/quarantined
    status (returns "failed"), and the per-file incoming staging is always cleaned.
    """
    identity = f"{fp}|{storage}|{f.remote_path}|{f.size}|{f.modified}"
    id_hash = hashlib.sha256(identity.encode()).hexdigest()[:8]

    incoming_sub = os.path.join(incoming_dir, uuid.uuid4().hex)
    os.makedirs(incoming_sub, exist_ok=True)
    timeout = pull_timeout if pull_timeout > 0 else max(600, int(f.size / (150 * 1024)) + 600)
    partial: str | None = None
    try:
        # Computed inside the guarded block: build_final_path raises ValueError if
        # the sanitized/realpath'd destination would escape DEST (e.g. via a symlink
        # ancestor). That must fail just this file, not abort the whole run.
        final_default = build_final_path(dest, device_dir, storage, f.remote_path)
        rc, out, _err = cli.run("pull", [device_id, storage, f.remote_path, incoming_sub], timeout)
        if rc != 0 or not pull_reported_success(out):
            manifest.mark_status(fp, storage, f, "failed",
                                 f"pull did not report success (rc={rc})", run_id)
            log.error("pull failed for %s", f.remote_path)
            return "failed"

        produced = discover_pulled_file(incoming_sub, os.path.basename(f.remote_path))
        if produced is None:
            manifest.mark_status(fp, storage, f, "failed", "pulled output not found", run_id)
            log.error("pulled output not discovered for %s", f.remote_path)
            return "failed"

        # Move to a unique .partial on the same volume before verifying.
        partial = os.path.join(incoming_dir, f"{uuid.uuid4().hex}.partial")
        os.replace(produced, partial)

        actual_size = os.path.getsize(partial)
        if actual_size != f.size:
            _quarantine(partial, quarantine_dir, f, id_hash)
            partial = None
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
            partial = None
            manifest.upsert_completed(fp, storage, f, sha, os.path.relpath(target, dest), run_id)
            log.info("already present (identical) %s -> %s", f.remote_path, os.path.relpath(target, dest))
            return "skipped"

        # Deterministic handling of sanitized file-vs-directory collisions: if an
        # ancestor directory we would need to create already exists as a FILE
        # (because two different remote names sanitized to the same local path),
        # do not crash — quarantine and fail just this file with a reproducible
        # message. (The reverse — target leaf colliding with a directory — is
        # handled by resolve_target picking a disambiguated sibling name.)
        conflict = ancestor_file_conflict(target, dest)
        if conflict is not None:
            _quarantine(partial, quarantine_dir, f, id_hash)
            partial = None
            rel = os.path.relpath(conflict, dest)
            manifest.mark_status(fp, storage, f, "quarantined",
                                 f"path collision: '{rel}' already exists as a file, cannot create "
                                 f"a directory there for {os.path.basename(target)}", run_id)
            log.error("path collision for %s: '%s' exists as a file", f.remote_path, rel)
            return "failed"

        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.replace(partial, target)  # atomic on same volume
        partial = None
        fsync_dir(os.path.dirname(target))
        manifest.upsert_completed(fp, storage, f, sha, os.path.relpath(target, dest), run_id)
        log.info("backed up %s -> %s", f.remote_path, os.path.relpath(target, dest))
        return "transferred"
    except DeviceError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        # Any local filesystem / collision / hashing / path-containment error:
        # never crash the run; preserve the pulled bytes for audit when we have them.
        if partial is not None and os.path.exists(partial):
            _quarantine(partial, quarantine_dir, f, id_hash)
            partial = None
        manifest.mark_status(fp, storage, f, "failed",
                             f"local error: {type(exc).__name__}: {exc}", run_id)
        log.error("local error backing up %s: %s", f.remote_path, exc)
        return "failed"
    finally:
        _cleanup_dir(incoming_sub)
        if partial is not None and os.path.exists(partial):
            try:
                os.remove(partial)
            except OSError:
                pass


def ancestor_file_conflict(target: str, dest: str) -> str | None:
    """Return the ancestor of `target` (at or above its parent, below `dest`) that
    already exists as a non-directory and would block creating the parent chain,
    or None. Bounded by `dest`; deterministic (pure filesystem inspection)."""
    dest = os.path.normpath(dest)
    chain = []
    cur = os.path.dirname(os.path.normpath(target))
    while True:
        chain.append(cur)
        parent = os.path.dirname(cur)
        if cur == dest or cur == parent:
            break
        cur = parent
    for path in reversed(chain):  # outermost ancestor first
        if os.path.lexists(path) and not os.path.isdir(path):
            return path
    return None


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
    p.add_argument("--allow-empty-inventory", action="store_true",
                   help="proceed even when no media is found while the device reports storage in "
                        "use (by default this is treated as a likely `swiftmtp-cli ls` failure and "
                        "refused). Use only for a device that genuinely has no photos/videos in the "
                        "source roots.")
    p.add_argument("--mtp-helper", default=None, metavar="PATH",
                   help="path to the native mtpinv enumeration helper (default: auto-discover "
                        "$SWIFTMTP_MTPINV, bin/mtpinv/mtpinv next to this script, or $PATH). "
                        "The helper works around the stock `swiftmtp-cli ls` returning empty "
                        "listings; build it with bin/mtpinv/build.sh.")
    p.add_argument("--delete-after-verify", action="store_true",
                   help="DELETE each source file FROM THE PHONE (via adb) after — and only "
                        "after — its local backup is byte-verified AND the on-device file is "
                        "re-verified byte-identical (size + SHA-256, non-symlink regular file). "
                        "Requires --run; NEVER deletes in dry-run/verify. Removes only regular "
                        "files, one at a time; any mismatch keeps the phone file.")
    p.add_argument("--adb", default=(shutil.which("adb") or DEFAULT_ADB),
                   help=f"path to the adb binary (default: adb on PATH, else {DEFAULT_ADB})")
    p.add_argument("--adb-serial", default=None,
                   help="explicit adb device serial; required when multiple authorized adb "
                        "devices are connected")
    p.add_argument("--android-root", default="/sdcard",
                   help="Android filesystem root that the SELECTED MTP storage root maps to "
                        "(default: /sdcard, i.e. internal shared storage). Must correspond to "
                        "the storage chosen via --storage; on a multi-storage device pointing "
                        "this at the wrong storage is guarded by the mandatory size+SHA-256 "
                        "match (a non-identical file is never deleted).")
    p.add_argument("--adb-timeout", type=int, default=60,
                   help="timeout (s) per adb command (default: 60)")
    p.add_argument("-v", "--verbose", action="store_true", help="verbose console output")
    return p


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.delete_after_verify and not args.run:
        # Fail closed: destruction is never allowed outside an explicit --run.
        parser.error("--delete-after-verify requires --run")
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
        storage, storage_used = resolve_storage(cli, device_id, args.storage)
        log.info("device fp=%s model=%s storage=%s", fp, model, storage)
        db_path = os.path.join(dest, BACKUP_DIRNAME, "manifest.sqlite3")
        # The empty-inventory guard uses reported storage usage as its trust signal;
        # --allow-empty-inventory disables it by withholding that signal.
        guard_used = None if args.allow_empty_inventory else storage_used
        # Prefer the native mtpinv helper for enumeration (the stock `ls` returns
        # empty listings on some devices). Fall back to `ls` only if unavailable.
        helper = resolve_mtp_helper(args.mtp_helper)
        if helper:
            log.info("inventory backend: native mtp helper (%s)", helper)
        else:
            log.warning("native mtp helper not found; falling back to `swiftmtp-cli ls` "
                        "(returns empty listings on some devices). Build bin/mtpinv/mtpinv "
                        "(see bin/mtpinv/README.md) or pass --mtp-helper PATH.")

        if mode == "run":
            ensure_destination(dest, mount)
            setup_file_logging(dest)
            lock_fd = acquire_lock(dest)
            manifest = Manifest(db_path)
            adb = None
            if args.delete_after_verify:
                # Arm deletion only after proving adb targets the SAME physical
                # device we just backed up (see _prepare_adb_for_delete).
                adb = _prepare_adb_for_delete(args.adb, args.adb_serial, device_id,
                                              args.adb_timeout)
            return do_run(manifest, cli, dest, device_id, model, fp, storage,
                          roots, args.max_depth, args.min_free_gib, args.pull_timeout,
                          guard_used, helper,
                          adb=adb, android_root=args.android_root,
                          delete_after_verify=args.delete_after_verify)

        # dry-run: read-only preview; creates no destination/manifest/logs/lock.
        completed = load_completed_map(db_path, fp, storage)
        return do_dry_run(cli, dest, mount, device_id, model, fp, storage,
                          roots, args.max_depth, args.min_free_gib, completed,
                          guard_used, helper)

    except PreflightError as exc:
        log.error("preflight: %s", exc)
        return EXIT_PREFLIGHT
    except LockError as exc:
        log.error("%s", exc)
        return EXIT_LOCK
    except (DeviceError, InventoryError, AdbError) as exc:
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
