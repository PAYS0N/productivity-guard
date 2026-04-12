"""Unit tests for Database using a real in-memory SQLite connection.

No mocking — these tests exercise the actual SQL logic.
"""

import pytest
from datetime import date, datetime

from database import Database


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def db():
    """Fresh in-memory database for each test."""
    d = Database(":memory:")
    await d.connect()
    yield d
    await d.close()


def _row_kwargs(**overrides):
    """Return a complete set of log_request kwargs with sensible defaults."""
    defaults = dict(
        device_ip="192.168.1.1",
        device_name="test-laptop",
        url="https://reddit.com/r/python",
        domain="reddit.com",
        reason="work research",
        room="office",
        approved=True,
        scope="/r/python/*",
        duration_minutes=15,
        llm_message="Approved for work",
        request_number_today=1,
    )
    defaults.update(overrides)
    return defaults


# ── connect / schema ──────────────────────────────────────────────────────────


class TestConnect:
    async def test_creates_requests_table(self, db):
        """The requests table must exist after connect()."""
        cursor = await db._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='requests'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "requests"

    async def test_idempotent_connect(self):
        """Calling connect twice (via CREATE TABLE IF NOT EXISTS) should not fail."""
        d = Database(":memory:")
        await d.connect()
        await d.connect()  # re-runs CREATE TABLE IF NOT EXISTS — should be fine
        await d.close()


# ── log_request ───────────────────────────────────────────────────────────────


class TestLogRequest:
    async def test_returns_integer_row_id(self, db):
        row_id = await db.log_request(**_row_kwargs())
        assert isinstance(row_id, int)
        assert row_id >= 1

    async def test_row_id_increments(self, db):
        id1 = await db.log_request(**_row_kwargs())
        id2 = await db.log_request(**_row_kwargs())
        assert id2 > id1

    async def test_approved_true_stored_as_1(self, db):
        await db.log_request(**_row_kwargs(approved=True))
        cursor = await db._db.execute("SELECT approved FROM requests LIMIT 1")
        row = await cursor.fetchone()
        assert row[0] == 1

    async def test_approved_false_stored_as_0(self, db):
        await db.log_request(**_row_kwargs(approved=False))
        cursor = await db._db.execute("SELECT approved FROM requests LIMIT 1")
        row = await cursor.fetchone()
        assert row[0] == 0

    async def test_nullable_fields_stored_as_none(self, db):
        await db.log_request(**_row_kwargs(
            device_name=None, room=None, scope=None,
            duration_minutes=None, llm_message=None,
        ))
        cursor = await db._db.execute(
            "SELECT device_name, room, scope, duration_minutes, llm_message FROM requests LIMIT 1"
        )
        row = await cursor.fetchone()
        assert row[0] is None  # device_name
        assert row[1] is None  # room
        assert row[2] is None  # scope

    async def test_all_fields_stored(self, db):
        await db.log_request(**_row_kwargs(
            device_ip="10.0.0.1",
            device_name="my-phone",
            url="https://youtube.com/watch?v=abc",
            domain="youtube.com",
            reason="background music",
            room="living_room",
            approved=True,
            scope="/watch*",
            duration_minutes=60,
            llm_message="Approved for music",
            request_number_today=3,
        ))
        cursor = await db._db.execute("SELECT * FROM requests LIMIT 1")
        row = dict(await cursor.fetchone())
        assert row["device_ip"] == "10.0.0.1"
        assert row["device_name"] == "my-phone"
        assert row["domain"] == "youtube.com"
        assert row["reason"] == "background music"
        assert row["room"] == "living_room"
        assert row["approved"] == 1
        assert row["scope"] == "/watch*"
        assert row["duration_minutes"] == 60
        assert row["request_number_today"] == 3


# ── get_today_count ───────────────────────────────────────────────────────────


