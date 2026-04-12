# Project Manifest

---

## Project Context

| File | Description |
|------|-------------|
| [CLAUDE.md](../CLAUDE.md) | Project rules and guidelines for Claude and file management |
| [project_management/manifest.md](manifest.md) | This file — full project file listing with descriptions |
| [project_management/status.md](status.md) | Active work, open items, and closed items tracking |
| [project_management/cdoc.md](cdoc.md) | Template instructions for generating context documents |
| [project_management/prompting.md](prompting.md) | Cdoc routing table and instructions for generating task prompts |
| [project_management/standards/style.md](standards/style.md) | Coding conventions: naming, formatting, error handling, build gate |
| [project_management/standards/architecture.md](standards/architecture.md) | Architecture conventions: module hierarchy, forbidden patterns, state mutation rules |
| [project_management/prompts/architecture-check.md](prompts/architecture-check.md) | Periodic health check prompt |

---

## Context Documents

| File | Description |
|------|-------------|
| [project_management/cdocs/project-overview.md](cdocs/project-overview.md) | System overview: components, hybrid enforcement model, request lifecycle |
| [project_management/cdocs/backend-api.md](cdocs/backend-api.md) | FastAPI routes, request flow, config loading, models, known issues |
| [project_management/cdocs/llm-gatekeeper.md](cdocs/llm-gatekeeper.md) | Claude API, system prompt rules, prompt structure, response parsing |
| [project_management/cdocs/dns-blocklist.md](cdocs/dns-blocklist.md) | BlocklistManager, dnsmasq hosts file, unblock/reblock scheduling |
| [project_management/cdocs/ha-integration.md](cdocs/ha-integration.md) | HAClient, Bermuda room tracking, device map, HA automations and rest_commands |
| [project_management/cdocs/database.md](cdocs/database.md) | SQLite schema, aiosqlite, request history query methods |
| [project_management/cdocs/extension.md](cdocs/extension.md) | Firefox MV2 extension: interception, scope matching, blocked/popup/options pages |
| [project_management/cdocs/deployment.md](cdocs/deployment.md) | Network topology, setup.sh, systemd service, sudoers, DoH blocking, config.yaml |

---

## Documentation

| File | Description |
|------|-------------|
| [prod-guard/README.md](../prod-guard/README.md) | Project overview, architecture diagram, how it works, infrastructure context |
| [prod-guard/ARCHITECTURE.md](../prod-guard/ARCHITECTURE.md) | Deep-dive: DNS mechanism, request flow diagrams, HA integration, edge cases |

---

## Backend

| File | Description |
|------|-------------|
| [prod-guard/backend/main.py](../prod-guard/backend/main.py) | FastAPI app entry point: route definitions, app lifecycle, config loading, `force_blocked_devices` state |
| [prod-guard/backend/blocklist.py](../prod-guard/backend/blocklist.py) | DNS blocklist management: dnsmasq hosts file writes, SIGHUP, temporary unblock scheduling |
| [prod-guard/backend/llm_gatekeeper.py](../prod-guard/backend/llm_gatekeeper.py) | Claude API client: prompt construction, API call, JSON response parsing, access decisions |
| [prod-guard/backend/ha_client.py](../prod-guard/backend/ha_client.py) | Home Assistant REST client: Bermuda room data, entity state queries, service calls |
| [prod-guard/backend/database.py](../prod-guard/backend/database.py) | Async SQLite client (aiosqlite): request history logging and querying |
| [prod-guard/backend/models.py](../prod-guard/backend/models.py) | Pydantic models for API requests, responses, and internal types |
| [prod-guard/backend/system_prompt.txt](../prod-guard/backend/system_prompt.txt) | Static system prompt loaded by LLMGatekeeper at startup |
| [prod-guard/backend/config.example.yaml](../prod-guard/backend/config.example.yaml) | Example configuration file showing all required fields |
| [prod-guard/backend/pyproject.toml](../prod-guard/backend/pyproject.toml) | Python project config: pytest settings (asyncio_mode, testpaths, pythonpath) |
| [prod-guard/backend/requirements.txt](../prod-guard/backend/requirements.txt) | Runtime dependencies |
| [prod-guard/backend/requirements-dev.txt](../prod-guard/backend/requirements-dev.txt) | Development/test dependencies |
| [prod-guard/backend/productivity-guard.service](../prod-guard/backend/productivity-guard.service) | systemd service unit for running the backend on the Pi |

