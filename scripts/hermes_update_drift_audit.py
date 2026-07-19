#!/usr/bin/env python3
"""Persist Hermes local drift and summarize update risk.

This script is intentionally audit-only: it never runs `hermes update`, resets,
stashes, commits, or edits the Hermes checkout. It fetches upstream, snapshots
local changes outside the repo, and prints a concise morning-ready report.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(os.environ.get("HERMES_REPO", "/Users/sai/.hermes/hermes-agent")).expanduser()
OUT_ROOT = Path(os.environ.get("HERMES_DRIFT_OUT", "/Users/sai/sai/outputs/hermes-update-drift")).expanduser()
RELEASE_REF = os.environ.get("HERMES_RELEASE_REF", "origin/main")
UPSTREAM_REF = os.environ.get("HERMES_UPSTREAM_REF", "upstream/main")
SENSITIVE_PATHS = [
    "gateway/run.py",
    "gateway/session.py",
    "gateway/platforms/base.py",
    "gateway/platforms/bluebubbles.py",
    "tests/gateway/test_bluebubbles.py",
    "tests/gateway/test_session.py",
    "tests/gateway/test_run_progress_topics.py",
    "cron",
    "hermes_cli",
]


def run(args: list[str], *, check: bool = False, max_chars: int | None = None) -> str:
    proc = subprocess.run(
        args,
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    out = proc.stdout.strip()
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(args)}\n{out}")
    if max_chars is not None and len(out) > max_chars:
        return out[:max_chars] + f"\n… truncated {len(out) - max_chars} chars"
    return out


def git(*args: str, check: bool = False, max_chars: int | None = None) -> str:
    return run(["git", *args], check=check, max_chars=max_chars)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + ("" if text.endswith("\n") else "\n"))


def split_files(text: str) -> set[str]:
    files: set[str] = set()
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            files.add(parts[-1])
    return files


def main() -> int:
    if not (REPO / ".git").exists():
        print(f"Hermes update drift audit failed: repo not found at {REPO}")
        return 2

    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    today = now.astimezone().strftime("%Y-%m-%d")
    out_dir = OUT_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    fetch = git("fetch", "--all", "--prune")
    status = git("status", "--short")
    branch = git("branch", "--show-current") or "(detached)"
    head = git("rev-parse", "HEAD")
    upstream_ref = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") or "(none)"
    release_ahead_behind = git("rev-list", "--left-right", "--count", f"HEAD...{RELEASE_REF}")
    release_ahead, release_behind = (release_ahead_behind.split() + ["?", "?"])[:2]
    upstream_exists = bool(git("rev-parse", "--verify", UPSTREAM_REF))
    effective_upstream_ref = UPSTREAM_REF if upstream_exists else RELEASE_REF
    fork_upstream_ahead_behind = git(
        "rev-list", "--left-right", "--count", f"{RELEASE_REF}...{effective_upstream_ref}"
    )
    downstream_only, upstream_pending = (
        fork_upstream_ahead_behind.split() + ["?", "?"]
    )[:2]
    upstream_merge_base = git("merge-base", RELEASE_REF, effective_upstream_ref)
    local_name_status = git("diff", "--name-status")
    local_cached_name_status = git("diff", "--cached", "--name-status")
    upstream_range = f"{upstream_merge_base}..{effective_upstream_ref}"
    upstream_name_status = git("diff", "--name-status", upstream_range)
    sensitive_upstream = git(
        "diff", "--name-status", upstream_range, "--", *SENSITIVE_PATHS
    )
    sensitive_local = git("diff", "--name-status", "--", *SENSITIVE_PATHS)
    local_patch = git("diff", "--binary", max_chars=None)
    cached_patch = git("diff", "--cached", "--binary", max_chars=None)

    write(out_dir / "fetch.txt", fetch)
    write(out_dir / "git-status.txt", status or "clean")
    write(out_dir / "branch.txt", branch)
    write(out_dir / "head.txt", head)
    write(out_dir / "upstream-ref.txt", upstream_ref)
    write(out_dir / "ahead-behind-origin-main.txt", release_ahead_behind)
    write(out_dir / "release-ref.txt", RELEASE_REF)
    write(out_dir / "upstream-source-ref.txt", effective_upstream_ref)
    write(out_dir / "fork-upstream-ahead-behind.txt", fork_upstream_ahead_behind)
    write(out_dir / "upstream-merge-base.txt", upstream_merge_base)
    write(out_dir / "local-name-status.txt", local_name_status or "clean")
    write(out_dir / "local-cached-name-status.txt", local_cached_name_status or "clean")
    write(out_dir / "upstream-name-status.txt", upstream_name_status or "none")
    write(out_dir / "sensitive-upstream-name-status.txt", sensitive_upstream or "none")
    write(out_dir / "sensitive-local-name-status.txt", sensitive_local or "none")
    write(out_dir / "local-uncommitted.patch", local_patch or "")
    write(out_dir / "local-cached.patch", cached_patch or "")

    untracked = []
    for line in status.splitlines():
        if line.startswith("?? "):
            rel = line[3:].strip()
            src = REPO / rel
            if src.is_file():
                dst = out_dir / "untracked" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                untracked.append(rel)
    write(out_dir / "untracked-files.txt", "\n".join(untracked) or "none")

    sha_lines = []
    for patch in ["local-uncommitted.patch", "local-cached.patch"]:
        p = out_dir / patch
        if p.exists() and p.stat().st_size:
            sha = subprocess.check_output(["shasum", "-a", "256", str(p)], text=True).strip()
            sha_lines.append(sha)
    write(out_dir / "patch.sha256", "\n".join(sha_lines) or "none")

    latest = OUT_ROOT / "latest"
    if latest.exists() or latest.is_symlink():
        latest.unlink()
    latest.symlink_to(out_dir, target_is_directory=True)

    local_files = split_files(local_name_status) | split_files(local_cached_name_status) | set(untracked)
    upstream_files = split_files(upstream_name_status)
    sensitive_upstream_files = split_files(sensitive_upstream)
    overlap = sorted(local_files & upstream_files)
    sensitive_overlap = sorted(local_files & sensitive_upstream_files)

    risk = "low"
    if status or release_ahead != "0" or release_behind != "0" or upstream_pending != "0" or sensitive_upstream_files:
        risk = "medium"
    if overlap or sensitive_overlap:
        risk = "high"

    summary = {
        "timestamp": stamp,
        "repo": str(REPO),
        "artifact_dir": str(out_dir),
        "branch": branch,
        "head": head,
        "tracking_ref": upstream_ref,
        "release_ref": RELEASE_REF,
        "ahead_release": release_ahead,
        "behind_release": release_behind,
        "upstream_ref": effective_upstream_ref,
        "downstream_only_commits": downstream_only,
        "upstream_pending_commits": upstream_pending,
        "working_tree_clean": not bool(status),
        "local_files": sorted(local_files),
        "upstream_changed_file_count": len(upstream_files),
        "sensitive_upstream_files": sorted(sensitive_upstream_files),
        "overlap_files": overlap,
        "sensitive_overlap_files": sensitive_overlap,
        "risk": risk,
    }
    write(out_dir / "summary.json", json.dumps(summary, indent=2, sort_keys=True))

    bullets: list[str] = []
    bullets.append(f"Hermes drift audit — {today}")
    bullets.append(f"Repo: {REPO}")
    bullets.append(f"Branch/head: {branch} @ {head[:10]}")
    bullets.append(
        f"Live vs tested release ({RELEASE_REF}): {release_ahead} ahead, {release_behind} behind"
    )
    bullets.append(
        f"Tested fork vs Nous ({effective_upstream_ref}): "
        f"{downstream_only} downstream-only, {upstream_pending} upstream-pending"
    )
    bullets.append(f"Working tree: {'clean' if not status else 'local changes persisted'}")
    if local_files:
        bullets.append("Local persisted files: " + ", ".join(sorted(local_files)[:8]) + ("…" if len(local_files) > 8 else ""))
    if sensitive_upstream_files:
        bullets.append("Upstream touched sensitive areas: " + ", ".join(sorted(sensitive_upstream_files)[:8]) + ("…" if len(sensitive_upstream_files) > 8 else ""))
    if overlap:
        bullets.append("Potential conflict overlap: " + ", ".join(overlap[:8]) + ("…" if len(overlap) > 8 else ""))
    bullets.append(f"Risk: {risk}")
    bullets.append(f"Persisted backup: {out_dir}")
    bullets.append(
        "Plan: advance the tested fork only through the BlueBubbles contract workflow; "
        "if integration is blocked, keep the live gateway on the current release and port forward in a candidate worktree."
    )

    report = "\n".join(bullets)
    write(out_dir / "report.txt", report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