class TestGetTodayCount:
    async def test_zero_when_no_rows(self, db):
        count = await db.get_today_count()
        assert count == 0

    async def test_counts_todays_rows(self, db):
        await db.log_request(**_row_kwargs())
        await db.log_request(**_row_kwargs())
        count = await db.get_today_count()
        assert count == 2

    async def test_filters_by_device_ip(self, db):
        await db.log_request(**_row_kwargs(device_ip="10.0.0.1"))
        await db.log_request(**_row_kwargs(device_ip="10.0.0.2"))
        await db.log_request(**_row_kwargs(device_ip="10.0.0.2"))

        count_1 = await db.get_today_count("10.0.0.1")
        count_2 = await db.get_today_count("10.0.0.2")
        assert count_1 == 1
        assert count_2 == 2

    async def test_does_not_count_other_days(self, db):
        # Insert a row with yesterday's timestamp directly
        yesterday = "2000-01-01T12:00:00"
        await db._db.execute(
            """INSERT INTO requests (timestamp, device_ip, device_name, url, domain,
               reason, room, approved, scope, duration_minutes, llm_message, request_number_today)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (yesterday, "1.1.1.1", "dev", "https://reddit.com", "reddit.com",
             "test", None, 1, None, None, None, 1),
        )
        await db._db.commit()
        count = await db.get_today_count()
        assert count == 0  # yesterday's row should not be counted


# ── get_recent_requests ───────────────────────────────────────────────────────


class TestGetRecentRequests:
    async def test_returns_empty_when_no_rows(self, db):
        result = await db.get_recent_requests()
        assert result == []

    async def test_returns_list_of_dicts(self, db):
        await db.log_request(**_row_kwargs())
        result = await db.get_recent_requests()
        assert isinstance(result, list)
        assert isinstance(result[0], dict)

    async def test_respects_limit(self, db):
        for i in range(10):
            await db.log_request(**_row_kwargs(reason=f"request {i}"))
        result = await db.get_recent_requests(limit=3)
        assert len(result) == 3

    async def test_ordered_newest_first(self, db):
        for i in range(5):
            await db.log_request(**_row_kwargs(reason=f"request {i}"))
        result = await db.get_recent_requests(limit=5)
        ids = [r["id"] for r in result]
        assert ids == sorted(ids, reverse=True)

    async def test_filters_by_device_ip(self, db):
        await db.log_request(**_row_kwargs(device_ip="1.1.1.1"))
        await db.log_request(**_row_kwargs(device_ip="2.2.2.2"))
        await db.log_request(**_row_kwargs(device_ip="1.1.1.1"))

        result = await db.get_recent_requests(device_ip="1.1.1.1")
        assert len(result) == 2
        for row in result:
            assert row["device_ip"] == "1.1.1.1"

    async def test_returns_all_when_under_limit(self, db):
        await db.log_request(**_row_kwargs())
        await db.log_request(**_row_kwargs())
        result = await db.get_recent_requests(limit=10)
        assert len(result) == 2


# ── get_today_history ──────────────────────────────────────────────────────────


class TestGetTodayHistory:
    async def test_returns_empty_when_no_rows(self, db):
        result = await db.get_today_history()
        assert result == []

    async def test_returns_todays_rows(self, db):
        await db.log_request(**_row_kwargs())
        result = await db.get_today_history()
        assert len(result) == 1

    async def test_excludes_other_days(self, db):
        # Insert yesterday's row manually
        yesterday = "2000-01-01T12:00:00"
        await db._db.execute(
            """INSERT INTO requests (timestamp, device_ip, device_name, url, domain,
               reason, room, approved, scope, duration_minutes, llm_message, request_number_today)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (yesterday, "1.1.1.1", "dev", "https://reddit.com", "reddit.com",
             "old request", None, 0, None, None, None, 1),
        )
        await db._db.commit()
        # Add today's row
        await db.log_request(**_row_kwargs())

        result = await db.get_today_history()
        assert len(result) == 1
        assert result[0]["reason"] == "work research"  # only today's row

    async def test_ordered_newest_first(self, db):
        for i in range(3):
            await db.log_request(**_row_kwargs(reason=f"req {i}"))
        result = await db.get_today_history()
        ids = [r["id"] for r in result]
        assert ids == sorted(ids, reverse=True)
