## Project Summary

Read project_management/manifest.md.

Productivity Guard is a FastAPI backend and Firefox extension that uses Claude as an LLM gatekeeper for DNS-level web access control, blocking distracting domains at the router and requiring users to justify access requests before temporarily unblocking them.

## Response rules

- When the user says "implement" or "implement <file>.md": read the specified prompt file (default: `project_management/prompts/implement-this.md`), implement the task described in it (plan-first, work with the user), then after the user confirms completion, run `python project_management/scripts/shutdown.py` from the repo root and follow its output to update all flagged documentation.

## Meta rules

- Challenge requests that are logically or structurally wrong, or where a clearly better approach exists (e.g. using markdown as a database). Briefly explain the concern and suggest an alternative before proceeding.

- Remember: If tracing code execution manually to understand a bug requires more than 2-3 reasoning steps without certainty, add targeted logging statements, ask the user to run them, and use the output to diagnose rather than guessing.

- Remember: All non-code files should be markdown unless specifically mentioned otherwise.

## Context Rules

- Remember: When asked to create or edit a context document, read project_management/cdoc.md.

- Remember: When asked to record an issue or summarize project status, read project_management/status.md.

- Remember: When asked to create project management files, create them in the project_management directory in root.

- Remember: Before creating new source files, adding cross-module imports, or moving responsibilities between modules, read `project_management/standards/architecture.md`.