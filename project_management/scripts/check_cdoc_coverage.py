#!/usr/bin/env python3
"""
check_cdoc_coverage.py — Reports repo files not declared as a source in any cdoc.

Scans all cdocs in project_management/cdocs/ for their sources frontmatter fields
and reports any repo files not covered by at least one cdoc.

Usage: python check_cdoc_coverage.py [--repo-root PATH] [--exclude PATH ...]

Exit codes:
  0 — all files covered
  1 — any uncovered files found
  2 — error (unreadable cdoc, etc.)
"""

import argparse
import sys
from pathlib import Path

from hash_util import parse_frontmatter

CDOCS_DIR = "project_management/cdocs"

DEFAULT_EXCLUDES = [
  "project_management",
  "scripts",
  "CLAUDE.md",
  ".gitignore",
]


# ── Logic layer (pure, no I/O) ────────────────────────────────────────────────


def collect_covered_sources(cdoc_entries):
  """Return the union of all sources declared across cdocs.

  cdoc_entries — iterable of (cdoc_key, text) pairs.
  Returns a set of path strings.
  """
  covered = set()
  for _key, text in cdoc_entries:
    frontmatter = parse_frontmatter(text)
    for src in frontmatter.get("sources", []):
      covered.add(src)
  return covered


def is_excluded(rel_path, excludes):
  """Return True if rel_path matches or is under any excluded path."""
  for excl in excludes:
    excl = excl.rstrip("/")
    if rel_path == excl or rel_path.startswith(excl + "/"):
      return True
  return False


# ── I/O layer ─────────────────────────────────────────────────────────────────


def walk_repo_files(repo_root, excludes):
  """Yield relative path strings for all files under repo_root.

  Excludes:
    - .git/ and __pycache__/ subtrees
    - any paths in excludes
  """
  for path in sorted(repo_root.rglob("*")):
    if not path.is_file():
      continue
    rel = str(path.relative_to(repo_root))
    if any(part in {".git", "__pycache__"} for part in path.relative_to(repo_root).parts):
      continue
    if is_excluded(rel, excludes):
      continue
    yield rel


def read_cdoc_entries(cdocs_dir):
  """Yield (cdoc_key, text) pairs for each .md file in cdocs_dir.

  cdoc_key is the path relative to the parent of cdocs_dir (i.e. repo_root).
  Raises OSError if a cdoc cannot be read.
  """
  if not cdocs_dir.is_dir():
    return
  repo_root = cdocs_dir.parent.parent
  for path in sorted(cdocs_dir.glob("*.md")):
    cdoc_key = str(path.relative_to(repo_root))
    yield cdoc_key, path.read_text(encoding="utf-8")


# ── Orchestration ─────────────────────────────────────────────────────────────


def normalize_excludes(excludes, repo_root):
  """Return excludes as paths relative to repo_root.

  Accepts paths relative to CWD (e.g. floor/setup.md when repo_root is floor/)
  or already relative to repo_root (e.g. setup.md). Absolute paths are also handled.
  Paths that cannot be made relative to repo_root are kept as-is.
  """
  normalized = []
  for excl in excludes:
    try:
      abs_excl = (Path.cwd() / excl).resolve()
      normalized.append(str(abs_excl.relative_to(repo_root)))
    except ValueError:
      normalized.append(excl)
  return normalized


def run_check(repo_root, excludes):
  """Scan cdocs for declared sources, compare against disk, print results.

  Returns exit code: 0 if all covered, 1 if any uncovered, 2 on error.
  """
  cdocs_dir = repo_root / CDOCS_DIR

  try:
    cdoc_entries = list(read_cdoc_entries(cdocs_dir))
  except OSError as exc:
    print(f"error: could not read cdocs: {exc}", file=sys.stderr)
    return 2

  covered = collect_covered_sources(cdoc_entries)
  all_excludes = DEFAULT_EXCLUDES + normalize_excludes(excludes, repo_root)
  disk_files = list(walk_repo_files(repo_root, all_excludes))

  uncovered = sorted(f for f in disk_files if f not in covered)
  for path in uncovered:
    print(f"UNCOVERED: {path}")

  return 1 if uncovered else 0


def main():
  parser = argparse.ArgumentParser(
    description="Report repo files not declared as a source in any cdoc."
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
