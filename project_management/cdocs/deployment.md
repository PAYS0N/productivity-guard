---
sources:
  - prod-guard/backend/productivity-guard.service
  - prod-guard/setup.sh
  - prod-guard/setup_doh_block.sh
---

# Deployment

## Network topology

| Component | Address |
|-----------|---------|
| Pi (`kuudra`) — router/gateway | `192.168.22.1` |
| WiFi (`wlan0`) — SSID "Payson" | hostapd, DHCP `.100–.200` |
| Internet uplink | `eth0`, NAT via iptables |
| Home Assistant (Docker) | `172.19.0.10`, published `:8123` |
| Backend API | `:8800` on the Pi |

Key device IPs: voidgloom (laptop) `192.168.22.50`, payson_s25 (phone) `192.168.22.75`.

## setup.sh

Run once as `pays0n` on the Pi. Steps:
1. Create Python venv at `./venv`, install `backend/requirements.txt`
2. Add `addn-hosts=<blocked_hosts>` to `/etc/dnsmasq.d/router.conf` if absent
3. Add `local-ttl=5` to dnsmasq config (short TTL so blocked responses expire quickly client-side)
4. Run `setup_doh_block.sh`
5. Create `/etc/productivity-guard/blocked_hosts` with header only
6. Add iptables rule to accept TCP `:8800` from `192.168.22.0/24` on `wlan0`
7. Add sudoers entry: `pays0n ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/dnsmasq.d/blocked_hosts` and `NOPASSWD: /usr/bin/pkill -HUP dnsmasq`
8. Install and enable `productivity-guard.service` via systemd
9. Copy `config.example.yaml` → `config.yaml` if absent

## setup_doh_block.sh

Creates `/etc/dnsmasq.d/doh_block.conf` — static file (not managed by the backend). Two mechanisms:
1. **Canary domain**: `address=/use-application-dns.net/` → NXDOMAIN; Firefox's official DoH opt-out hook disables DoH automatically
2. **DoH provider hostnames**: `address=/cloudflare-dns.com/0.0.0.0`, same for `dns.google`, `mozilla.cloudflare-dns.com`, `doh.opendns.com`, etc. Blocks bootstrap DNS resolution for DoH endpoints

## systemd service (`productivity-guard.service`)

Runs as `User=pays0n`. `ExecStart` calls uvicorn via the venv interpreter. `Restart=on-failure`, `RestartSec=5`. Environment file at `/etc/productivity-guard/env` for secrets (API key, HA token).

## Config file (`config.yaml`)

Required fields: `anthropic.api_key`, `anthropic.model`, `anthropic.max_tokens`, `anthropic.temperature`, `homeassistant.url`, `homeassistant.token`, `database.path`, `dnsmasq.blocked_hosts_path`, `domains.conditional` (list), `domains.always_blocked` (list), `api.host`, `api.port`, `devices` (map of IP → name/type/bermuda_entity).

Secrets can be overridden via env vars: `ANTHROPIC_API_KEY`, `HA_TOKEN`.
