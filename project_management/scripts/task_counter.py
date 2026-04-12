#!/usr/bin/env python3
"""
task_counter.py — Manage the Task Counter value.

Reads and writes the counter from project_management/task_counter.txt.
A missing file is treated as a counter value of 0.

Usage: python project_management/scripts/task_counter.py <operation> [--repo-root PATH]

Operations:
  read       — print the current counter value
  increment  — increment the counter by 1 and print the new value
  reset      — reset the counter to 0

Exit codes:
  0 — success
  1 — invalid operation
  2 — I/O error
"""

import argparse
import sys
from pathlib import Path

COUNTER_PATH = "project_management/task_counter.txt"

VALID_OPERATIONS = ("read", "increment", "reset")


# ── Logic layer (pure, no I/O) ────────────────────────────────────────────────


def apply_operation(current_value, operation):
  """Return the new counter value after applying the operation.

  Raises ValueError for unrecognized operations.
  """
  if operation == "read":
    return current_value
  if operation == "increment":
    return current_value + 1
  if operation == "reset":
    return 0
  raise ValueError(f"unknown operation: {operation!r}")


# ── I/O layer ─────────────────────────────────────────────────────────────────


def read_counter(counter_path):
  """Read the counter from disk. Returns 0 if the file does not exist."""
  if not counter_path.exists():
    return 0
  try:
    return int(counter_path.read_text(encoding="utf-8").strip())
  except (ValueError, OSError) as exc:
    print(f"error: could not read counter at {counter_path}: {exc}", file=sys.stderr)
    sys.exit(2)


def write_counter(counter_path, value):
  """Write the counter value to disk, creating parent directories if needed."""
  try:
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    counter_path.write_text(str(value) + "\n", encoding="utf-8")
  except OSError as exc:
    print(f"error: could not write counter at {counter_path}: {exc}", file=sys.stderr)
    sys.exit(2)


# ── Orchestration ─────────────────────────────────────────────────────────────


def run(repo_root, operation):
  """Execute the operation and print the resulting counter value.

  Returns exit code 0 on success, 1 on invalid operation.
  """
  if operation not in VALID_OPERATIONS:
    print(
      f"error: invalid operation {operation!r}. Choose from: {', '.join(VALID_OPERATIONS)}",
      file=sys.stderr,
    )
    return 1

  counter_path = repo_root / COUNTER_PATH
  current = read_counter(counter_path)
  new_value = apply_operation(current, operation)

  if operation != "read":
    write_counter(counter_path, new_value)

  print(new_value)
  return 0


def main():
  parser = argparse.ArgumentParser(
    description="Manage the Task Counter value."
  )
  parser.add_argument(
    "operation",
    choices=VALID_OPERATIONS,
    help="operation to perform: read, increment, or reset",
  )
  parser.add_argument(
    "--repo-root",
    default=".",
    help="path to repo root (default: current directory)",
  )
  args = parser.parse_args()
  repo_root = Path(args.repo_root).resolve()
  sys.exit(run(repo_root, args.operation))


if __name__ == "__main__":
  main()
