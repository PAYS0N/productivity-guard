# Architecture Conventions: Productivity Guard

## Universal Rules

- **Single responsibility per module** — Every file/module owns one concern. If you can't describe what it does in one sentence without "and", split it.
- **Dependency direction is inward/downward** — High-level modules do not reference low-level modules. The project-specific layer table below defines what "inward/downward" means for this project.
- **No circular dependencies** — No module may reference a module that (directly or transitively) references it.
- **Explicit references, no implicit coupling** — When a module needs something from another module, it references it explicitly. No shared mutable singletons, no coupling through side channels. For code projects: no global mutable state, explicit imports only.
- **Public interfaces have at least one test** *(code)* — Every public function, method, or API endpoint has at least one test exercising it. Internal helpers may be tested indirectly through their callers.
- **No side effects at import time** *(code)* — Importing a module does not trigger behavior. Initialization happens explicitly.
- **Separate I/O from logic** *(code)* — Pure computation should be separable from I/O (file, network, user input).

---

## Module Hierarchy

Files are organized in layers. A module may only reference its own layer or lower layers — never upward.

### Backend

| Layer | Modules | Responsibility |
|-------|---------|----------------|
| 0 — Entry | `backend/main.py` | FastAPI app: route definitions, app lifecycle, config loading, global `force_blocked_devices` state |
| 1 — Domain | `backend/blocklist.py` | DNS blocklist management: hosts file writes, dnsmasq SIGHUP, unblock scheduling, `active_unblocks` state |
| 1 — Domain | `backend/llm_gatekeeper.py` | Claude API interaction: prompt construction, API call, response parsing, access decisions |
| 1 — Domain | `backend/ha_client.py` | Home Assistant REST client: room data queries, entity state, service calls |
| 1 — Domain | `backend/database.py` | Request history: async SQLite read/write via aiosqlite |
| 2 — Data | `backend/models.py` | Pydantic models for API types and internal data structures; no logic |

### Extension

| Layer | Modules | Responsibility |
|-------|---------|----------------|
| 0 — Entry | `extension/background.js` | Request interception, active scope tracking, backend API communication |
| 1 — UI | `extension/blocked.js` | Access request form on the blocked page |
| 1 — UI | `extension/popup.js` | Toolbar popup: active unblock status display |
| 1 — UI | `extension/options.js` | User settings: backend URL and device IP configuration |

**Rule: no upward references.** Domain modules (`blocklist`, `llm_gatekeeper`, `ha_client`, `database`) must never import from `main.py`. Extension UI scripts must not import from `background.js`.

## Module Responsibilities

- **main.py** — FastAPI app entry point. Owns HTTP routing, app lifecycle (startup/shutdown hooks), global config loading, and the `force_blocked_devices` set. Only place where routes are defined.
- **blocklist.py** — Owns all DNS blocklist mutations. Only module that writes the dnsmasq hosts file or sends SIGHUP. Owns the `active_unblocks` dict and all re-block scheduling.
- **llm_gatekeeper.py** — Owns the Claude API interaction. Only module that constructs the LLM prompt and parses the JSON response. Returns `LLMDecision` to `main.py`.
- **ha_client.py** — Owns all Home Assistant API communication. No domain logic — queries entities and returns state strings.
- **database.py** — Owns all SQLite read/write. No domain logic — persists and retrieves request history rows.
- **models.py** — Defines data contracts (Pydantic models). No logic, no imports from other project modules.
- **background.js** — Owns request interception and active scope state. Only JS module that communicates with the backend API.

## State / Data Mutation Rules

- **`active_unblocks` (BlocklistManager dict)**: changed only in `blocklist.py` via `unblock_domain`, `reblock_domain`, `reblock_all`, and the internal `_reblock_after` timer.
- **DNS blocklist file** (`/etc/dnsmasq.d/blocked_hosts`): written only in `blocklist.py` via `_write_blocklist`.
- **`force_blocked_devices` (main.py set)**: changed only in `main.py` via the `/force-block` and `/force-unblock` endpoints.
- **SQLite database**: written only in `database.py` via `log_request`.

## Adding New Modules

When creating a new file or component:
1. Determine its layer in the hierarchy above. If it doesn't fit an existing layer, that's a signal to reconsider the design.
2. Ensure it references only its layer or below.
3. Give it a single clear responsibility that doesn't overlap with existing modules.
4. Update the module hierarchy table in this document.
5. Update `project_management/artifacts/architecture-baseline.md` with the new dependency.
