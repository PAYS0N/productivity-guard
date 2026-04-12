---
sources:
  - prod-guard/backend/main.py
  - prod-guard/backend/models.py
---

# Backend API

## Overview

FastAPI app running on the Pi at `:8800`. Serves as the orchestration layer: receives access requests from the extension, gathers context, calls the LLM, acts on its decision, and logs the result.

## Config loading

Config is loaded at module import time from `config.yaml` (path from `PG_CONFIG` env var or adjacent `config.yaml`). Components are instantiated as module-level globals: `db`, `blocklist`, `ha_client`, `llm`. The `force_blocked_devices: set[str]` is also module-level global state.

## App lifecycle

Startup (`lifespan`): connects DB, connects HA, writes initial blocklist. Shutdown: re-blocks all domains, closes HA and DB.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/request-access` | Main flow: LLM evaluation → DNS unblock → DB log |
| `POST` | `/debug/prompt` | Returns the system prompt + user message without calling LLM |
| `GET` | `/status` | Active unblocks and force-blocked devices |
| `GET` | `/history` | Today's request log |
| `POST` | `/force-block` | Add device to `force_blocked_devices`; revoke its active unblocks |
| `POST` | `/force-unblock` | Remove device from `force_blocked_devices` |
| `POST` | `/revoke/{domain}` | Immediately re-block a domain |
| `POST` | `/revoke-all` | Re-block all domains |
| `GET` | `/health` | Liveness check |

## Request flow (`/request-access`)

1. Determine `device_ip` (body field or `request.client.host`)
2. Extract domain from URL
3. If device is force-blocked → deny immediately
4. Map domain to conditional entry via `domain_to_conditional()`; deny if not found or always-blocked
5. Gather context: HA room, DB today count, DB recent history
6. Call `llm.evaluate_request()` → `LLMDecision`
7. If approved: call `blocklist.unblock_domain()`; flip `approved=False` on DNS failure
8. Log to DB via `db.log_request()`
9. Return `AccessResponse`

## Key helpers

`extract_domain(url)` — extracts `netloc` from URL. `domain_to_conditional(domain)` — maps a domain (with or without `www.`) to its entry in `config["domains"]["conditional"]`; returns `None` if not managed. **Known bug**: `lstrip("www.")` at lines 163 and 221 strips individual chars, not a prefix; domains starting with `w` or `.` may be incorrectly handled.

## Models

`AccessRequest`: `{url, reason, device_ip?}`. `AccessResponse`: `{approved, scope?, duration_minutes?, message, domain?}`. `LLMDecision`: `{approved, scope="/*", duration_minutes=15, message=""}`. `StatusResponse`: `{active_unblocks: [DomainStatus], force_blocked_devices: [str]}`. `ForceBlockRequest` / `ForceUnblockRequest`: `{device_ip}`.

## Known issues

`/debug/prompt` and `/request-access` both define a function named `request_access` — FastAPI retains both routes (decorators capture function objects), but the name collision is a latent bug.
