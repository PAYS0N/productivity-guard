---
sources:
  - prod-guard/extension/manifest.json
  - prod-guard/extension/background.js
  - prod-guard/extension/blocked.js
  - prod-guard/extension/popup.js
  - prod-guard/extension/options.js
  - prod-guard/extension/blocked.html
  - prod-guard/extension/popup.html
  - prod-guard/extension/options.html
---

# Firefox Extension

## Overview

Manifest V2 WebExtension. MV2 is required for synchronous `webRequest.onBeforeRequest` blocking — MV3's `declarativeNetRequest` cannot do dynamic path-level scope matching. Distributed as `.xpi` via AMO.

## Request interception (`background.js`)

On startup, reads `apiUrl` and `conditionalDomains` from `browser.storage.local`, then calls `setupRequestListener()` which registers `handleRequest` as a blocking listener on `main_frame` requests matching all conditional domain URL patterns.

`handleRequest(details)`:
1. If domain not in `CONDITIONAL_DOMAINS` → allow
2. If `approvedScopes` has an entry for this domain with `Date.now() < expires` AND path matches `pathPrefix` → allow
3. Otherwise: store `{url, domain}` in `pendingRequests` keyed by `tabId`, redirect to `blocked.html?url=...&domain=...`

`pathMatchesScope(fullPath, scopePrefix)` — strips trailing `*`, checks `fullPath.startsWith(prefix)`. `"/*"` or `"/"` are treated as wildcard (allow all paths).

## State

`approvedScopes: Map<domain, {pathPrefix, expires, originalUrl, scope}>` — active approved scopes in memory. Keyed for both base domain and www variant when applicable. Cleared by `setTimeout` at expiry + by a `setInterval` cleanup every 30 seconds.

`pendingRequests: Map<tabId, {url, domain}>` — tracks which tab is waiting at the blocked page.

## Blocked page (`blocked.html` / `blocked.js`)

Reads `url` and `domain` from query params. Sends `GET_PENDING` to background to retrieve the blocked URL, then presents a form for the user to type a reason. On submit, sends `REQUEST_ACCESS` message to background, which calls `handleAccessRequest`.

On approval: background stores scope, schedules cleanup, waits 2500ms (DNS propagation), then navigates the original tab to the URL.

## Message types (background ↔ pages)

| Type | Direction | Purpose |
|------|-----------|---------|
| `REQUEST_ACCESS` | page → bg | Send URL + reason to backend |
| `GET_PENDING` | page → bg | Get blocked URL for current tab |
| `GET_STATUS` | popup → bg | Get active scopes + apiUrl |
| `UPDATE_SETTINGS` | options → bg | Update apiUrl and/or conditionalDomains |

## Popup (`popup.html` / `popup.js`)

Sends `GET_STATUS`, displays active approved scopes with remaining seconds and path prefix.

## Options (`options.html` / `options.js`)

Saves/loads `apiUrl` and `conditionalDomains` (newline-separated in a textarea) to `browser.storage.local` and propagates via `UPDATE_SETTINGS` message.
