"""SQLite database for request history logging."""

import aiosqlite
from datetime import datetime, date
from typing import Optional
from pathlib import Path


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                device_ip TEXT NOT NULL,
                device_name TEXT,
                url TEXT NOT NULL,
                domain TEXT NOT NULL,
                reason TEXT NOT NULL,
                room TEXT,
                approved INTEGER NOT NULL,
                scope TEXT,
                duration_minutes INTEGER,
                llm_message TEXT,
                request_number_today INTEGER
            )
        """)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    async def log_request(
        self,
        device_ip: str,
        device_name: Optional[str],
        url: str,
        domain: str,
        reason: str,
        room: Optional[str],
        approved: bool,
        scope: Optional[str],
        duration_minutes: Optional[int],
        llm_message: Optional[str],
        request_number_today: int,
    ) -> int:
        cursor = await self._db.execute(
            """
            INSERT INTO requests
                (timestamp, device_ip, device_name, url, domain, reason, room,
                 approved, scope, duration_minutes, llm_message, request_number_today)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                device_ip,
                device_name,
                url,
                domain,
                reason,
                room,
                1 if approved else 0,
                scope,
                duration_minutes,
                llm_message,
                request_number_today,
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_today_count(self, device_ip: Optional[str] = None) -> int:
        today_str = date.today().isoformat()
        if device_ip:
            cursor = await self._db.execute(
                "SELECT COUNT(*) FROM requests WHERE timestamp LIKE ? AND device_ip = ?",
                (f"{today_str}%", device_ip),
            )
        else:
            cursor = await self._db.execute(
                "SELECT COUNT(*) FROM requests WHERE timestamp LIKE ?",
                (f"{today_str}%",),
            )
        row = await cursor.fetchone()
        return row[0]

    async def get_recent_requests(self, limit: int = 5, device_ip: Optional[str] = None) -> list[dict]:
        if device_ip:
            cursor = await self._db.execute(
                "SELECT * FROM requests WHERE device_ip = ? ORDER BY id DESC LIMIT ?",
                (device_ip, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM requests ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_today_history(self) -> list[dict]:
        today_str = date.today().isoformat()
        cursor = await self._db.execute(
            "SELECT * FROM requests WHERE timestamp LIKE ? ORDER BY id DESC",
            (f"{today_str}%",),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
