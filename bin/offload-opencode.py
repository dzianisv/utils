#!/usr/bin/env python3
"""Archive cold OpenCode sessions from a SQLite database.

The archive is a SQLite backup including recent sessions, with credential tables
removed. It is needed because OpenCode's JSON export omits database tables.
Only complete session families inactive before the cutoff are removed locally.
"""
import argparse
import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
import uuid


def connect(path, readonly=False):
    if readonly:
        return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    return sqlite3.connect(str(path), timeout=5)


def schema(conn):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = {"session", "project", "message", "part", "event", "event_sequence"}
    if not required.issubset(tables):
        raise RuntimeError("unrecognized OpenCode schema; refusing to offload")
    related = []
    for name in sorted(tables):
        if not name.replace("_", "").isalnum():
            raise RuntimeError("unrecognized table name")
        columns = {r[1] for r in conn.execute(f'PRAGMA table_info("{name}")')}
        if "session_id" in columns:
            related.append(name)
        fks = list(conn.execute(f'PRAGMA foreign_key_list("{name}")'))
        if "session_id" in columns and not any(
            fk[2] in {"session", "message"} and fk[6].upper() == "CASCADE" for fk in fks
        ):
            raise RuntimeError(f"unsupported session cascade: {name}")
        for fk in fks:
            if fk[2] in {"session", "message", "part", "event_sequence"} and name not in related and name != "event":
                raise RuntimeError(f"unsupported session dependency: {name}")
            if name == "event" and fk[2] == "event_sequence" and fk[6].upper() != "CASCADE":
                raise RuntimeError("unsupported event cascade")
    return related


def candidates(conn, cutoff, related):
    rows = conn.execute("SELECT id, parent_id, time_updated FROM session").fetchall()
    parent = {row[0]: row[1] for row in rows}
    children = {sid: [] for sid in parent}
    for sid, pid, _ in rows:
        if pid in children:
            children[pid].append(sid)
    stale = {sid: updated < cutoff for sid, _, updated in rows}
    # Some writes can update messages without updating the session row.
    for table in related:
        columns = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
        timestamp = "time_updated" if "time_updated" in columns else (
            "time_created" if "time_created" in columns else None)
        if timestamp:
            for (sid,) in conn.execute(f'SELECT DISTINCT session_id FROM "{table}" WHERE "{timestamp}" >= ?', (cutoff,)):
                if sid in stale:
                    stale[sid] = False
    selected = []
    for root, pid, _ in rows:
        if pid is not None:
            continue
        stack, family, seen = [root], [], set()
        while stack:
            sid = stack.pop()
            if sid in seen:
                raise RuntimeError("cycle in session family")
            seen.add(sid)
            family.append(sid)
            stack.extend(children[sid])
        if all(stale[sid] for sid in family):
            selected.extend(family)
    return selected


def digest_session(conn, sid, related):
    h = hashlib.sha256()
    queries = [("session", "id"), ("event_sequence", "aggregate_id"), ("event", "aggregate_id")]
    queries += [(table, "session_id") for table in related]
    for table, key in queries:
        rows = conn.execute(f'SELECT * FROM "{table}" WHERE "{key}" = ? ORDER BY rowid', (sid,))
        h.update(table.encode() + b"\0")
        for row in rows:
            # SQLite values are JSON scalars in the recognized OpenCode schema.
            h.update(json.dumps([encode_value(v) for v in row], ensure_ascii=True, separators=(",", ":")).encode() + b"\n")
    return h.digest()


def encode_value(value):
    return {"$blob": base64.b64encode(value).decode("ascii")} if isinstance(value, bytes) else value


def decode_value(value):
    if isinstance(value, dict) and set(value) == {"$blob"}:
        return base64.b64decode(value["$blob"], validate=True)
    if value is None or isinstance(value, (str, int, float)):
        return value
    raise ValueError("invalid archived SQLite value")


