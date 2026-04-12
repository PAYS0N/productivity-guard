---
sources:
  - prod-guard/backend/blocklist.py
---

# DNS Blocklist

## Overview

`BlocklistManager` manages a dnsmasq `addn-hosts` file that maps blocked domains to `0.0.0.0`. Rewriting the file and sending `SIGHUP` (`pkill -HUP dnsmasq`) reloads dnsmasq in ~1 second with no restart or DHCP disruption. Both operations run via `sudo tee` and `sudo pkill` — require sudoers entries.

## Domain sets

`conditional_domains` — temporarily blockable on request. `always_blocked_domains` — never unblockable. `all_blocked_domains = conditional | always_blocked`. Both sets are populated from `config.yaml` at init.

## Hosts file format

```
# Managed by Productivity Guard — do not edit manually
# Updated: <ISO timestamp>
0.0.0.0 domain.com
0.0.0.0 www.domain.com
```

One `0.0.0.0 <domain>` line per blocked domain, sorted. Written atomically via `sudo tee`.

## Active unblocks

`active_unblocks: dict[str, ActiveUnblock]` maps domain → `ActiveUnblock`. Both the base domain and its `www`/non-`www` variant are tracked under the same `ActiveUnblock` object. On `_write_blocklist`, all domains in `active_unblocks` are excluded from the file.

`ActiveUnblock` fields: `domain`, `device_ip`, `device_name`, `scope`, `reason`, `unblocked_at`, `expires_at`, `timer_task` (asyncio Task).

## Unblock flow

`unblock_domain(domain, device_ip, device_name, scope, reason, duration_minutes)`:
1. Reject always-blocked or unknown domains
2. If domain already unblocked, cancel existing timer
3. Compute related domains (`www` ↔ base) that exist in `all_blocked_domains`
4. Register all related domains in `active_unblocks`
5. Rewrite blocklist file, SIGHUP dnsmasq
6. Schedule `_reblock_after(domains, minutes)` as an asyncio Task

## Reblock flow

`reblock_domain(domain)` — removes domain + related from `active_unblocks`, cancels timer, rewrites file, SIGHUP. `reblock_all()` — cancels all timers, clears dict, rewrites, SIGHUP.

`_reblock_after` — awaits `asyncio.sleep(minutes * 60)`, then removes from dict and rewrites. Catches `CancelledError` silently (manual reblock or extension).

## On startup / shutdown

`initialize()` — writes the full blocklist (all domains blocked) and SIGHUPs. Called during FastAPI lifespan startup. `reblock_all()` is called on shutdown to ensure clean state.

## Callback

Optional `on_reblock_callback: Callable[[str], Awaitable[None]]` — called per domain after auto-reblock timer fires. Not currently wired in `main.py`.
