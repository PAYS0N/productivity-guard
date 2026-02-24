"""Manages the dnsmasq blocked_hosts file for DNS-level domain blocking.

This module handles:
- Writing/removing domains from /etc/dnsmasq.d/blocked_hosts
- Sending SIGHUP to dnsmasq to reload the hosts file (no restart needed)
- Scheduling re-blocking after temporary unblock durations expire
- Tracking which domains are temporarily unblocked for which devices
"""

import asyncio
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

HOSTS_HEADER = "# Managed by Productivity Guard — do not edit manually\n"


class ActiveUnblock:
    """Tracks a temporarily unblocked domain."""

    def __init__(
        self,
        domain: str,
        device_ip: str,
        device_name: Optional[str],
        scope: Optional[str],
        reason: str,
        duration_minutes: int,
    ):
        self.domain = domain
        self.device_ip = device_ip
        self.device_name = device_name
        self.scope = scope
        self.reason = reason
        self.unblocked_at = datetime.now()
        self.expires_at = self.unblocked_at + timedelta(minutes=duration_minutes)
        self.timer_task: Optional[asyncio.Task] = None


class BlocklistManager:
    def __init__(
        self,
        blocked_hosts_path: str,
        conditional_domains: list[str],
        always_blocked_domains: list[str],
        on_reblock_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        self.blocked_hosts_path = Path(blocked_hosts_path)
        self.conditional_domains = set(conditional_domains)
        self.always_blocked_domains = set(always_blocked_domains)
        self.all_blocked_domains = self.conditional_domains | self.always_blocked_domains
        self.active_unblocks: dict[str, ActiveUnblock] = {}  # domain -> ActiveUnblock
        self.on_reblock_callback = on_reblock_callback

    async def initialize(self):
        """Write the full blocklist and signal dnsmasq. Called on startup."""
        await self._write_blocklist()
        self._signal_dnsmasq()
        logger.info(
            "Blocklist initialized with %d domains", len(self.all_blocked_domains)
        )

    async def unblock_domain(
        self,
        domain: str,
        device_ip: str,
        device_name: Optional[str],
        scope: Optional[str],
        reason: str,
        duration_minutes: int,
    ) -> bool:
        """Temporarily unblock a domain. Returns True if successful."""
        if domain in self.always_blocked_domains:
            logger.warning("Attempted to unblock always-blocked domain: %s", domain)
            return False

        if domain not in self.conditional_domains:
            logger.warning("Attempted to unblock unknown domain: %s", domain)
            return False

        # If already unblocked, cancel the existing timer and extend
        if domain in self.active_unblocks:
            existing = self.active_unblocks[domain]
            if existing.timer_task:
                existing.timer_task.cancel()
            logger.info("Extending unblock for %s (was for %s)", domain, existing.device_ip)

        # Also unblock www variant if the base domain was requested, and vice versa
        related_domains = self._get_related_domains(domain)
        domains_to_unblock = {domain} | related_domains

        unblock = ActiveUnblock(
            domain=domain,
            device_ip=device_ip,
            device_name=device_name,
            scope=scope,
            reason=reason,
            duration_minutes=duration_minutes,
        )

        # Track all related domains under the same unblock
        for d in domains_to_unblock:
            self.active_unblocks[d] = unblock

        # Rewrite the blocklist without the unblocked domains
        await self._write_blocklist()
        self._signal_dnsmasq()

        # Schedule re-block
        unblock.timer_task = asyncio.create_task(
            self._reblock_after(domains_to_unblock, duration_minutes)
        )

        logger.info(
            "Unblocked %s for %s (%s) — %d minutes, scope: %s",
            domains_to_unblock, device_ip, device_name, duration_minutes, scope,
        )
        return True

    async def reblock_domain(self, domain: str):
        """Immediately re-block a domain."""
        related_domains = self._get_related_domains(domain)
        domains_to_reblock = {domain} | related_domains

        for d in list(domains_to_reblock):
            if d in self.active_unblocks:
                unblock = self.active_unblocks.pop(d)
                if unblock.timer_task:
                    unblock.timer_task.cancel()

        await self._write_blocklist()
        self._signal_dnsmasq()
        logger.info("Re-blocked domains: %s", domains_to_reblock)

    async def reblock_all(self):
        """Re-block all domains. Cancel all timers."""
        for domain, unblock in self.active_unblocks.items():
            if unblock.timer_task:
                unblock.timer_task.cancel()
        self.active_unblocks.clear()
        await self._write_blocklist()
        self._signal_dnsmasq()
        logger.info("Re-blocked all domains")

    def get_active_unblocks(self) -> list[ActiveUnblock]:
        """Return list of currently unblocked domains (deduplicated by base domain)."""
        seen = set()
        result = []
        for domain, unblock in self.active_unblocks.items():
            if unblock.domain not in seen:
                seen.add(unblock.domain)
                result.append(unblock)
        return result

    def is_domain_unblocked(self, domain: str) -> bool:
        return domain in self.active_unblocks

    def _get_related_domains(self, domain: str) -> set[str]:
        """Get www/non-www variants that are also in our domain lists."""
        related = set()
        if domain.startswith("www."):
            base = domain[4:]
            if base in self.all_blocked_domains:
                related.add(base)
        else:
            www = f"www.{domain}"
            if www in self.all_blocked_domains:
                related.add(www)
        return related

    async def _write_blocklist(self):
        """Write the blocked_hosts file with all domains EXCEPT currently unblocked ones."""
        unblocked = set(self.active_unblocks.keys())
        blocked = self.all_blocked_domains - unblocked

        lines = [HOSTS_HEADER]
        lines.append(f"# Updated: {datetime.now().isoformat()}\n")
        for domain in sorted(blocked):
            lines.append(f"0.0.0.0 {domain}\n")

        content = "".join(lines)

        # Write via sudo tee
        try:
            proc = subprocess.run(
                ["sudo", "tee", str(self.blocked_hosts_path)],
                input=content.encode(),
                capture_output=True,
                timeout=5,
            )
            if proc.returncode != 0:
                logger.error(
                    "Failed to write blocklist: %s", proc.stderr.decode()
                )
        except subprocess.TimeoutExpired:
            logger.error("Timeout writing blocklist")

    def _signal_dnsmasq(self):
        """Send SIGHUP to dnsmasq to reload hosts files."""
        try:
            proc = subprocess.run(
                ["sudo", "pkill", "-HUP", "dnsmasq"],
                capture_output=True,
                timeout=5,
            )
            if proc.returncode != 0:
                logger.error(
                    "Failed to signal dnsmasq: %s", proc.stderr.decode()
                )
            else:
                logger.debug("Sent SIGHUP to dnsmasq")
        except subprocess.TimeoutExpired:
            logger.error("Timeout signaling dnsmasq")

    async def _reblock_after(self, domains: set[str], minutes: int):
        """Wait for the duration, then re-block the domains."""
        try:
            await asyncio.sleep(minutes * 60)
            for d in domains:
                self.active_unblocks.pop(d, None)
            await self._write_blocklist()
            self._signal_dnsmasq()
            logger.info("Auto re-blocked after %d minutes: %s", minutes, domains)
            if self.on_reblock_callback:
                for d in domains:
                    await self.on_reblock_callback(d)
        except asyncio.CancelledError:
            # Timer was cancelled (domain was manually re-blocked or extended)
            pass
