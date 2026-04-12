# Architecture Deep Dive

This document covers the detailed technical decisions, data flows, and edge cases for the Productivity Guard system. Read `README.md` first for the overview.

## DNS Blocking Mechanism

### Why `addn-hosts` + SIGHUP

dnsmasq supports multiple mechanisms for blocking domains. We use `addn-hosts` because:

1. **SIGHUP reload**: dnsmasq re-reads `addn-hosts` files on receiving SIGHUP without restarting. This means no DNS downtime, no DHCP lease disruption, and near-instant effect (~1 second).
2. **Separate file**: We use `/etc/dnsmasq.d/blocked_hosts` (separate from `router.conf`) so the backend only needs write access to one file, and we never risk corrupting the main dnsmasq config.
3. **Standard hosts format**: Simple `0.0.0.0 domain.com` lines. Easy to parse and modify programmatically.

### Hosts File Format

```
# Managed by Productivity Guard — do not edit manually
# Last updated: 2026-01-20T15:30:00
0.0.0.0 reddit.com
0.0.0.0 www.reddit.com
0.0.0.0 youtube.com
0.0.0.0 www.youtube.com
0.0.0.0 inv.nadeko.net
0.0.0.0 yewtu.be
0.0.0.0 invidious.nerdvpn.de
```

When a domain is temporarily unblocked, its lines are removed from this file and SIGHUP is sent. A background timer re-adds them after the approval expires.

### Race Condition: DNS Caching

After unblocking a domain in the hosts file and sending SIGHUP, the client's OS may still have the old `0.0.0.0` response cached. Mitigations:

- dnsmasq is configured with short TTLs for blocked responses (we add `local-ttl=5` to dnsmasq config)
- The extension, after receiving approval, waits 2 seconds before retrying navigation (gives DNS cache time to expire)
- Worst case: user refreshes once. Not a major UX issue.

## Request Flow (Detailed)

### Happy Path: Approved Request

```
User clicks reddit.com/r/esp32/thread-123
        │
        ▼
Extension: onBeforeRequest fires
  ├── Checks domain against conditional list → match
  ├── Checks local approved scopes → no match
  ├── Cancels request, shows blocked.html with "Request Access" button
        │
User clicks "Request Access", types reason
        │
        ▼
Extension: POST /request-access
  {
    url: "https://reddit.com/r/esp32/thread-123",
    reason: "debugging BLE scanning issue on ESP32",
    device_ip: "192.168.22.50"  // detected from extension or sent by user config
  }
        │
        ▼
Backend: main.py receives request
  ├── ha_client.py: GET HA API → device room = "office"
  ├── database.py: query today's history → 2 requests, both approved
  ├── llm_gatekeeper.py: build prompt with context, call Claude API
  │     System prompt + user message:
  │     "URL: reddit.com/r/esp32/thread-123
  │      Reason: debugging BLE scanning issue on ESP32
  │      Time: Tuesday 2:30 PM
  │      Device: voidgloom (laptop, office)
  │      Today's requests: 2 (both approved, both work-related)
  │      ..."
  │     Claude responds (JSON):
  │     {"approved": true, "scope": "/r/esp32/*", "duration_minutes": 30,
  │      "message": "Approved. ESP32 debugging is a valid work reason. Scoped to /r/esp32/ for 30 minutes."}
  │
  ├── blocklist.py: remove reddit.com + www.reddit.com from blocked_hosts
  ├── blocklist.py: SIGHUP dnsmasq
  ├── blocklist.py: schedule re-block in 30 minutes
  ├── database.py: log request + outcome
  │
  └── Return to extension:
      {approved: true, scope: "/r/esp32/*", duration_minutes: 30,
       message: "Approved. ESP32 debugging is a valid work reason."}
        │
        ▼
Extension: stores scope {domain: "reddit.com", path_pattern: "/r/esp32/*", expires: <now+30min>}
  ├── Waits 2 seconds (DNS cache)
  ├── Retries original navigation → DNS resolves → page loads
        │
        ▼
User clicks link to reddit.com/ (homepage)
  ├── Extension: onBeforeRequest fires
  ├── Domain matches, check scope: "/" does NOT match "/r/esp32/*"
  └── Blocked. Shows blocked.html. User can request again if they want.
```