def hash_file(fileobj):
    digest = hashlib.sha256()
    for chunk in iter(lambda: fileobj.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest


def archive_session(conn, sid, related, folder):
    if not re.fullmatch(r"ses_[A-Za-z0-9_-]+", sid):
        raise RuntimeError(f"unsafe session id: {sid}")
    project = conn.execute("SELECT project_id FROM session WHERE id=?", (sid,)).fetchone()
    if not project:
        raise RuntimeError(f"session missing from backup: {sid}")
    tables = [("project", "id", project[0]), ("session", "id", sid),
              ("event_sequence", "aggregate_id", sid), ("event", "aggregate_id", sid)]
    tables += [(table, "session_id", sid) for table in related]
    path = folder / (sid + ".jsonl")
    h = hashlib.sha256()
    with path.open("xb") as f:
        def write(record):
            data = (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
            f.write(data)
            h.update(data)
        write({"type": "opencode-session-archive", "version": 1, "session_id": sid})
        for table, key, value in tables:
            columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
            for row in conn.execute(f'SELECT * FROM "{table}" WHERE "{key}" = ? ORDER BY rowid', (value,)):
                write({"table": table, "columns": columns, "values": [encode_value(v) for v in row]})
        f.flush()
        os.fsync(f.fileno())
    with path.open("rb") as f:
        if hash_file(f).digest() != h.digest():
            raise RuntimeError(f"JSONL verification failed: {path}")
    return h.hexdigest()


def restore_jsonl(db, path):
    if not db.is_file() or not path.is_file():
        raise RuntimeError("database or JSONL archive does not exist")
    manifest_path = path.parent.parent / (path.parent.name.removesuffix("-jsonl") + ".json")
    with manifest_path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    expected = manifest.get("jsonl_sha256", {}).get(path.stem)
    if not expected or path.name != path.stem + ".jsonl":
        raise RuntimeError("JSONL archive is not listed in its manifest")
    with closing(connect(db)) as live, path.open("rb") as source:
        related = schema(live)
        allowed = {"project", "session", "event_sequence", "event", *related}
        live.execute("PRAGMA foreign_keys=ON")
        live.execute("BEGIN IMMEDIATE")
        h = hashlib.sha256()
        header = source.readline()
        h.update(header)
        meta = json.loads(header)
        sid = meta.get("session_id")
        if meta != {"type": "opencode-session-archive", "version": 1, "session_id": path.stem}:
            raise RuntimeError("invalid JSONL archive header")
        if live.execute("SELECT 1 FROM session WHERE id=?", (sid,)).fetchone():
            raise RuntimeError(f"session already exists: {sid}")
        restored_session = False
        for line in source:
            h.update(line)
            record = json.loads(line)
            table = record.get("table")
            if table not in allowed:
                raise RuntimeError(f"unsupported archive table: {table}")
            columns = [row[1] for row in live.execute(f'PRAGMA table_info("{table}")')]
            values = [decode_value(value) for value in record.get("values", [])]
            if record.get("columns") != columns or len(values) != len(columns):
                raise RuntimeError(f"archive schema differs for {table}")
            data = dict(zip(columns, values))
            if table == "project":
                if live.execute("SELECT 1 FROM project WHERE id=?", (data["id"],)).fetchone():
                    continue
            elif table == "session":
                if data["id"] != sid or restored_session:
                    raise RuntimeError("invalid session row in archive")
                restored_session = True
            elif table in {"event", "event_sequence"}:
                if data["aggregate_id"] != sid:
                    raise RuntimeError("invalid event owner in archive")
            elif data["session_id"] != sid:
                raise RuntimeError("invalid session owner in archive")
            live.execute(f'INSERT INTO "{table}" VALUES (' + ",".join("?" for _ in values) + ")", values)
        if not restored_session or h.hexdigest() != expected:
            raise RuntimeError("JSONL checksum or session row verification failed; restore rolled back")
        live.commit()
    print(f"Restored session {sid} from {path}")


def run(db, archive, days, execute):
    if not db.is_file():
        raise RuntimeError(f"OpenCode database not found: {db}")
    cutoff = int((time.time() - days * 86400) * 1000)
    with closing(connect(db, readonly=True)) as source:
        related = schema(source)
        ids = candidates(source, cutoff, related)
    print(f"OpenCode: {len(ids)} sessions in fully inactive families older than {days} days", flush=True)
    if not execute or not ids:
        return
    archive.mkdir(parents=True, exist_ok=True)
    name = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:12]
    target = archive / (name + ".db")
    # Stage privately on the local disk. A native backup captures the WAL;
    # remove account credentials and VACUUM before writing to the SSD.
    with tempfile.TemporaryDirectory(prefix="opencode-offload-", dir=db.parent) as tmp:
        staged = Path(tmp) / "snapshot.db"
        with closing(connect(db, readonly=True)) as source, closing(connect(staged)) as dest:
            source.backup(dest)
            dest.execute("PRAGMA foreign_keys=ON")
            dest.execute("PRAGMA secure_delete=ON")
            available = {r[0] for r in dest.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("account_state", "account", "control_account", "credential"):
                if table in available:
                    dest.execute(f'DELETE FROM "{table}"')
            dest.commit()
            dest.execute("VACUUM")
            with closing(connect(target)) as archive_db:
                dest.backup(archive_db)
                if archive_db.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                    raise RuntimeError("could not finalize archive without WAL")
    with closing(connect(target, readonly=True)) as saved:
        if saved.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError(f"archive integrity check failed: {target}")
        if schema(saved) != related:
            raise RuntimeError("archive schema differs; no sessions removed")
        archived_ids = set(candidates(saved, cutoff, related))
        if not set(ids).issubset(archived_ids):
            raise RuntimeError("archive does not contain all candidates; no sessions removed")
    with target.open("rb") as f:
        os.fsync(f.fileno())
        digest = hash_file(f).hexdigest()
    jsonl_folder = archive / (name + "-jsonl")
    jsonl_folder.mkdir()
    with closing(connect(target, readonly=True)) as saved:
        jsonl_hashes = {sid: archive_session(saved, sid, related, jsonl_folder) for sid in ids}
    jsonl_fd = os.open(jsonl_folder, os.O_RDONLY)
    try:
        os.fsync(jsonl_fd)
    finally:
        os.close(jsonl_fd)
    manifest = archive / (name + ".json")
    with manifest.open("x", encoding="utf-8") as f:
        json.dump({"database": str(db), "backup": target.name, "sha256": digest,
                   "cutoff_ms": cutoff, "session_ids": ids, "jsonl_sha256": jsonl_hashes}, f)
        f.flush()
        os.fsync(f.fileno())
    directory_fd = os.open(archive, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    # Keep the local DB's write transaction open while rechecking both the
    # backup and current eligibility. No unverified row is ever removed.
    with closing(connect(db)) as live, closing(connect(target, readonly=True)) as saved:
        live.execute("PRAGMA foreign_keys=ON")
        live.execute("BEGIN IMMEDIATE")
        eligible = set(candidates(live, cutoff, related))
        if not set(ids).issubset(eligible):
            raise RuntimeError("sessions changed during backup; no sessions removed")
        for sid in ids:
            with (jsonl_folder / (sid + ".jsonl")).open("rb") as f:
                if hash_file(f).hexdigest() != jsonl_hashes[sid]:
                    raise RuntimeError(f"JSONL archive changed: {sid}; no sessions removed")
            if digest_session(live, sid, related) != digest_session(saved, sid, related):
                raise RuntimeError(f"session changed during backup: {sid}; no sessions removed")
        for sid in ids:
            live.execute("DELETE FROM event_sequence WHERE aggregate_id=?", (sid,))
            live.execute("DELETE FROM session WHERE id=?", (sid,))
        live.commit()
        print(f"Archived {len(ids)} sessions in {target}; SHA-256 {digest}", flush=True)
        print(f"Manifest: {manifest}", flush=True)
        # SQLite frees pages internally on delete; VACUUM returns them to macOS.
        live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        live.execute("VACUUM")
        checkpoint = live.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if checkpoint and checkpoint[0]:
        print("Database compacted; WAL checkpoint is busy and disk reclamation may be delayed.")
    else:
        print("Database compaction and WAL checkpoint completed.")
    print(f"Session JSONL files: {jsonl_folder}")
    print("Recovery: python3 offload-opencode.py --db <database> --restore <session.jsonl>")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--restore", type=Path, help="restore one session from its JSONL archive")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")
    if not args.restore and not args.archive:
        parser.error("--archive is required for offloading")
    if args.restore and (args.archive or args.execute):
        parser.error("--restore cannot be combined with --archive or --execute")
    try:
        if args.restore:
            restore_jsonl(args.db, args.restore)
        else:
            run(args.db, args.archive, args.days, args.execute)
    except (RuntimeError, OSError, sqlite3.Error, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
