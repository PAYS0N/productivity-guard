---
sources:
  - prod-guard/backend/ha_client.py
  - prod-guard/homeassistant/automations.yaml
  - prod-guard/homeassistant/rest_commands.yaml
---

# Home Assistant Integration

## Overview

Home Assistant runs in Docker on the Pi at `172.19.0.10`, published on `:8123`. The backend queries it for Bermuda BLE room tracking data. HA also calls back into the backend via automations to force-block devices.

## HAClient

Wraps an `httpx.AsyncClient` with a Bearer token. Initialized with `ha_url`, `token`, and `device_map` (from `config.yaml`). `connect()` creates the client and tests the connection; failure is a warning, not fatal.

**Methods:**
- `get_device_info(device_ip)` — returns the device config dict from `device_map`, or `None`
- `get_device_room(device_ip)` — looks up `bermuda_entity` from `device_map`, queries HA state, returns room string or `None`
- `get_entity_state(entity_id)` — public wrapper for arbitrary HA entity state queries
- `call_service(domain, service, data)` — calls an HA service, returns `True` on HTTP 200

Entity states of `"unknown"` or `"unavailable"` are returned as `None`.

## Device map (config.yaml)

```yaml
devices:
  "192.168.22.50":
    name: "voidgloom"
    type: "laptop"
    bermuda_entity: "sensor.voidgloom_ble_room"
  "192.168.22.75":
    name: "payson_s25"
    type: "phone"
    bermuda_entity: "sensor.payson_s25_ble_room"
```

`bermuda_entity` is optional. If absent, room context is `None` and room-based LLM rules are skipped.

## Bermuda BLE tracking

Bermuda is a HA integration that uses BLE RSSI from fixed ESP32 proxies to estimate which room a device is in. Entity state is a room name string (e.g. `"office"`, `"bedroom"`). The backend passes this room string directly to the LLM.

## HA automations

`homeassistant/automations.yaml` — two automations:
- **`pg_phone_bedroom_block`**: triggers when `sensor.payson_s25_ble_room` enters `"bedroom"` → calls `rest_command.productivity_guard_force_block` with `device_ip: "192.168.22.75"`
- **`pg_phone_bedroom_unblock`**: triggers when the same sensor leaves `"bedroom"` → calls `rest_command.productivity_guard_force_unblock`

A commented-out `pg_sleep_revoke` automation would call `revoke-all` at 23:00.

## HA REST commands

`homeassistant/rest_commands.yaml` — defines three `rest_command` entries for `configuration.yaml`:
- `productivity_guard_force_block` — POST `/force-block` with `{"device_ip": "{{ device_ip }}"}`
- `productivity_guard_force_unblock` — POST `/force-unblock` with `{"device_ip": "{{ device_ip }}"}`
- `productivity_guard_revoke_all` — POST `/revoke-all`

All target `http://192.168.22.1:8800` (Pi LAN IP).