### Denied Request

Same flow but Claude returns `{approved: false, ...}`. The extension shows the denial message. No DNS changes.

### Expiry

```
30 minutes pass
        │
        ▼
Backend: asyncio timer fires
  ├── blocklist.py: re-add reddit.com to blocked_hosts
  ├── blocklist.py: SIGHUP dnsmasq
  ├── Notify any connected extension clients (optional, via polling)
        │
        ▼
Extension: scope expiry timer fires (independent of backend)
  ├── Clears stored scope for reddit.com
  ├── Any new navigation to reddit.com → blocked again
```

Both the backend and extension have independent timers. The backend is the authority — even if the extension timer is off by a few seconds, DNS will be re-blocked.

## LLM Prompt Architecture

### System Prompt Structure

The system prompt in `system_prompt.txt` is static — it's your "sober self" rules. At request time, the backend injects dynamic context into the user message.

**System prompt covers**:
- Role definition ("strict productivity gatekeeper, default DENY")
- Response format (must be JSON: `{approved, scope, duration_minutes, message}`)
- Evaluation criteria (URL relevance, reason specificity, time awareness)
- Concrete approve/deny examples
- Escalation rules (more requests = stricter)
- Anti-manipulation instructions
- Relax rules (time windows, room requirements)

**User message (built at runtime) contains**:
- The URL being requested
- The user's stated reason
- Current time and day of week
- Device name and room (from Bermuda)
- Today's request count and last N requests with outcomes
- Whether current time falls in a relax window
- Whether device is in a relax-eligible room

### Structured Output

We instruct Claude to respond in JSON only. The backend parses this. If parsing fails, default to DENY.

```json
{
  "approved": true,
  "scope": "/r/esp32/*",
  "duration_minutes": 30,
  "message": "Approved. ESP32 debugging is a valid work reason. Scoped to /r/esp32/ for 30 minutes."
}
```

The `scope` field is a path prefix pattern. The extension does simple prefix matching: if the URL path starts with the scope (minus the trailing `*`), it's allowed.

### Anti-Manipulation

Key elements:
- **Temperature 0.2**: Reduces creative/agreeable responses
- **Request count injection**: The LLM sees "this is request #7 today" and has instructions to be near-impossible to convince past a threshold
- **History injection**: The LLM sees your previous reasons. Repeating variations of the same excuse is visible.
- **No emotional appeals**: The prompt explicitly says to ignore urgency, FOMO, and "just one more" framing.
- **URL coherence**: If reason says "microcontroller research" but URL is `youtube.com/watch?v=cat-video`, deny.

## Extension Architecture

### Manifest V2 (not V3)

Firefox still fully supports Manifest V2 and it's required for synchronous `webRequest.onBeforeRequest` blocking. MV3's `declarativeNetRequest` is less flexible for our dynamic scope matching.

### Request Interception

```javascript
browser.webRequest.onBeforeRequest.addListener(
  handleRequest,
  { urls: ["*://*.reddit.com/*", "*://*.youtube.com/*", ...] },
  ["blocking"]
);
```

The listener returns `{cancel: true}` and redirects to `blocked.html` with the original URL as a query parameter. If the URL matches an active approved scope, it returns `{}` (allow).

### Scope Matching

Scopes are stored in the background script's memory (not persistent storage — they're transient).

```javascript
// Approved scope example
{
  domain: "reddit.com",
  pathPrefix: "/r/esp32/",  // derived from scope "/r/esp32/*"
  expires: 1706123456789,   // Unix timestamp
  originalUrl: "https://reddit.com/r/esp32/thread-123"
}
```

URL matching: extract domain and path from the intercepted URL. If domain matches a scope entry AND the path starts with `pathPrefix` AND `Date.now() < expires`, allow.

### Device IP Detection

