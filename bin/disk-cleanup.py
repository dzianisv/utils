#!/usr/bin/env python3
"""Daily disk cleanup for this Mac.

Removes linked git worktrees that are stale AND already on a remote.
Never deletes a branch, a primary checkout, a dirty tree, an unpushed
commit, a locked worktree, or a directory a process still has open.

Also prunes a short list of regenerable caches. Does not touch
~/Downloads, Android AVDs, Colima disks, Hugging Face models, or .env files.

    disk-cleanup.py              # dry-run
    disk-cleanup.py --apply      # delete eligible worktrees and caches
    disk-cleanup.py --worktrees-only --root /tmp/fixture --stale-hours 0 --apply
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

SKIP_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "target",
    ".next",
    "Pods",
    "vendor",
    ".venv",
}
DENY_PREFIXES = (
    os.path.expanduser("~/.colima"),
    os.path.expanduser("~/.android"),
    os.path.expanduser("~/.local/share/opencode"),
    os.path.expanduser("~/.hermes"),
    os.path.expanduser("~/.paperclip"),
    os.path.expanduser("~/.paperclip-worktrees"),
    "/private/tmp",
    "/tmp",
)


@dataclass
class Verdict:
    path: str
    action: str  # remove | preserve
    reason: str
    repo: str = ""
    size_kb: int = 0


def run(cmd: list[str], timeout: int = 40, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}", flush=True)


def denied(path: str) -> bool:
    real = os.path.realpath(path)
    for prefix in DENY_PREFIXES:
        pre = os.path.realpath(prefix)
        if real == pre or real.startswith(pre + os.sep):
            return True
    parts = real.split(os.sep)
    return ".paperclip" in parts and "worktrees" in parts


def find_primary_repos(root: str, max_depth: int) -> list[str]:
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return []
    repos: list[str] = []
    for dirpath, dirnames, _filenames in os.walk(root):
        depth = dirpath[len(root):].count(os.sep)
        if depth >= max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".nm-broken")]
        git_dir = os.path.join(dirpath, ".git")
        if os.path.isdir(git_dir):
            repos.append(dirpath)
    return repos


def parse_worktrees(repo: str) -> list[dict]:
    try:
        res = run(["git", "-C", repo, "worktree", "list", "--porcelain"], timeout=30)
    except subprocess.TimeoutExpired:
        return []
    if res.returncode != 0:
        return []
    items = []
    block: dict = {}
    for line in res.stdout.splitlines():
        if not line.strip():
            if block.get("path"):
                items.append(block)
            block = {}
            continue
        if line.startswith("worktree "):
            block["path"] = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            block["branch"] = line.split(" ", 1)[1]
        elif line == "detached":
            block["detached"] = True
        elif line.startswith("locked"):
            block["locked"] = True
    if block.get("path"):
        items.append(block)
    return items


def porcelain_dirty(path: str) -> str | None:
    """Return None if clean, a reason string otherwise."""
    try:
        res = run(["git", "-C", path, "status", "--porcelain"], timeout=45)
    except subprocess.TimeoutExpired:
        return "status-timeout"
    if res.returncode != 0:
        return "status-failed"
    if res.stdout.strip():
        return "dirty"
    return None


def on_remote(path: str) -> str | None:
    """Return None if HEAD is on a remote-tracking branch, else a reason."""
    try:
        res = run(["git", "-C", path, "branch", "-r", "--contains", "HEAD"], timeout=40)
    except subprocess.TimeoutExpired:
        return "remote-check-timeout"
    if res.returncode != 0:
        return "remote-check-failed"
    refs = [
        ln.strip()
        for ln in res.stdout.splitlines()
        if ln.strip() and "HEAD ->" not in ln
    ]
    if not refs:
        return "not-on-remote"
    return None


def in_use(path: str) -> str | None:
    try:
        res = run(["lsof", "+D", path], timeout=20)
    except subprocess.TimeoutExpired:
        return "lsof-timeout"
    # macOS lsof exits 1 even when it printed matches. stdout is the signal.
    if res.stdout.strip():
        return "in-use"
    return None


def idle(path: str, stale_seconds: int) -> str | None:
    if stale_seconds <= 0:
        return None
    try:
        res = run(["git", "-C", path, "log", "-1", "--format=%ct"], timeout=20)
    except subprocess.TimeoutExpired:
        return "commit-time-timeout"
    if res.returncode != 0 or not res.stdout.strip().isdigit():
        return "no-commit"
    age = int(time.time()) - int(res.stdout.strip())
    if age < stale_seconds:
        return "recent-commit"
    cutoff = time.time() - stale_seconds
    # One recent file is enough. Don't walk node_modules forever.
    newest = 0.0
    checked = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d != "node_modules" and d != ".git"]
        for name in filenames:
            checked += 1
            if checked > 4000:
                return None
            try:
                mtime = os.stat(os.path.join(dirpath, name)).st_mtime
            except OSError:
                continue
            if mtime > newest:
                newest = mtime
            if newest > cutoff:
                return "recent-file"
    return None


def du_kb(path: str) -> int:
    try:
        res = run(["du", "-sk", path], timeout=60)
    except subprocess.TimeoutExpired:
        return 0
    if res.returncode != 0 or not res.stdout.strip():
        return 0
    return int(res.stdout.split()[0])


def judge(repo: str, wt: dict, stale_seconds: int) -> Verdict:
    path = wt["path"]
    if denied(path):
        return Verdict(path, "preserve", "denylisted", repo)
    if not os.path.isdir(path):
        return Verdict(path, "preserve", "missing", repo)
    if os.path.isdir(os.path.join(path, ".git")) or not os.path.isfile(os.path.join(path, ".git")):
        return Verdict(path, "preserve", "primary-checkout", repo)
    if wt.get("locked"):
        return Verdict(path, "preserve", "locked", repo)
    for check in (
        lambda: in_use(path),
        lambda: porcelain_dirty(path),
        lambda: on_remote(path),
        lambda: idle(path, stale_seconds),
    ):
        reason = check()
        if reason:
            return Verdict(path, "preserve", reason, repo)
    return Verdict(path, "remove", "clean+pushed+idle", repo, du_kb(path))


def remove_worktree(repo: str, path: str) -> bool:
    try:
        res = run(["git", "-C", repo, "worktree", "remove", "--force", path], timeout=180)
    except subprocess.TimeoutExpired:
        return False
    if res.returncode == 0 and not os.path.exists(path):
        return True
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
        run(["git", "-C", repo, "worktree", "prune"], timeout=30)
    return not os.path.exists(path)


def broken_nm_dirs(root: str, max_depth: int) -> list[str]:
    found = []
    root = os.path.abspath(root)
    for dirpath, dirnames, _filenames in os.walk(root):
        depth = dirpath[len(root):].count(os.sep)
        if depth >= max_depth:
            dirnames[:] = []
            continue
        keep = []
        for name in dirnames:
            full = os.path.join(dirpath, name)
            if name.startswith(".nm-broken"):
                found.append(full)
                continue
            if name in SKIP_DIRS:
                continue
            keep.append(name)
        dirnames[:] = keep
    return found


def cache_steps(apply: bool) -> int:
    freed = 0
    home = os.path.expanduser("~")

    def step(name: str, cmd: list[str] | None = None, paths: list[str] | None = None) -> None:
        nonlocal freed
        if paths:
            existing = [p for p in paths if os.path.exists(p)]
            kb = sum(du_kb(p) for p in existing)
            log(f"cache {name}: {kb} KB {'apply' if apply else 'dry-run'}")
            if apply:
                for p in existing:
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        try:
                            os.remove(p)
                        except OSError:
                            pass
                    if not os.path.exists(p):
                        freed += du_kb(p) if False else kb
            return
        if not cmd:
            return
        log(f"cache {name}: {' '.join(cmd)} {'apply' if apply else 'dry-run'}")
        if not apply:
            return
        try:
            res = run(cmd, timeout=180)
            if res.returncode != 0:
                err = (res.stderr or res.stdout or "").strip().splitlines()
                log(f"WARN {name} exit {res.returncode}: {err[-1] if err else ''}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            log(f"WARN {name}: {exc}")

    broken = glob.glob(os.path.join(home, ".cache", "puppeteer.broken.*"))
    step("puppeteer.broken", paths=broken)

    for tool, cmd in (
        ("npm", ["npm", "cache", "clean", "--force"]),
        ("pnpm", ["pnpm", "store", "prune"]),
        ("uv", ["uv", "cache", "prune"]),
        ("brew", ["brew", "cleanup", "--prune=14"]),
    ):
        if shutil.which(tool):
            step(tool, cmd)
        else:
            log(f"skip {tool}: not on PATH")
    if shutil.which("docker"):
        info = None
        try:
            info = run(["docker", "info"], timeout=8)
        except subprocess.TimeoutExpired:
            info = None
        if info and info.returncode == 0:
            step("docker-prune", ["docker", "system", "prune", "-f"])
        else:
            log("skip docker: not running")
    return freed


def free_kb() -> int:
    try:
        res = run(["df", "-k", "/System/Volumes/Data"], timeout=10)
    except subprocess.TimeoutExpired:
        return 0
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    if len(lines) < 2:
        return 0
    parts = lines[-1].split()
    return int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean stale pushed worktrees and regenerable caches.")
    parser.add_argument("--apply", action="store_true", help="delete eligible paths (default is dry-run)")
    parser.add_argument("--root", action="append", default=[], help="scan root (repeatable). default: ~/workspace")
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--stale-hours", type=int, default=24)
    parser.add_argument("--worktrees-only", action="store_true")
    args = parser.parse_args()

    roots = args.root or [os.path.expanduser("~/workspace")]
    stale_seconds = args.stale_hours * 3600
    before = free_kb()
    log(
        f"start apply={args.apply} stale_hours={args.stale_hours} "
        f"free={before // 1024}MiB roots={','.join(roots)}"
    )

    repos: list[str] = []
    for root in roots:
        repos.extend(find_primary_repos(root, args.max_depth))
    repos = sorted(set(repos))
    log(f"primary repos: {len(repos)}")

    verdicts: list[Verdict] = []
    seen: set[str] = set()
    for repo in repos:
        for wt in parse_worktrees(repo):
            path = os.path.realpath(wt["path"])
            if path in seen:
                continue
            seen.add(path)
            verdicts.append(judge(repo, wt, stale_seconds))

    remove = [v for v in verdicts if v.action == "remove"]
    preserve = [v for v in verdicts if v.action == "preserve" and v.reason != "primary-checkout"]
    log(f"worktrees remove={len(remove)} preserve={len(preserve)}")
    for v in remove + preserve:
        log(f"  {v.action:8} {v.reason:22} {v.size_kb:8}KB  {v.path}")

    removed = 0
    if args.apply:
        for v in remove:
            if remove_worktree(v.repo, v.path):
                removed += 1
                log(f"REMOVED {v.path}")
            else:
                log(f"FAILED {v.path}")
        for repo in repos:
            try:
                run(["git", "-C", repo, "worktree", "prune"], timeout=20)
            except subprocess.TimeoutExpired:
                log(f"WARN prune timeout {repo}")

    junk = []
    for root in roots:
        junk.extend(broken_nm_dirs(root, args.max_depth))
    junk_kb = sum(du_kb(p) for p in junk)
    log(f"nm-broken dirs={len(junk)} size={junk_kb}KB")
    if args.apply:
        for path in junk:
            shutil.rmtree(path, ignore_errors=True)
            log(f"REMOVED junk {path}" if not os.path.exists(path) else f"FAILED junk {path}")

    if not args.worktrees_only:
        cache_steps(args.apply)

    after = free_kb()
    log(
        f"done removed_worktrees={removed if args.apply else 0} "
        f"candidates={len(remove)} free={after // 1024}MiB "
        f"delta={(after - before) // 1024}MiB"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