---

## Backend Tests

| File | Description |
|------|-------------|
| [prod-guard/backend/tests/conftest.py](../prod-guard/backend/tests/conftest.py) | Session-scoped pytest fixtures: writes temp config and sets `PG_CONFIG` env var |
| [prod-guard/backend/tests/helpers/fake_config.py](../prod-guard/backend/tests/helpers/fake_config.py) | Fake YAML config dict used by conftest and test fixtures |
| [prod-guard/backend/tests/test_blocklist.py](../prod-guard/backend/tests/test_blocklist.py) | Tests for BlocklistManager: unblock, reblock, scheduling, related domain handling |
| [prod-guard/backend/tests/test_database.py](../prod-guard/backend/tests/test_database.py) | Tests for Database: log_request, get_today_count, get_recent_requests, get_today_history |
| [prod-guard/backend/tests/test_ha_client.py](../prod-guard/backend/tests/test_ha_client.py) | Tests for HAClient: get_device_info, get_device_room, entity state queries |
| [prod-guard/backend/tests/test_llm_gatekeeper.py](../prod-guard/backend/tests/test_llm_gatekeeper.py) | Tests for LLMGatekeeper: prompt building, response parsing, API error handling |
| [prod-guard/backend/tests/test_main.py](../prod-guard/backend/tests/test_main.py) | Tests for main.py API endpoints via FastAPI TestClient |

---

## Extension

| File | Description |
|------|-------------|
| [prod-guard/extension/manifest.json](../prod-guard/extension/manifest.json) | WebExtension MV2 manifest: permissions, background script, UI page declarations |
| [prod-guard/extension/background.js](../prod-guard/extension/background.js) | Background script: `webRequest.onBeforeRequest` interception, active scope management, backend API calls |
| [prod-guard/extension/blocked.html](../prod-guard/extension/blocked.html) | Page shown when a request is blocked; hosts the access request form |
| [prod-guard/extension/blocked.js](../prod-guard/extension/blocked.js) | Logic for blocked.html: reason input, POST to backend, result display |
| [prod-guard/extension/popup.html](../prod-guard/extension/popup.html) | Toolbar popup page |
| [prod-guard/extension/popup.js](../prod-guard/extension/popup.js) | Popup logic: displays active unblocks and current status |
| [prod-guard/extension/options.html](../prod-guard/extension/options.html) | Extension options page |
| [prod-guard/extension/options.js](../prod-guard/extension/options.js) | Options logic: save/load backend URL and device IP from extension storage |

---

## Home Assistant

| File | Description |
|------|-------------|
| [prod-guard/homeassistant/automations.yaml](../prod-guard/homeassistant/automations.yaml) | HA automations: force-block phone on bedroom entry, remove on exit |
| [prod-guard/homeassistant/rest_commands.yaml](../prod-guard/homeassistant/rest_commands.yaml) | HA rest_command definitions for calling backend force-block/unblock/revoke endpoints |

---

## Setup

| File | Description |
|------|-------------|
| [prod-guard/setup.sh](../prod-guard/setup.sh) | One-time Pi setup: venv, dnsmasq config, iptables, sudoers, systemd service install |
| [prod-guard/setup_doh_block.sh](../prod-guard/setup_doh_block.sh) | Creates dnsmasq config to block DNS-over-HTTPS providers (canary domain + hostname blocking) |
