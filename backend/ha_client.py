"""Home Assistant REST API client for querying Bermuda room data and other entities."""

import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class HAClient:
    def __init__(self, ha_url: str, token: str, device_map: dict):
        """
        Args:
            ha_url: Base URL for HA (e.g., "http://192.168.22.1:8123")
            token: Long-lived access token
            device_map: Mapping of device_ip -> device config dict with keys:
                        name, type, bermuda_entity (optional)
        """
        self.ha_url = ha_url.rstrip("/")
        self.token = token
        self.device_map = device_map
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self):
        self._client = httpx.AsyncClient(
            base_url=self.ha_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        # Test connection
        try:
            resp = await self._client.get("/api/")
            resp.raise_for_status()
            logger.info("Connected to Home Assistant at %s", self.ha_url)
        except Exception as e:
            logger.warning("Could not connect to Home Assistant: %s", e)

    async def close(self):
        if self._client:
            await self._client.aclose()

    def get_device_info(self, device_ip: str) -> Optional[dict]:
        """Get device name and type from config."""
        return self.device_map.get(device_ip)

    async def get_device_room(self, device_ip: str) -> Optional[str]:
        """Query Bermuda for the device's current room.

        Returns the room name string, or None if unavailable.
        """
        device_info = self.device_map.get(device_ip)
        if not device_info:
            logger.debug("No device config for IP %s", device_ip)
            return None

        entity_id = device_info.get("bermuda_entity")
        if not entity_id:
            logger.debug("No Bermuda entity for device %s", device_ip)
            return None

        return await self._get_entity_state(entity_id)

    async def get_entity_state(self, entity_id: str) -> Optional[str]:
        """Public wrapper for getting any entity state."""
        return await self._get_entity_state(entity_id)

    async def _get_entity_state(self, entity_id: str) -> Optional[str]:
        """Query HA REST API for an entity's state value."""
        if not self._client:
            logger.warning("HA client not connected")
            return None

        try:
            resp = await self._client.get(f"/api/states/{entity_id}")
            if resp.status_code == 200:
                data = resp.json()
                state = data.get("state")
                if state and state not in ("unknown", "unavailable"):
                    return state
                return None
            elif resp.status_code == 404:
                logger.warning("Entity not found: %s", entity_id)
                return None
            else:
                logger.warning(
                    "HA API error for %s: %d %s",
                    entity_id, resp.status_code, resp.text,
                )
                return None
        except httpx.RequestError as e:
            logger.warning("HA request failed for %s: %s", entity_id, e)
            return None

    async def call_service(self, domain: str, service: str, data: dict) -> bool:
        """Call an HA service. Returns True on success."""
        if not self._client:
            logger.warning("HA client not connected")
            return False

        try:
            resp = await self._client.post(
                f"/api/services/{domain}/{service}",
                json=data,
            )
            return resp.status_code == 200
        except httpx.RequestError as e:
            logger.warning("HA service call failed: %s", e)
            return False
