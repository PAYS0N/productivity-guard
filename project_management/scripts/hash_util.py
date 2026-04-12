"""
hash_util.py — Shared hashing utilities for Floor scripts.

Provides pure functions for SHA-256 hashing, YAML frontmatter parsing,
and aggregating source file hashes.
"""

import hashlib
from pathlib import Path

__all__ = [
  "FRONTMATTER_DELIM",
  "compute_source_hash",
  "file_sha256",
  "find_changed_sources",
  "parse_frontmatter",
  "text_sha256",
]

FRONTMATTER_DELIM = "---"


def parse_frontmatter(text):
  """Extract key/value pairs from YAML frontmatter. Returns {} if none found.

  Supports string values and simple list values under a 'sources' key:
    sources:
      - path/to/file.py
  """
  lines = text.splitlines()
  if not lines or lines[0].strip() != FRONTMATTER_DELIM:
    return {}

  end = None
  for i, line in enumerate(lines[1:], 1):
    if line.strip() == FRONTMATTER_DELIM:
      end = i
      break
  if end is None:
    return {}

  result = {}
  current_key = None
  list_items = []

  for line in lines[1:end]:
    stripped = line.strip()
    if not stripped:
      continue
    if stripped.startswith("- ") and current_key == "sources":
      list_items.append(stripped[2:].strip())
    elif ":" in stripped and not stripped.startswith("-"):
      if current_key == "sources" and list_items:
        result["sources"] = list_items
        list_items = []
      key, _, val = stripped.partition(":")
      current_key = key.strip()
      val = val.strip()
      if val:
        result[current_key] = val

  if current_key == "sources" and list_items:
    result["sources"] = list_items

  return result


def file_sha256(path):
  """Compute SHA-256 hex digest of a file. Raises FileNotFoundError if missing."""
  if not path.exists():
    raise FileNotFoundError(f"source file not found: {path}")
  return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256(text):
  """Compute SHA-256 hex digest of a UTF-8 string."""
  return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_source_hash(sources, repo_root):
  """Compute the aggregate source hash and per-file hashes.

  source_hash = SHA-256 of the concatenated per-file SHA-256 hashes,
                with files sorted by path for determinism.

  Returns (source_hash, {rel_path: file_hash}).
  Raises FileNotFoundError if any source file is missing.
  """
  per_file = {}
  for src in sorted(sources):
    per_file[src] = file_sha256(repo_root / src)

  combined = "".join(per_file[s] for s in sorted(per_file))
  aggregate = hashlib.sha256(combined.encode("utf-8")).hexdigest()
  return aggregate, per_file


def find_changed_sources(current_per_file, stored_per_file):
  """Return sorted list of source paths that were added, removed, or changed."""
  all_paths = set(current_per_file) | set(stored_per_file)
  return sorted(p for p in all_paths if current_per_file.get(p) != stored_per_file.get(p))
