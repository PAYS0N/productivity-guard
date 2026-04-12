# Project Manifest

---

## Project Context

| File | Description |
|------|-------------|
| [CLAUDE.md](../CLAUDE.md) | Project rules and guidelines for Claude and file management |
| [project_management/manifest.md](manifest.md) | This file — full project file listing with descriptions |
| [project_management/status.md](status.md) | Active work, open items, and closed items tracking |
| [project_management/cdoc.md](cdoc.md) | Template instructions for generating context documents |
| [project_management/prompting.md](prompting.md) | Template instructions for generating task prompts |
| [project_management/standards/style.md](standards/style.md) | Coding conventions: universal rules, naming, formatting, error handling, and build gate |
| [project_management/standards/architecture.md](standards/architecture.md) | Architecture conventions: universal rules, module hierarchy, forbidden patterns, state mutation rules |
| [project_management/prompts/architecture-check.md](prompts/architecture-check.md) | Periodic health check prompt: map current architecture, run forbidden pattern checks, compare to baseline, produce verdict |

---

## Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Deep-dive: DNS mechanism, request flow diagrams, HA integration, extension architecture, edge cases |
| [project_management/cdocs/project-overview.md](cdocs/project-overview.md) | Project overview context document |

---

## Backend

| File | Description |
|------|-------------|
| [backend/main.py](../backend/main.py) | FastAPI app entry point: route definitions, app lifecycle, config loading, `force_blocked_devices` state |
| [backend/blocklist.py](../backend/blocklist.py) | DNS blocklist management: dnsmasq hosts file writes, SIGHUP, temporary unblock scheduling |
| [backend/llm_gatekeeper.py](../backend/llm_gatekeeper.py) | Claude API client: prompt construction, API call, JSON response parsing, access decisions |
| [backend/ha_client.py](../backend/ha_client.py) | Home Assistant REST client: Bermuda room data, entity state queries, service calls |
| [backend/database.py](../backend/database.py) | Async SQLite client (aiosqlite): request history logging and querying |
| [backend/models.py](../backend/models.py) | Pydantic models for API requests, responses, and internal types |
| [backend/system_prompt.txt](../backend/system_prompt.txt) | Static system prompt loaded by LLMGatekeeper at startup |
| [backend/config.example.yaml](../backend/config.example.yaml) | Example configuration file showing all required fields |
| [backend/pyproject.toml](../backend/pyproject.toml) | Python project config: pytest settings (asyncio_mode, testpaths, pythonpath) |
| [backend/requirements.txt](../backend/requirements.txt) | Runtime dependencies |
| [backend/requirements-dev.txt](../backend/requirements-dev.txt) | Development/test dependencies |
| [backend/productivity-guard.service](../backend/productivity-guard.service) | systemd service unit for running the backend on the Pi |

---

## Backend Tests

| File | Description |
|------|-------------|
| [backend/tests/conftest.py](../backend/tests/conftest.py) | Session-scoped pytest fixtures: writes temp config and sets `PG_CONFIG` env var |
| [backend/tests/helpers/fake_config.py](../backend/tests/helpers/fake_config.py) | Fake YAML config dict used by conftest and test fixtures |
| [backend/tests/test_blocklist.py](../backend/tests/test_blocklist.py) | Tests for BlocklistManager: unblock, reblock, scheduling, related domain handling |
| [backend/tests/test_database.py](../backend/tests/test_database.py) | Tests for Database: log_request, get_today_count, get_recent_requests, get_today_history |
| [backend/tests/test_ha_client.py](../backend/tests/test_ha_client.py) | Tests for HAClient: get_device_info, get_device_room, entity state queries |
| [backend/tests/test_llm_gatekeeper.py](../backend/tests/test_llm_gatekeeper.py) | Tests for LLMGatekeeper: prompt building, response parsing, API error handling |
| [backend/tests/test_main.py](../backend/tests/test_main.py) | Tests for main.py API endpoints via FastAPI TestClient |

---

## Extension

| File | Description |
|------|-------------|
| [extension/manifest.json](../extension/manifest.json) | WebExtension MV2 manifest: permissions, background script, UI page declarations |
| [extension/background.js](../extension/background.js) | Background script: `webRequest.onBeforeRequest` interception, active scope management, backend API calls |
| [extension/blocked.html](../extension/blocked.html) | Page shown when a request is blocked; hosts the access request form |
| [extension/blocked.js](../extension/blocked.js) | Logic for blocked.html: reason input, POST to backend, result display |
| [extension/popup.html](../extension/popup.html) | Toolbar popup page |
| [extension/popup.js](../extension/popup.js) | Popup logic: displays active unblocks and current status |
| [extension/options.html](../extension/options.html) | Extension options page |
| [extension/options.js](../extension/options.js) | Options logic: save/load backend URL and device IP from extension storage |
