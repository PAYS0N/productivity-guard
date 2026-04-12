"""Unit tests for BlocklistManager.

subprocess.run is mocked throughout to avoid actual file writes and dnsmasq signals.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, call, patch

from blocklist import BlocklistManager, ActiveUnblock


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_manager(
    conditional=None,
    always_blocked=None,
    path="/fake/blocked_hosts",
    callback=None,
):
    return BlocklistManager(
        blocked_hosts_path=path,
        conditional_domains=conditional or ["reddit.com", "www.reddit.com", "youtube.com"],
        always_blocked_domains=always_blocked or ["twitter.com"],
        on_reblock_callback=callback,
    )


@pytest.fixture
def mock_subprocess(mocker):
    """Patch subprocess.run so no files are written and no dnsmasq is signaled."""
    mock = mocker.patch("blocklist.subprocess.run")
    mock.return_value = MagicMock(returncode=0, stderr=b"")
    return mock


@pytest.fixture
async def manager(mock_subprocess):
    """A fresh BlocklistManager with subprocess mocked."""
    mgr = make_manager()
    yield mgr
    # Cancel all lingering timer tasks to avoid asyncio warnings
    for unblock in mgr.active_unblocks.values():
        if unblock.timer_task and not unblock.timer_task.done():
            unblock.timer_task.cancel()
    await asyncio.sleep(0)


# ── Constructor ───────────────────────────────────────────────────────────────


class TestInit:
    def test_all_blocked_domains_is_union(self):
        mgr = make_manager(
            conditional=["reddit.com"],
            always_blocked=["twitter.com"],
        )
        assert mgr.all_blocked_domains == {"reddit.com", "twitter.com"}

    def test_overlapping_domains_handled_by_set_union(self):
        mgr = make_manager(
            conditional=["reddit.com", "twitter.com"],
            always_blocked=["twitter.com"],
        )
        assert "twitter.com" in mgr.all_blocked_domains
        assert len([d for d in mgr.all_blocked_domains if d == "twitter.com"]) == 1

    def test_active_unblocks_starts_empty(self):
        mgr = make_manager()
        assert mgr.active_unblocks == {}


# ── initialize ────────────────────────────────────────────────────────────────


class TestInitialize:
    async def test_writes_blocklist_and_signals_dnsmasq(self, mock_subprocess):
        mgr = make_manager()
        await mgr.initialize()
        # Two subprocess calls: one for `sudo tee` (write), one for `sudo pkill -HUP dnsmasq`
        assert mock_subprocess.call_count == 2

    async def test_initial_blocklist_contains_all_domains(self, mock_subprocess):
        mgr = make_manager(
            conditional=["reddit.com"],
            always_blocked=["twitter.com"],
        )
        await mgr.initialize()
        # Grab the content written to the file (first call, input kwarg)
        content = mock_subprocess.call_args_list[0].kwargs["input"].decode()
        assert "reddit.com" in content
        assert "twitter.com" in content


# ── unblock_domain ────────────────────────────────────────────────────────────


class TestUnblockDomain:
    async def test_returns_true_for_valid_domain(self, manager):
        result = await manager.unblock_domain(
            domain="reddit.com",
            device_ip="192.168.1.1",
            device_name="laptop",
            scope="/*",
            reason="work",
            duration_minutes=10,
        )
        assert result is True

    async def test_domain_added_to_active_unblocks(self, manager):
        await manager.unblock_domain(
            domain="reddit.com",
            device_ip="192.168.1.1",
            device_name="laptop",
            scope="/*",
            reason="work",
            duration_minutes=10,
        )
        assert "reddit.com" in manager.active_unblocks

    async def test_www_variant_also_tracked(self, manager):
        """When reddit.com is unblocked, www.reddit.com (its www variant) is also tracked."""
        await manager.unblock_domain(
            domain="reddit.com",
            device_ip="192.168.1.1",
            device_name="laptop",
            scope="/*",
            reason="work",
            duration_minutes=10,
        )
        assert "www.reddit.com" in manager.active_unblocks

    async def test_always_blocked_domain_returns_false(self, manager):
        result = await manager.unblock_domain(
            domain="twitter.com",
            device_ip="192.168.1.1",
            device_name="laptop",
            scope="/*",
            reason="checking DMs",
            duration_minutes=5,
        )
        assert result is False
        assert "twitter.com" not in manager.active_unblocks

    async def test_unknown_domain_returns_false(self, manager):
        result = await manager.unblock_domain(
            domain="facebook.com",
            device_ip="192.168.1.1",
            device_name="laptop",
            scope="/*",
            reason="work",
            duration_minutes=5,
        )
        assert result is False

    async def test_timer_task_created(self, manager):
        await manager.unblock_domain(
            domain="reddit.com",
            device_ip="192.168.1.1",
            device_name="laptop",
            scope="/*",
            reason="work",
            duration_minutes=10,
        )
        task = manager.active_unblocks["reddit.com"].timer_task
        assert task is not None
        assert isinstance(task, asyncio.Task)

    async def test_extending_unblock_creates_new_timer(self, mock_subprocess):
        """Second unblock of the same domain creates a new timer task."""
        mgr = make_manager()
        await mgr.unblock_domain(
            domain="reddit.com", device_ip="1.1.1.1", device_name="dev",
            scope="/*", reason="first", duration_minutes=10,
        )
        first_task = mgr.active_unblocks["reddit.com"].timer_task

        await mgr.unblock_domain(
            domain="reddit.com", device_ip="1.1.1.1", device_name="dev",
            scope="/*", reason="extended", duration_minutes=5,
        )
        second_task = mgr.active_unblocks["reddit.com"].timer_task

        assert second_task is not first_task

        # Cancel both tasks to avoid asyncio warnings
        first_task.cancel()
        second_task.cancel()
        await asyncio.sleep(0)

    async def test_unblock_removes_domain_from_written_blocklist(self, mock_subprocess):
        """After unblocking, the domain should not appear in the written hosts file."""
        mgr = make_manager(
            conditional=["reddit.com", "youtube.com"],
            always_blocked=[],
        )
        await mgr.unblock_domain(
            domain="reddit.com", device_ip="1.1.1.1", device_name="dev",
            scope="/*", reason="work", duration_minutes=10,
        )
        # Get the most recent write call's content
        write_calls = [
            c for c in mock_subprocess.call_args_list
            if "tee" in c.args[0]
        ]
        content = write_calls[-1].kwargs["input"].decode()
        assert "reddit.com" not in content
        assert "youtube.com" in content

        # Cleanup
        for unblock in mgr.active_unblocks.values():
            if unblock.timer_task:
                unblock.timer_task.cancel()
        await asyncio.sleep(0)


# ── reblock_domain ────────────────────────────────────────────────────────────


class TestReblockDomain:
    async def test_removes_domain_from_active_unblocks(self, mock_subprocess):
        mgr = make_manager()
        await mgr.unblock_domain(
            domain="reddit.com", device_ip="1.1.1.1", device_name="dev",
            scope="/*", reason="work", duration_minutes=10,
        )
        assert "reddit.com" in mgr.active_unblocks

        await mgr.reblock_domain("reddit.com")
        assert "reddit.com" not in mgr.active_unblocks

    async def test_also_removes_www_variant(self, mock_subprocess):
        mgr = make_manager()
        await mgr.unblock_domain(
            domain="reddit.com", device_ip="1.1.1.1", device_name="dev",
            scope="/*", reason="work", duration_minutes=10,
        )
        assert "www.reddit.com" in mgr.active_unblocks

        await mgr.reblock_domain("reddit.com")
        assert "www.reddit.com" not in mgr.active_unblocks

    async def test_reblock_signals_dnsmasq(self, mock_subprocess):
        mgr = make_manager()
        await mgr.unblock_domain(
            domain="reddit.com", device_ip="1.1.1.1", device_name="dev",
            scope="/*", reason="work", duration_minutes=10,
        )
        call_count_before = mock_subprocess.call_count
        await mgr.reblock_domain("reddit.com")
        assert mock_subprocess.call_count > call_count_before

    async def test_reblock_nonexistent_domain_is_noop(self, manager):
        """Reblocking a domain not in active_unblocks should not raise."""
        await manager.reblock_domain("notblocked.com")  # should not raise


# ── reblock_all ───────────────────────────────────────────────────────────────


class TestReblockAll:
    async def test_clears_all_active_unblocks(self, mock_subprocess):
        mgr = make_manager()
        await mgr.unblock_domain(
            domain="reddit.com", device_ip="1.1.1.1", device_name="dev",
            scope="/*", reason="work", duration_minutes=10,
        )
        await mgr.unblock_domain(
            domain="youtube.com", device_ip="1.1.1.1", device_name="dev",
            scope="/*", reason="music", duration_minutes=5,
        )
        assert len(mgr.active_unblocks) > 0

        await mgr.reblock_all()
        assert mgr.active_unblocks == {}

    async def test_signals_dnsmasq_after_reblock_all(self, mock_subprocess):
        mgr = make_manager()
        initial_calls = mock_subprocess.call_count
        await mgr.reblock_all()
        assert mock_subprocess.call_count > initial_calls


# ── get_active_unblocks ────────────────────────────────────────────────────────


class TestGetActiveUnblocks:
    async def test_returns_empty_when_nothing_unblocked(self, manager):
        result = manager.get_active_unblocks()
        assert result == []

    async def test_deduplicates_by_base_domain(self, mock_subprocess):
        """reddit.com and www.reddit.com share the same ActiveUnblock — only one entry."""
        mgr = make_manager()
        await mgr.unblock_domain(
            domain="reddit.com", device_ip="1.1.1.1", device_name="dev",
            scope="/*", reason="work", duration_minutes=10,
        )
        # Both reddit.com and www.reddit.com are in active_unblocks
        assert "reddit.com" in mgr.active_unblocks
        assert "www.reddit.com" in mgr.active_unblocks

        result = mgr.get_active_unblocks()
        # But get_active_unblocks deduplicates by unblock.domain (== "reddit.com")
        assert len(result) == 1
        assert result[0].domain == "reddit.com"

        for u in mgr.active_unblocks.values():
            if u.timer_task:
                u.timer_task.cancel()
        await asyncio.sleep(0)

    async def test_returns_correct_device_info(self, mock_subprocess):
        mgr = make_manager()
        await mgr.unblock_domain(
            domain="youtube.com", device_ip="192.168.1.50", device_name="my-phone",
            scope="/watch*", reason="music", duration_minutes=30,
        )
        result = mgr.get_active_unblocks()
        assert len(result) == 1
        assert result[0].device_ip == "192.168.1.50"
        assert result[0].device_name == "my-phone"
        assert result[0].scope == "/watch*"

        for u in mgr.active_unblocks.values():
            if u.timer_task:
                u.timer_task.cancel()
        await asyncio.sleep(0)


# ── _get_related_domains ──────────────────────────────────────────────────────


class TestGetRelatedDomains:
    def test_bare_domain_finds_www_variant(self):
        mgr = make_manager(conditional=["reddit.com", "www.reddit.com"])
        related = mgr._get_related_domains("reddit.com")
        assert related == {"www.reddit.com"}

    def test_www_domain_finds_bare_variant(self):
        mgr = make_manager(conditional=["reddit.com", "www.reddit.com"])
        related = mgr._get_related_domains("www.reddit.com")
        assert related == {"reddit.com"}

    def test_domain_with_no_www_variant_in_list(self):
        mgr = make_manager(conditional=["youtube.com"])  # no www.youtube.com
        related = mgr._get_related_domains("youtube.com")
        assert related == set()

    def test_always_blocked_variant_found(self):
        mgr = make_manager(
            conditional=[],
            always_blocked=["evil.com", "www.evil.com"],
        )
        related = mgr._get_related_domains("evil.com")
        assert related == {"www.evil.com"}


# ── _write_blocklist content ──────────────────────────────────────────────────


class TestWriteBlocklistContent:
    async def test_header_present(self, mock_subprocess):
        mgr = make_manager(conditional=["reddit.com"], always_blocked=[])
        await mgr._write_blocklist()
        # _write_blocklist makes exactly 1 subprocess call (sudo tee); index [0]
        content = mock_subprocess.call_args_list[0].kwargs["input"].decode()
        assert "Managed by Productivity Guard" in content

    async def test_blocked_domain_uses_null_ip(self, mock_subprocess):
        mgr = make_manager(conditional=["reddit.com"], always_blocked=[])
        await mgr._write_blocklist()
        content = mock_subprocess.call_args_list[0].kwargs["input"].decode()
        assert "0.0.0.0 reddit.com" in content

    async def test_active_unblocked_domain_absent(self, mock_subprocess):
        mgr = make_manager(conditional=["reddit.com", "youtube.com"], always_blocked=[])
        mgr.active_unblocks["reddit.com"] = MagicMock()
        await mgr._write_blocklist()
        content = mock_subprocess.call_args_list[0].kwargs["input"].decode()
        assert "reddit.com" not in content
        assert "youtube.com" in content

    async def test_always_blocked_always_present(self, mock_subprocess):
        mgr = make_manager(conditional=[], always_blocked=["badsite.com"])
        await mgr._write_blocklist()
        content = mock_subprocess.call_args_list[0].kwargs["input"].decode()
        assert "badsite.com" in content


# ── is_domain_unblocked ────────────────────────────────────────────────────────


class TestIsDomainUnblocked:
    def test_returns_false_when_not_unblocked(self, manager):
        assert manager.is_domain_unblocked("reddit.com") is False

    async def test_returns_true_after_unblock(self, mock_subprocess):
        mgr = make_manager()
        await mgr.unblock_domain(
            domain="reddit.com", device_ip="1.1.1.1", device_name="dev",
            scope="/*", reason="work", duration_minutes=10,
        )
        assert mgr.is_domain_unblocked("reddit.com") is True

        for u in mgr.active_unblocks.values():
            if u.timer_task:
                u.timer_task.cancel()
        await asyncio.sleep(0)
