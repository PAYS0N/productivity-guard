# Task: Migrate Backend to Docker

## Prerequisites

Read `project_management/manifest.md` before proceeding.

Then read:
- `project_management/cdocs/deployment.md`
- `project_management/cdocs/dns-blocklist.md`
- `project_management/cdocs/backend-api.md`
- `project_management/standards/architecture.md` (new files and module responsibility changes are involved)
- `project_management/standards/style.md`

## Context

The Pi (`kuudra`) is a router/gateway running hostapd, dnsmasq (DNS + DHCP), and iptables NAT as native system services. These must stay native — they are network infrastructure.

The productivity-guard FastAPI backend currently runs as a systemd service using a Python venv, with two sudoers entries that allow it to write the dnsmasq blocklist file and send SIGHUP to dnsmasq.

The goal is to run the backend in Docker instead, eliminating the systemd service, the venv, and both sudoers entries.

**dnsmasq must remain a native service.** Do not propose containerizing it.

## System design (pre-approved)

### dnsmasq reload mechanism change

The current `addn-hosts=/etc/productivity-guard/blocked_hosts` directive in `/etc/dnsmasq.d/router.conf` must be replaced with:

```
hostsdir=/etc/productivity-guard/
```

`hostsdir` causes dnsmasq to watch the directory with inotify and reload automatically when any hosts file in it changes. This eliminates the need for SIGHUP entirely.

### Backend container

- Single-service `docker-compose.yml` in `prod-guard/`
- Bind-mount `/etc/productivity-guard/` from the host into the container at the same path — the container writes directly to the file (no sudo needed)
- Secrets passed via env file (`.env`) — `ANTHROPIC_API_KEY`, `HA_TOKEN`
- `config.yaml` bind-mounted read-only into the container
- Port `8800` exposed to the LAN interface

### `blocklist.py` changes

- `_write_blocklist()`: replace `subprocess.run(["sudo", "tee", ...])` with a direct Python file write
- Remove the SIGHUP call (`pkill -HUP dnsmasq`) entirely — `hostsdir` handles reload automatically
- All other logic (unblock scheduling, domain sets, `active_unblocks`) stays unchanged

## Plan first

Present your full implementation plan before making any code changes. The plan must cover:

1. All new files to create (`Dockerfile`, `docker-compose.yml`, `.env.example`)
2. All files to modify (`blocklist.py`, `setup.sh`, `config.example.yaml`)
3. Files to delete or retire (e.g. `productivity-guard.service`)
4. The exact `hostsdir` change to `router.conf` (done manually by the user during setup — include it in the updated `setup.sh`)
5. Any `config.yaml` field changes needed

Wait for confirmation before writing any code.

## Constraints

- `dnsmasq.blocked_hosts_path` in `config.yaml` should remain `/etc/productivity-guard/blocked_hosts` — the bind mount makes the host path available at the same container-internal path
- The hosts file format must not change (dnsmasq still reads it)
- Do not change any endpoint behavior or API contracts
- Follow `project_management/standards/style.md` for all code

# Shutdown
- When implementation is complete (task description fully implemented), before waiting for user confirmation:

    1. Write a brief summary of what was done.
    2. List suggested test steps for the user to verify the work — make clear that running tests is the user's responsibility, not the agent's.
    3. Explicitly pause and wait for the user to confirm the task is done.

- Only after the user has confirmed the task is done, run scripts/shutdown.py.