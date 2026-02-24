# Productivity Guard

A self-hosted, LLM-gated web access control system that blocks distracting websites at the network level (DNS) and allows intelligent, context-aware temporary unblocking through a browser extension that negotiates with a Claude API-powered backend.

## Problem

You want to block distracting sites (Reddit, YouTube, etc.) but sometimes have legitimate reasons to access them (e.g., a Reddit thread about an ESP32 bug you're debugging). Traditional blockers are all-or-nothing. This system lets you **bargain** with an LLM gatekeeper that understands context: what URL you want, why, what time it is, and where you are in the house.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Raspberry Pi (Router)                       │
│                                                                │
│  ┌─────────────┐    ┌──────────────────────┐    ┌──────────┐ │
│  │  dnsmasq     │◄───│  Blocklist Manager   │    │  Home    │ │
│  │  (DNS+DHCP)  │    │  (blocked_hosts file │    │Assistant │ │
│  │              │    │   + SIGHUP dnsmasq)  │    │ (Docker) │ │
│  └─────────────┘    └──────────┬───────────┘    └────┬─────┘ │
│                                │                      │       │
│                     ┌──────────┴───────────┐          │       │
│                     │  FastAPI Backend      │◄─────────┘       │
│                     │  (LLM Gatekeeper)     │  (Bermuda room  │
│                     │  :8800                │   data via REST) │
│                     └──────────┬───────────┘                  │
│                                │                               │
└────────────────────────────────┼───────────────────────────────┘
                                 │ HTTP API
                    ┌────────────┴────────────┐
                    │                         │
              ┌─────┴─────┐            ┌──────┴──────┐
              │  Firefox   │            │  Firefox    │
              │  Extension │            │  Extension  │
              │  (Desktop) │            │  (Android)  │
              └───────────┘            └─────────────┘
```

### How It Works

1. **DNS blocks all conditional domains by default** for all devices on the network. dnsmasq serves `0.0.0.0` for blocked domains via an `addn-hosts` file.

2. **When you navigate to a blocked site**, the Firefox extension intercepts the request (before DNS even fires), shows a popup asking for your reason.

3. **The extension sends your request** (URL, reason, device info) to the FastAPI backend running on the Pi.

4. **The backend gathers context**: current time, your device's room location (via Home Assistant + Bermuda BLE tracking), your request history today, and your configured rules.

5. **The backend calls the Claude API** with all this context + a carefully crafted system prompt that encodes your "sober self" productivity rules.

6. **If approved**: the backend temporarily removes the domain from the DNS blocklist, sends `SIGHUP` to dnsmasq (instant reload), and returns the approval with a scope (e.g., `/r/esp32/*` for 30 minutes) and duration.

7. **The extension stores the approved scope** and retries the navigation. DNS now resolves. If you navigate outside the approved scope (e.g., click to Reddit homepage), the extension blocks it client-side.

8. **When the approval expires**, the backend re-adds the domain to the blocklist and signals dnsmasq. The extension clears its local scope.

### Why DNS + Extension (Hybrid Approach)

- **DNS alone** can only block/unblock entire domains. It can't distinguish `reddit.com/r/esp32` from `reddit.com/r/memes`.
- **Extension alone** can be disabled by the user, providing no real enforcement.
- **HTTPS MITM proxy** (the only way to do per-path filtering at network level) requires installing custom CA certs on every device, breaks certificate pinning (banking apps, etc.), and is fragile.
- **The hybrid** gives you: hard DNS blocking as the floor (can't be bypassed without Pi access), intelligent path-level control via the extension, and a seamless UX.

## Infrastructure Context

### Network Topology (Pi as Router)

- **Pi IP**: `192.168.22.1` (gateway for all WiFi clients)
- **WiFi**: hostapd on `wlan0`, SSID "Payson"
- **DNS/DHCP**: dnsmasq on `wlan0`, range `.100-.200`, static leases for known devices
- **Internet**: eth0 (upstream), NAT via iptables
- **Access control**: iptables + ipset (`allowed_internet`) controls which devices get internet
- **Docker**: Home Assistant at `172.19.0.10` (bridge network `172.19.0.0/16`), published on `:8123`
- **Tailscale**: Present for remote access

### Key Device IPs

| Device | IP | Type |
|---|---|---|
| Pi (kuudra) | 192.168.22.1 | Router/Gateway |
| ESP32 proxies | .10-.12 | Bermuda BLE proxies |
| voidgloom | .50 | Laptop/PC |
| plantera | .51 | Laptop/PC |
| akura_malice | .52 | Laptop/PC |
| coral | .53 | Laptop/PC |
| payson_s25 | .75 | Phone (Samsung S25) |
| iphone_14 | .76 | Phone |
| notebook | .77 | Tablet |

### Existing Config Files (on Pi)

- `/etc/hostapd/hostapd.conf` — AP config
- `/etc/dnsmasq.d/router.conf` — DNS/DHCP config
- `/etc/iptables/rules.v4` — Firewall rules (saved via `netfilter-persistent`)
- `/etc/ipset.conf` — IP sets for internet access control
- `/home/pays0n/homeassistant/` — HA config directory

### Home Assistant + Bermuda

- HA is running as a Docker container
- Bermuda is installed as an HA integration for BLE room-level device tracking
- ESP32-S3 devices (`.10-.12`) act as BLE proxies in different rooms
- Bermuda exposes room data via HA entities (e.g., `sensor.payson_s25_ble_room`)
- HA REST API is available at `http://172.19.0.10:8123/api/` (or `http://192.168.22.1:8123/api/`)

## Components

### 1. Backend (`backend/`)

**Stack**: Python 3, FastAPI, uvicorn, anthropic SDK, httpx, aiosqlite

**Files**:
- `main.py` — FastAPI app, endpoint definitions, startup/shutdown lifecycle
- `blocklist.py` — Manages `/etc/dnsmasq.d/blocked_hosts`, adds/removes domains, sends SIGHUP to dnsmasq
- `llm_gatekeeper.py` — Builds Claude API requests with context, parses structured responses
- `ha_client.py` — Queries Home Assistant REST API for Bermuda room data and other entity states
- `models.py` — Pydantic models for API requests/responses
- `database.py` — SQLite for request history logging
- `config.yaml` — All configuration: blocked domains, rules, schedule, HA connection info
- `system_prompt.txt` — The LLM system prompt encoding productivity rules
- `requirements.txt` — Python dependencies
- `productivity-guard.service` — systemd unit file

**API Endpoints**:
- `POST /request-access` — Extension sends `{url, reason, device_ip}`, gets back `{approved, scope, duration_minutes, message}`
- `GET /status` — Returns current state: which domains are temporarily unblocked, for whom, time remaining
- `POST /revoke/{domain}` — Manually re-block a domain immediately
- `GET /history` — Returns today's request log

**Runs on**: `http://192.168.22.1:8800`

### 2. Firefox Extension (`extension/`)

**Type**: WebExtension (Manifest V2 for `webRequest.onBeforeRequest` blocking support)

**Files**:
- `manifest.json` — Extension manifest with permissions for webRequest, all URLs, storage
- `background.js` — Service worker: intercepts requests to conditional domains, manages approved scopes, communicates with backend
- `popup.html` + `popup.js` — UI shown when blocked: text input for reason, submit button, displays LLM response
- `options.html` + `options.js` — Settings page: backend API URL configuration
- `blocked.html` + `blocked.js` — Page shown when navigation is blocked (domain blocked + no approval, or out-of-scope)

**Works on**: Firefox Desktop + Firefox for Android (both support WebExtension Manifest V2)

### 3. Home Assistant (`homeassistant/`)

**Files**:
- `automations.yaml` — Bermuda-triggered automations (e.g., phone in bedroom → force block)
- `rest_commands.yaml` — REST command definitions for calling the backend API

## Configuration

### `backend/config.yaml`

```yaml
api:
  host: "0.0.0.0"
  port: 8800

anthropic:
  api_key: "sk-ant-..." # GITIGNORED — set in file or env var ANTHROPIC_API_KEY
  model: "claude-sonnet-4-20250514"
  max_tokens: 500
  temperature: 0.2

homeassistant:
  url: "http://192.168.22.1:8123"
  token: "..." # Long-lived access token — GITIGNORED

dnsmasq:
  blocked_hosts_path: "/etc/dnsmasq.d/blocked_hosts"
  # SIGHUP is sent to dnsmasq after modifying blocked_hosts

domains:
  conditional: # Blocked by default, can be bargained for
    - reddit.com
    - www.reddit.com
    - youtube.com
    - www.youtube.com
    - inv.nadeko.net
    - yewtu.be
    - invidious.nerdvpn.de
  always_blocked: [] # No bargaining possible

schedule:
  relax_windows:
    weekday: {start: "20:00", end: "23:00"}
    weekend: {start: "15:00", end: "23:00"}
  relax_rooms:
    - living_room

database:
  path: "/home/pays0n/productivity-guard/requests.db"
```

### LLM Prompt Strategy

The system prompt (`system_prompt.txt`) is written by "sober you" and encodes:

1. **Default DENY** — the LLM must be convinced, not the other way around
2. **Concrete examples** of valid/invalid reasons with expected outcomes
3. **Context injection** — at runtime, the backend injects: current time, day of week, device room location, number of requests today, last 5 requests with reasons/outcomes
4. **Escalating resistance** — more requests today = stricter evaluation
5. **URL coherence** — reason must match the actual URL content
6. **Duration specificity** — "watch this 12-min video" gets exactly 12 minutes, not 30
7. **Relax rules** — "relax" is valid only during configured windows + valid rooms
8. **Anti-manipulation** — low temperature, explicit instruction to not be swayed by emotional appeals or urgency framing

## Setup & Deployment

### Prerequisites

- Raspberry Pi already running as router (hostapd + dnsmasq + iptables)
- Home Assistant Docker container running with Bermuda integration
- Python 3.11+ on the Pi
- Anthropic API key
- Home Assistant long-lived access token

### Installation

```bash
# Clone to Pi
cd /home/pays0n
git clone <repo> productivity-guard
cd productivity-guard

# Run setup
chmod +x setup.sh
./setup.sh
```

The setup script:
1. Installs Python dependencies
2. Adds `addn-hosts=/etc/dnsmasq.d/blocked_hosts` to dnsmasq config
3. Creates initial blocked_hosts file
4. Adds iptables rule for port 8800
5. Creates sudoers entry for the backend (limited to hosts file + SIGHUP)
6. Installs and enables the systemd service
7. Restarts dnsmasq

### Firefox Extension Installation

**Desktop**: `about:debugging` → Load Temporary Add-on → select `extension/manifest.json`
(For permanent install: package as `.xpi` and self-sign, or use `about:config` → `xpinstall.signatures.required` = `false`)

**Android**: Use `web-ext` tool to side-load, or set up Firefox for Android extension development.

## Development

### Running Backend Locally (for testing)

```bash
cd backend
pip install -r requirements.txt
# Set env vars or edit config.yaml
uvicorn main:app --host 0.0.0.0 --port 8800 --reload
```

### Testing with curl

```bash
# Request access
curl -X POST http://192.168.22.1:8800/request-access \
  -H "Content-Type: application/json" \
  -d '{"url": "https://reddit.com/r/esp32/some-thread", "reason": "debugging BLE scanning issue", "device_ip": "192.168.22.50"}'

# Check status
curl http://192.168.22.1:8800/status

# View history
curl http://192.168.22.1:8800/history

# Force re-block
curl -X POST http://192.168.22.1:8800/revoke/reddit.com
```

### Project Structure

```
productivity-guard/
├── README.md                  # This file
├── ARCHITECTURE.md            # Detailed technical decisions and flows
├── setup.sh                   # One-shot installation script
├── .gitignore
├── backend/
│   ├── main.py                # FastAPI application
│   ├── blocklist.py           # dnsmasq blocked_hosts manager
│   ├── llm_gatekeeper.py      # Claude API integration
│   ├── ha_client.py           # Home Assistant API client
│   ├── models.py              # Pydantic request/response models
│   ├── database.py            # SQLite request history
│   ├── config.yaml            # Configuration (CONTAINS SECRETS — gitignored)
│   ├── config.example.yaml    # Example config (committed)
│   ├── system_prompt.txt      # LLM system prompt
│   ├── requirements.txt       # Python dependencies
│   └── productivity-guard.service  # systemd unit
├── extension/
│   ├── manifest.json          # Firefox WebExtension manifest (V2)
│   ├── background.js          # Request interceptor + scope manager
│   ├── popup.html             # "Why do you need this?" dialog
│   ├── popup.js               # Popup logic
│   ├── blocked.html           # "Access denied" page
│   ├── blocked.js             # Blocked page logic
│   ├── options.html           # Extension settings
│   └── options.js             # Settings logic
└── homeassistant/
    ├── automations.yaml       # Bermuda room-based automations
    └── rest_commands.yaml     # REST commands for backend API
```

## Security Notes

- The backend runs on the local network only (192.168.22.0/24). No internet exposure.
- API keys are in `config.yaml` which is gitignored.
- The backend has limited sudo: only write to `/etc/dnsmasq.d/blocked_hosts` and send SIGHUP to dnsmasq.
- The extension communicates with the backend over plain HTTP (acceptable on local network).
- The DNS blocklist is the hard floor — disabling the extension means you're MORE blocked, not less.
- To truly bypass, you'd need SSH access to the Pi. If you find yourself doing that, the system is working as intended (the friction is the point).
