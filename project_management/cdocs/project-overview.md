---
sources:
  - prod-guard/README.md
  - prod-guard/ARCHITECTURE.md
---

# Productivity Guard — Overview

## Project

**Name:** Productivity Guard

**Description:** Productivity Guard is a self-hosted web access control system that blocks distracting domains at the DNS level and requires users to justify requests through a Claude AI gatekeeper before temporarily unblocking them. It is built for personal use to enforce intentional browsing habits: the FastAPI backend evaluates each request using context from Home Assistant (device room, request history) and either grants a scoped, time-limited unblock or denies access with an explanation.

## System components

- **Backend** (`prod-guard/backend/`) — Python/FastAPI app running on a Raspberry Pi. Receives extension requests, gathers HA context, calls Claude, manages the dnsmasq blocklist, logs to SQLite.
- **Extension** (`prod-guard/extension/`) — Firefox WebExtension (MV2). Intercepts navigation to blocked domains, shows blocked.html, sends access requests, stores approved scopes, retries navigation after DNS propagates.
- **dnsmasq** — DNS + DHCP server on the Pi. All WiFi clients use the Pi as gateway and DNS resolver. Blocked domains resolve to `0.0.0.0`.
- **Home Assistant** — Docker container on the Pi. Bermuda BLE integration tracks device room locations. HA automations call the backend to force-block devices.

## Hybrid enforcement model

DNS alone can only block/unblock entire domains; extension alone can be disabled. The hybrid provides: hard DNS blocking as the floor (requires Pi access to bypass), intelligent path-level control via the extension, and seamless UX (2.5s wait after approval for DNS propagation).

## Request lifecycle

1. Browser navigates to blocked domain → extension intercepts (`onBeforeRequest`)
2. Extension redirects to `blocked.html`; user enters reason
3. Extension POSTs `{url, reason}` to `/request-access`
4. Backend queries HA for room, queries DB for history, calls Claude
5. If approved: DNS unblocked, scope and expiry returned
6. Extension stores scope, navigates to original URL after 2.5s
7. Backend re-blocks after `duration_minutes`; extension clears scope at expiry
