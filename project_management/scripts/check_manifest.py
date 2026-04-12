#!/usr/bin/env python3
"""
check_manifest.py — Audits project_management/manifest.md for file coverage.

  MISSING: file exists on disk but has no manifest entry
  DEAD:    manifest entry whose file path does not exist on disk

Usage: python check_manifest.py [--repo-root PATH] [--exclude PATH ...]

Exit codes:
  0 — no missing, no dead
  1 — any missing or dead entries found
  2 — error (unreadable manifest, etc.)
"""

import argparse
import re
import sys
from pathlib import Path

MANIFEST_PATH = "project_management/manifest.md"

MANIFEST_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


# ── Logic layer (pure, no I/O) ────────────────────────────────────────────────


def parse_manifest_paths(manifest_text):
  """Extract file paths from manifest table rows.

  Parses [link text](href) — uses the text inside [...], not the href.
  Skips header and separator rows.
  Returns a set of path strings.
  """
  paths = set()
  for line in manifest_text.splitlines():
    stripped = line.strip()
    if not stripped.startswith("|"):
      continue
    if re.match(r"^\|[-| ]+\|$", stripped):
      continue
    match = MANIFEST_LINK_RE.search(stripped)
    if not match:
      continue
    link_text = match.group(1)
    if link_text.lower() == "file":
      continue
    paths.add(link_text)
  return paths


def is_excluded(rel_path, excludes):
  """Return True if rel_path matches or is under any excluded path."""
  for excl in excludes:
    excl = excl.rstrip("/")
    if rel_path == excl or rel_path.startswith(excl + "/"):
      return True
  return False


# ── I/O layer ─────────────────────────────────────────────────────────────────


def walk_repo_files(repo_root, manifest_rel, excludes):
  """Yield relative path strings for all files under repo_root.

  Excludes:
    - .git/ and __pycache__/ subtrees
    - the manifest file itself
    - any paths in excludes
  """
  for path in sorted(repo_root.rglob("*")):
    if not path.is_file():
      continue
    rel = str(path.relative_to(repo_root))
    if any(part in {".git", "__pycache__"} for part in path.relative_to(repo_root).parts):
      continue
    if rel == manifest_rel:
      continue
    if is_excluded(rel, excludes):
      continue
    yield rel


# ── Orchestration ─────────────────────────────────────────────────────────────


def run_check(repo_root, excludes):
  """Compare manifest entries against disk, print results.

  Returns exit code: 0 if all clear, 1 if any issues, 2 on error.
  """
  manifest_path = repo_root / MANIFEST_PATH

  if not manifest_path.exists():
    print(f"error: manifest not found at {manifest_path}", file=sys.stderr)
    return 2

  try:
    manifest_text = manifest_path.read_text(encoding="utf-8")
  except OSError as exc:
    print(f"error: could not read manifest: {exc}", file=sys.stderr)
    return 2

  manifest_paths = parse_manifest_paths(manifest_text)
  disk_paths = set(walk_repo_files(repo_root, MANIFEST_PATH, excludes))

  missing = sorted(disk_paths - manifest_paths)
  dead = sorted(p for p in manifest_paths if not (repo_root / p).exists())

  for path in missing:
    print(f"MISSING: {path}")
  for path in dead:
    print(f"DEAD: {path}")

  return 1 if (missing or dead) else 0


def main():
  parser = argparse.ArgumentParser(
    description="Audit manifest.md for missing and dead file entries."
  )
  parser.add_argument(
    "--repo-root",
    default=".",
    help="path to repo root (default: current directory)",
  )
  parser.add_argument(
    "--exclude",
    metavar="PATH",
    action="append",
    default=[],
    help="path to exclude from the file walk (may be specified multiple times)",
  )
  args = parser.parse_args()
  repo_root = Path(args.repo_root).resolve()
  sys.exit(run_check(repo_root, args.exclude))


if __name__ == "__main__":
  main()