The extension needs to send the device's IP to the backend so the backend knows which device is requesting. Options:
1. **Configure it manually** in extension options (simplest, most reliable)
2. **Backend detects it** from the HTTP request source IP (works since it's all on the local network)

We use option 2 as primary (FastAPI `request.client.host`) with option 1 as override.

## Home Assistant Integration

### Bermuda Room Data

Bermuda exposes entities like `sensor.payson_s25_room` (exact entity name depends on HA config). The backend queries HA's REST API:

```
GET http://192.168.22.1:8123/api/states/sensor.payson_s25_room
Authorization: Bearer <long-lived-token>
```

Response includes the room name as the entity state.

### Device-to-IP Mapping

The backend config maps device IPs to HA entity names:

```yaml
devices:
  "192.168.22.50":
    name: "voidgloom"
    type: "laptop"
    bermuda_entity: "sensor.voidgloom_ble_room"  # if tracked
  "192.168.22.75":
    name: "payson_s25"
    type: "phone"
    bermuda_entity: "sensor.payson_s25_ble_room"
```

Not all devices need Bermuda tracking. If a device doesn't have a Bermuda entity, the room context is "unknown" and room-based rules are skipped.

### Automations

HA automations can call the backend API proactively:

**Phone in bedroom → block everything**:
```yaml
trigger:
  - platform: state
    entity_id: sensor.payson_s25_ble_room
    to: "bedroom"
action:
  - service: rest_command.force_block_device
    data:
      device_ip: "192.168.22.75"
```

This calls a backend endpoint that revokes any active approvals for that device and sets a "force blocked" flag that causes all new requests from that IP to be auto-denied.

## Database Schema

SQLite at the configured path. Single table for request history.

```sql
CREATE TABLE requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,          -- ISO 8601
    device_ip TEXT NOT NULL,
    device_name TEXT,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    reason TEXT NOT NULL,
    room TEXT,                        -- from Bermuda, nullable
    approved INTEGER NOT NULL,        -- 0 or 1
    scope TEXT,                       -- approved scope pattern, nullable
    duration_minutes INTEGER,         -- nullable
    llm_message TEXT,                 -- LLM's explanation
    request_number_today INTEGER      -- nth request today
);
```

## Deployment

### systemd Service

The backend runs as a systemd service under the `pays0n` user with targeted sudo access.

### sudoers Entry

```
pays0n ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/dnsmasq.d/blocked_hosts
pays0n ALL=(ALL) NOPASSWD: /usr/bin/pkill -HUP dnsmasq
```

The backend calls these via `subprocess.run(["sudo", ...])`.

### iptables Rule

```
-A INPUT -s 192.168.22.0/24 -i wlan0 -p tcp -m tcp --dport 8800 -j ACCEPT
```

Added during setup, saved with `netfilter-persistent`.

## Edge Cases and Failure Modes

1. **Claude API down**: Default to DENY. The extension shows "Gatekeeper unavailable, access denied."
2. **HA API down**: Proceed without room context. The LLM is told "room: unavailable" and room-based rules are skipped.
3. **dnsmasq SIGHUP fails**: Log error, report to extension. The approval is granted in the extension's local scope but DNS may not resolve. User may need to wait or the backend retries.
4. **Extension disabled**: DNS blocklist is still active. User is fully blocked with no way to request access. This is by design — removing the extension makes things stricter, not looser.
5. **Multiple devices**: Each device's approvals are independent. Approving reddit on the laptop doesn't affect the phone's DNS block. (Note: DNS is domain-wide, so temporarily unblocking reddit.com at DNS level means ALL devices can resolve it during that window. The extension on other devices still enforces scopes. Devices without the extension get full domain access during the window. This is an acceptable tradeoff — the window is short and the primary enforcement target is the requesting device.)
6. **Backend crashes**: DNS blocklist stays in its last state. If domains were unblocked, they stay unblocked until the backend restarts. The systemd service auto-restarts. On startup, the backend re-generates the full blocklist from config (re-blocking everything).

## Future Enhancements

- Web dashboard for viewing request history and patterns
- Weekly productivity reports (which domains requested most, approval rate, etc.)
- Integration with focus/Pomodoro timers
- Per-device rule customization
- Gradual trust: if you've been good for a week, auto-approve certain patterns
