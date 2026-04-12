#!/usr/bin/env python3
"""
check_cdocs.py — Detects stale context documents by comparing source file hashes.

A cdoc is stale when the aggregate hash of its declared source files differs from
the hash recorded when the cdoc was last updated.

Usage: python check_cdocs.py [--repo-root PATH]
Run from the repo root, or pass --repo-root to specify it.

Exit codes:
  0 — all cdocs fresh (or no cdocs with sources found)
  1 — one or more cdocs are stale
  2 — error (missing source file, unreadable store, etc.)
"""

import argparse
import json
import sys
from pathlib import Path

from hash_util import (
  compute_source_hash,
  find_changed_sources,
  parse_frontmatter,
  text_sha256,
)

HASH_STORE_PATH = "project_management/cdoc_hashes.json"
CDOCS_DIR = "project_management/cdocs"


# ── Logic layer (pure, no I/O) ────────────────────────────────────────────────


def assess_cdoc(cdoc_key, cdoc_text, sources, store, repo_root):
  """Pure assessment of a single cdoc. Raises FileNotFoundError for missing sources.

  Returns a result dict:
    status           — "fresh" | "stale" | "new"
    stale_magnitude  — float [0,1]: changed_files / total_files (stale only)
    changed_sources  — list of changed paths (stale only)
    content_changed  — bool: cdoc text differs from stored hash
    current_content_hash  — str
    current_source_hash   — str
    current_per_file      — dict
  """
  current_content_hash = text_sha256(cdoc_text)
  current_source_hash, current_per_file = compute_source_hash(sources, repo_root)

  stored = store.get(cdoc_key, {})
  stored_source_hash = stored.get("source_hash")
  stored_content_hash = stored.get("content_hash")
  stored_per_file = stored.get("source_file_hashes", {})

  content_changed = current_content_hash != stored_content_hash

  if stored_source_hash is None:
    status = "new"
    changed = []
    magnitude = 0.0
  elif current_source_hash != stored_source_hash:
    status = "stale"
    changed = find_changed_sources(current_per_file, stored_per_file)
    magnitude = len(changed) / max(len(sources), 1)
  else:
    status = "fresh"
    changed = []
    magnitude = 0.0

  return {
    "status": status,
    "stale_magnitude": magnitude,
    "changed_sources": changed,
    "content_changed": content_changed,
    "current_content_hash": current_content_hash,
    "current_source_hash": current_source_hash,
    "current_per_file": current_per_file,
  }


def build_store_entry(result):
  """Build the hash store entry from an assessment result."""
  return {
    "content_hash": result["current_content_hash"],
    "source_hash": result["current_source_hash"],
    "source_file_hashes": result["current_per_file"],
  }


# ── I/O layer ─────────────────────────────────────────────────────────────────


def load_hash_store(store_path):
  """Load the JSON hash store. Returns {} if the file doesn't exist."""
  if not store_path.exists():
    return {}
  try:
    return json.loads(store_path.read_text(encoding="utf-8"))
  except (json.JSONDecodeError, OSError) as exc:
    print(f"error: could not read hash store at {store_path}: {exc}", file=sys.stderr)
    sys.exit(2)


def save_hash_store(store_path, store):
  """Write the JSON hash store, creating parent directories if needed."""
  store_path.parent.mkdir(parents=True, exist_ok=True)
  store_path.write_text(
    json.dumps(store, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
  )


def collect_cdoc_paths(cdocs_dir):
  """Return sorted list of .md files in cdocs_dir."""
  if not cdocs_dir.is_dir():
    return []
  return sorted(cdocs_dir.glob("*.md"))


def read_cdoc(path):
  """Read a cdoc file as text."""
  return path.read_text(encoding="utf-8")


# ── Orchestration ─────────────────────────────────────────────────────────────


def run_check(repo_root):
  """Scan cdocs, compare hashes, print report, update store.

  Returns exit code: 0 if all fresh/new, 1 if any stale, 2 on error.
  """
  cdocs_dir = repo_root / CDOCS_DIR
  store_path = repo_root / HASH_STORE_PATH

  store = load_hash_store(store_path)
  cdoc_paths = collect_cdoc_paths(cdocs_dir)

  if not cdoc_paths:
    print(f"no cdocs found in {cdocs_dir}")
    return 0

  any_stale = False
  updated_store = dict(store)

  for cdoc_path in cdoc_paths:
    cdoc_key = str(cdoc_path.relative_to(repo_root))
    text = read_cdoc(cdoc_path)
    frontmatter = parse_frontmatter(text)

    if "sources" not in frontmatter:
      print(f"{cdoc_key}: skipped (no sources declared)")
      continue

    sources = frontmatter["sources"]

    try:
      result = assess_cdoc(cdoc_key, text, sources, store, repo_root)
    except FileNotFoundError as exc:
      print(f"error: {exc}", file=sys.stderr)
      return 2

    status = result["status"]

    if status == "stale":
      # If the cdoc content was updated, it's been refreshed despite source changes.
      # Report as fresh and update the store. Otherwise, it's truly stale.
      if result["content_changed"]:
        print(f"{cdoc_key}: fresh (sources changed but cdoc refreshed)")
        updated_store[cdoc_key] = build_store_entry(result)
      else:
        any_stale = True
        magnitude_pct = round(result["stale_magnitude"] * 100)
        print(f"{cdoc_key}: STALE ({magnitude_pct}% of sources changed)")
        for src in result["changed_sources"]:
          print(f"  changed: {src}")
    elif status == "new":
      print(f"{cdoc_key}: new (no prior hash recorded)")
      updated_store[cdoc_key] = build_store_entry(result)
    else:
      print(f"{cdoc_key}: fresh")
      updated_store[cdoc_key] = build_store_entry(result)

  save_hash_store(store_path, updated_store)
  return 1 if any_stale else 0


def main():
  parser = argparse.ArgumentParser(
    description="Check cdocs for staleness by comparing source file hashes."
  )
  parser.add_argument(
    "--repo-root",
    default=".",
    help="path to repo root (default: current directory)",
  )
  args = parser.parse_args()
  repo_root = Path(args.repo_root).resolve()
  sys.exit(run_check(repo_root))


if __name__ == "__main__":
  main()
