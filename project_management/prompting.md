Compose a prompt for a new Claude Code session to implement the task. The prompt must:

1. Include an instruction to read `project_management/manifest.md` before proceeding.
2. Require the plan to be presented first, before any code changes.
3. Include only the cdocs relevant to the task — use the routing table below.
4. Where applicable, direct the agent to follow `project_management/standards/style.md`.
5. Where the task involves creating new files, adding imports, or changing module responsibilities, direct the agent to read `project_management/standards/architecture.md` before planning.

## Interview the user if necessary

If management decisions must be made before the prompt can be composed, ask the user — do not decide yourself.

## Cdoc routing table

| Task involves... | Load these cdocs |
|-----------------|-----------------|
| Overall system, project goals, or cross-cutting concerns | `cdocs/project-overview.md` |
| Backend API, access request flow, LLM gating, HA integration | `cdocs/project-overview.md` |
| DNS blocking, blocklist management, dnsmasq | `cdocs/project-overview.md` |
| Firefox extension, request interception, scope management | `cdocs/project-overview.md` |

## Model recommendation

After composing the prompt, indicate the Claude model best suited for the task. This is guidance for the user, not part of the prompt itself.
