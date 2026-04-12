#!/usr/bin/env python3
"""
shutdown.py — Post-task cleanup for the Floor workflow.

Runs all check scripts, increments the task counter, marks a matched status
item complete, and outputs structured results for Claude Code to act on.

Usage: python project_management/scripts/shutdown.py [--repo-root PATH]

Exit codes:
  0 — success
  2 — I/O or subprocess error
"""

import json
import argparse
import subprocess
import sys
from pathlib import Path

SESSION_FILE = ".floor_session.json"
TASK_COUNTER_SCRIPT = "project_management/scripts/task_counter.py"
CHECK_CDOCS_SCRIPT = "project_management/scripts/check_cdocs.py"
CHECK_MANIFEST_SCRIPT = "project_management/scripts/check_manifest.py"
CHECK_CDOC_COVERAGE_SCRIPT = "project_management/scripts/check_cdoc_coverage.py"


# ── I/O layer ─────────────────────────────────────────────────────────────────


def run_script(repo_root, script, args=None):
  """Run a Python script and return (stdout, stderr, returncode)."""
  cmd = [sys.executable, str(repo_root / script)] + (args or [])
  try:
    result = subprocess.run(
      cmd,
      capture_output=True,
      text=True,
      cwd=str(repo_root),
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode
  except OSError as exc:
    return "", str(exc), 2


def load_session(repo_root):
  """Load .floor_session.json. Returns {} if missing."""
  path = repo_root / SESSION_FILE
  if not path.exists():
    return {}
  try:
    return json.loads(path.read_text(encoding="utf-8"))
  except (json.JSONDecodeError, OSError):
    return {}


def cleanup_session(repo_root):
  """Remove .floor_session.json if it exists."""
  path = repo_root / SESSION_FILE
  if path.exists():
    path.unlink()


# ── Orchestration ─────────────────────────────────────────────────────────────


def run_shutdown(repo_root):
  """Run all post-task checks and output structured results.

  Returns exit code.
  """
  session = load_session(repo_root)
  results = []

  # 1. Check cdoc coverage
  stdout, stderr, rc = run_script(repo_root, CHECK_CDOC_COVERAGE_SCRIPT)
  results.append(("Cdoc Coverage", stdout, stderr, rc))

  # 2. Check manifest
  stdout, stderr, rc = run_script(repo_root, CHECK_MANIFEST_SCRIPT)
  results.append(("Manifest Audit", stdout, stderr, rc))

  # 3. Check cdocs staleness
  stdout, stderr, rc = run_script(repo_root, CHECK_CDOCS_SCRIPT)
  results.append(("Cdoc Staleness", stdout, stderr, rc))

  # 4. Increment task counter
  stdout, stderr, rc = run_script(repo_root, TASK_COUNTER_SCRIPT, ["increment"])
  results.append(("Task Counter", stdout, stderr, rc))

  # 5. Mark status item complete if session has a matched ID
  status_id = session.get("status_item_id")
  if status_id:
    results.append(("Status Item", f"Mark task {status_id} as complete", "", 0))

  # 6. Output structured markdown
  print("# Shutdown Results\n")

  for name, stdout, stderr, rc in results:
    print(f"## {name}\n")
    if stdout:
      print(f"```\n{stdout}\n```\n")
    if stderr:
      print(f"Errors:\n```\n{stderr}\n```\n")
    if not stdout and not stderr:
      print("No issues found.\n")

  print("## Actions Required\n")
  print("Based on the results above:")
  print("- Add any UNCOVERED files to the appropriate cdoc's sources list")
  print("- Add any MISSING files to manifest.md; remove any DEAD entries")
  print("- Read cdoc.md, then update affected context documents")
  print("- Make sure to update any STALE cdocs to reflect current source file state")
  print("- Remind the user to make a git commit")

  # 7. Cleanup
  cleanup_session(repo_root)

  return 0


def main():
  parser = argparse.ArgumentParser(
    description="Run post-task shutdown checks and output results."
  )
  parser.add_argument(
    "--repo-root",
    default=".",
    help="path to repo root (default: current directory)",
  )
  args = parser.parse_args()
  repo_root = Path(args.repo_root).resolve()
  sys.exit(run_shutdown(repo_root))


if __name__ == "__main__":
  main()
