---
sources:
  - prod-guard/Dockerfile
  - prod-guard/docker-compose.yml
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

## Docker setup

The backend runs as a single Docker Compose service (`prod-guard/`). Bridge networking with `ports: 8800:8800`. Secrets (`ANTHROPIC_API_KEY`, `HA_TOKEN`) are required via `.env`. Two bind-mounts: `/etc/productivity-guard/` (rw, for blocklist writes) and `./backend/config.yaml` (ro). SQLite DB persists in named volume `pg-data` at `/data/requests.db` inside the container.

An iptables rule in `DOCKER-USER` allows the container bridge to reach `eth0` (internet):
```
-I DOCKER-USER 1 -i br-xxxx -o eth0 -j ACCEPT
```
Return traffic is covered by the existing `RELATED,ESTABLISHED` rule in `FORWARD`.

## setup.sh

Run once as `pays0n` on the Pi. Steps:
1. Swap dnsmasq `addn-hosts` → `hostsdir=/etc/productivity-guard/` (inotify-based auto-reload; no SIGHUP needed)
2. Add `local-ttl=5` to dnsmasq config
3. Run `setup_doh_block.sh`
4. Create `/etc/productivity-guard/blocked_hosts` with initial entries
5. Add iptables rule to accept TCP `:8800` from `192.168.22.0/24` on `wlan0`
6. Install Docker and Docker Compose if absent
7. Create `.env` from `.env.example` if absent (warn to fill in secrets)
8. Migrate existing SQLite DB from legacy path into `pg-data` volume if found
9. Copy `config.example.yaml` → `config.yaml` if absent
10. Start backend with `docker compose up -d --build`

## setup_doh_block.sh

Creates `/etc/dnsmasq.d/doh_block.conf` — static file (not managed by the backend). Two mechanisms:
1. **Canary domain**: `address=/use-application-dns.net/` → NXDOMAIN; Firefox's official DoH opt-out hook disables DoH automatically
2. **DoH provider hostnames**: `address=/cloudflare-dns.com/0.0.0.0`, same for `dns.google`, `mozilla.cloudflare-dns.com`, `doh.opendns.com`, etc.

## Config file (`config.yaml`)

Required fields: `anthropic.model`, `anthropic.max_tokens`, `anthropic.temperature`, `homeassistant.url`, `database.path`, `dnsmasq.blocked_hosts_path`, `domains.conditional` (list), `domains.always_blocked` (list), `api.host`, `api.port`, `devices` (map of IP → name/type/bermuda_entity).

Secrets (`ANTHROPIC_API_KEY`, `HA_TOKEN`) are required as environment variables — not in `config.yaml`. The backend raises `RuntimeError` at startup if either is absent.
