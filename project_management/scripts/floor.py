#!/usr/bin/env python3
"""
floor.py — CLI entry point for the Floor workflow.

Gathers context (cdoc staleness, status items, prompting instructions),
assembles a base prompt, and launches an interactive Claude CLI session
for prompt iteration.

Usage: python project_management/scripts/floor.py "<task description>"

Exit codes:
  0 — success (or arch-check gate triggered)
  1 — usage error
  2 — I/O or subprocess error
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROMPTING_PATH = "project_management/prompting.md"
STATUS_PATH = "project_management/status.md"
SESSION_FILE = ".floor_session.json"
PROMPT_OUTPUT_PATH = "project_management/prompts/implement-this.md"
TASK_COUNTER_SCRIPT = "project_management/scripts/task_counter.py"
CHECK_CDOCS_SCRIPT = "project_management/scripts/check_cdocs.py"
ARCH_CHECK_THRESHOLD = 10


# ── I/O layer ─────────────────────────────────────────────────────────────────


def read_file(path):
  """Read a file and return its text. Returns None if the file does not exist."""
  if not path.exists():
    return None
  return path.read_text(encoding="utf-8")


def run_script(repo_root, script, args=None):
  """Run a Python script and return its stdout. Returns None on failure."""
  cmd = [sys.executable, str(repo_root / script)] + (args or [])
  try:
    result = subprocess.run(
      cmd,
      capture_output=True,
      text=True,
      cwd=str(repo_root),
    )
    return result.stdout.strip()
  except OSError as exc:
    print(f"warning: could not run {script}: {exc}", file=sys.stderr)
    return None


def write_session_file(repo_root, task_description):
  """Write the initial .floor_session.json."""
  session = {
    "task": task_description,
    "status_item_id": None,
  }
  path = repo_root / SESSION_FILE
  path.write_text(
    json.dumps(session, indent=2) + "\n",
    encoding="utf-8",
  )


# ── Prompt assembly ──────────────────────────────────────────────────────────


def assemble_prompt(task_description, prompting_text, cdocs_output, status_text):
  """Build the base prompt string sent to the Claude CLI session."""
  sections = []

  sections.append("You are a prompting assistant. Your job is to iterate with "
    "the user on a task prompt until they are satisfied, then write the final "
    f"prompt to `{PROMPT_OUTPUT_PATH}`.")

  sections.append("If a status item matches this task, record its ID in "
    f"`{SESSION_FILE}` under the `status_item_id` key.")

  if prompting_text:
    sections.append(f"## Base prompting instructions\n\n{prompting_text}")

  if cdocs_output:
    sections.append(f"## Cdoc staleness report\n\n```\n{cdocs_output}\n```")

  if status_text:
    sections.append(f"## Current project status\n\n{status_text}")

  sections.append(f"## Task description\n\n{task_description}")

  return "\n\n".join(sections)


# ── Status resolution ────────────────────────────────────────────────────────

CLI_PATH_RE = re.compile(r"(/\S+/project_tasks_cli\.py)")
PROJECT_NAME_RE = re.compile(r"project_tasks_cli\.py\s+(list|add|complete|update|delete)\s+(\w+)")


def detect_status_cli(status_text):
  """Parse status.md for a project_tasks_cli.py path and project name.

  Returns (cli_path, project_name) or (None, None) if not found.
  """
  cli_match = CLI_PATH_RE.search(status_text)
  if not cli_match:
    return None, None
  cli_path = cli_match.group(1)
  project_match = PROJECT_NAME_RE.search(status_text)
  if not project_match:
    return None, None
  return cli_path, project_match.group(1)


def resolve_status(repo_root):
  """Read status.md. If it references project_tasks_cli.py, run the list
  command and return the output. Otherwise return the file contents as-is."""
  status_text = read_file(repo_root / STATUS_PATH)
  if status_text is None:
    return None
  cli_path, project = detect_status_cli(status_text)
  if cli_path is None:
    return status_text
  try:
    result = subprocess.run(
      [sys.executable, cli_path, "list", project],
      capture_output=True,
      text=True,
      timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
      return result.stdout.strip()
  except (OSError, subprocess.TimeoutExpired) as exc:
    print(f"warning: could not run status CLI: {exc}", file=sys.stderr)
  return status_text


# ── Orchestration ─────────────────────────────────────────────────────────────


def check_arch_gate(repo_root):
  """Check task counter. Returns True if arch check is required."""
  output = run_script(repo_root, TASK_COUNTER_SCRIPT, ["read"])
  if output is None:
    return False
  try:
    return int(output) >= ARCH_CHECK_THRESHOLD
  except ValueError:
    return False


def run_floor(repo_root, task_description):
  """Main orchestration: gather context, assemble prompt, launch session.

  Returns exit code.
  """
  if check_arch_gate(repo_root):
    print(
      f"Architecture check required (task counter >= {ARCH_CHECK_THRESHOLD}).\n"
      "Run the architecture health check prompt before proceeding with new tasks."
    )
    return 0

  cdocs_output = run_script(repo_root, CHECK_CDOCS_SCRIPT)

  prompting_text = read_file(repo_root / PROMPTING_PATH)
  if prompting_text is None:
    print(f"error: {PROMPTING_PATH} not found", file=sys.stderr)
    return 2

  status_text = resolve_status(repo_root)

  prompt = assemble_prompt(task_description, prompting_text, cdocs_output, status_text)

  write_session_file(repo_root, task_description)

  claude_path = "claude"
  try:
    os.execvp(claude_path, [claude_path, "--model", "claude-sonnet-4-6", prompt])
  except OSError as exc:
    print(f"error: could not launch claude CLI: {exc}", file=sys.stderr)
    return 2


def main():
  parser = argparse.ArgumentParser(
    description="Launch a Floor prompting session for a task."
  )
  parser.add_argument(
    "task",
    help="task description string",
  )
  parser.add_argument(
    "--repo-root",
    default=".",
    help="path to repo root (default: current directory)",
  )
  args = parser.parse_args()
  repo_root = Path(args.repo_root).resolve()
  sys.exit(run_floor(repo_root, args.task))


if __name__ == "__main__":
  main()
