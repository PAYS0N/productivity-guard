---
sources:
  - prod-guard/backend/database.py
---

# Database

## Overview

`Database` wraps `aiosqlite` for async SQLite access. A single table `requests` stores all access request history. The DB file path is set in `config.yaml`; the parent directory is created on connect if it doesn't exist.

## Schema

```sql
CREATE TABLE IF NOT EXISTS requests (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp            TEXT NOT NULL,        -- ISO 8601 datetime string
    device_ip            TEXT NOT NULL,
    device_name          TEXT,
    url                  TEXT NOT NULL,
    domain               TEXT NOT NULL,
    reason               TEXT NOT NULL,
    room                 TEXT,                 -- Bermuda room, nullable
    approved             INTEGER NOT NULL,     -- 0 or 1
    scope                TEXT,                 -- approved path pattern, nullable
    duration_minutes     INTEGER,              -- nullable
    llm_message          TEXT,                 -- LLM explanation, nullable
    request_number_today INTEGER
)
```

`row_factory = aiosqlite.Row` so queries return dict-like rows.

## Methods

`connect()` — creates DB file/dirs, opens connection, creates table if absent. `close()` — closes connection.

`log_request(...)` — inserts a row; returns `lastrowid`.

`get_today_count(device_ip?)` — count of rows where `timestamp LIKE '<today>%'`, optionally filtered by `device_ip`.

`get_recent_requests(limit=5, device_ip?)` — last N rows ordered by `id DESC`, optionally filtered by device.

`get_today_history()` — all of today's rows ordered by `id DESC`; used by the `/history` endpoint.
