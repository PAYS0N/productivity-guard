"""Unit tests for HAClient.

The httpx.AsyncClient is mocked directly — no real HTTP calls are made.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from ha_client import HAClient


# ── Fixtures ──────────────────────────────────────────────────────────────────


DEVICE_MAP = {
    "192.168.1.100": {
        "name": "test-laptop",
        "type": "laptop",
        "bermuda_entity": "sensor.test_laptop_ble_room",
    },
    "192.168.1.101": {
        "name": "test-phone",
        "type": "phone",
        # No bermuda_entity — tests the "no entity configured" path
    },
}


@pytest.fixture
def ha():
    """HAClient with real device_map but no HTTP connection yet."""
    return HAClient(
        ha_url="http://ha.test:8123",
        token="fake-token",
        device_map=DEVICE_MAP,
    )


@pytest.fixture
def ha_connected(ha):
    """HAClient with a mocked httpx.AsyncClient injected."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    ha._client = mock_client
    return ha


def _mock_response(status_code: int, json_body: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.text = str(json_body)
    return resp


# ── get_device_info (synchronous) ─────────────────────────────────────────────


class TestGetDeviceInfo:
    def test_known_ip_returns_info(self, ha):
        info = ha.get_device_info("192.168.1.100")
        assert info is not None
        assert info["name"] == "test-laptop"
        assert info["type"] == "laptop"

    def test_unknown_ip_returns_none(self, ha):
        assert ha.get_device_info("10.0.0.99") is None

    def test_returns_full_dict_including_bermuda_entity(self, ha):
        info = ha.get_device_info("192.168.1.100")
        assert info["bermuda_entity"] == "sensor.test_laptop_ble_room"

    def test_device_without_bermuda_entity(self, ha):
        info = ha.get_device_info("192.168.1.101")
        assert info is not None
        assert "bermuda_entity" not in info


# ── get_device_room (async) ───────────────────────────────────────────────────


class TestGetDeviceRoom:
    async def test_returns_room_for_known_device(self, ha_connected):
        ha_connected._client.get.return_value = _mock_response(
            200, {"state": "living_room"}
        )
        room = await ha_connected.get_device_room("192.168.1.100")
        assert room == "living_room"

    async def test_returns_none_for_unknown_ip(self, ha_connected):
        room = await ha_connected.get_device_room("10.0.0.99")
        assert room is None
        # No HTTP call should be made for an unknown device
        ha_connected._client.get.assert_not_called()

    async def test_returns_none_when_no_bermuda_entity(self, ha_connected):
        """Device at .101 has no bermuda_entity key."""
        room = await ha_connected.get_device_room("192.168.1.101")
        assert room is None
        ha_connected._client.get.assert_not_called()

    async def test_returns_none_when_not_connected(self, ha):
        """_client is None — should return None without raising."""
        assert ha._client is None
        room = await ha.get_device_room("192.168.1.100")
        assert room is None


# ── _get_entity_state (async) ─────────────────────────────────────────────────


class TestGetEntityState:
    async def test_200_with_valid_state(self, ha_connected):
        ha_connected._client.get.return_value = _mock_response(
            200, {"state": "office"}
        )
        result = await ha_connected._get_entity_state("sensor.test_ble_room")
        assert result == "office"

    async def test_200_with_unknown_state_returns_none(self, ha_connected):
        ha_connected._client.get.return_value = _mock_response(
            200, {"state": "unknown"}
        )
        result = await ha_connected._get_entity_state("sensor.test")
        assert result is None

    async def test_200_with_unavailable_state_returns_none(self, ha_connected):
        ha_connected._client.get.return_value = _mock_response(
            200, {"state": "unavailable"}
        )
        result = await ha_connected._get_entity_state("sensor.test")
        assert result is None

    async def test_200_with_empty_state_returns_none(self, ha_connected):
        ha_connected._client.get.return_value = _mock_response(
            200, {"state": ""}
        )
        result = await ha_connected._get_entity_state("sensor.test")
        assert result is None

    async def test_404_returns_none(self, ha_connected):
        ha_connected._client.get.return_value = _mock_response(404, {})
        result = await ha_connected._get_entity_state("sensor.nonexistent")
        assert result is None

    async def test_500_returns_none(self, ha_connected):
        ha_connected._client.get.return_value = _mock_response(500, {})
        result = await ha_connected._get_entity_state("sensor.broken")
        assert result is None

    async def test_request_error_returns_none(self, ha_connected):
        ha_connected._client.get.side_effect = httpx.RequestError("Connection refused")
        result = await ha_connected._get_entity_state("sensor.test")
        assert result is None

    async def test_not_connected_returns_none(self, ha):
        """_client is None — should return None cleanly."""
        result = await ha._get_entity_state("sensor.test")
        assert result is None

    async def test_calls_correct_api_path(self, ha_connected):
        ha_connected._client.get.return_value = _mock_response(
            200, {"state": "bedroom"}
        )
        await ha_connected._get_entity_state("sensor.my_device_ble_room")
        ha_connected._client.get.assert_called_once_with(
            "/api/states/sensor.my_device_ble_room"
        )


# ── connect / close ───────────────────────────────────────────────────────────


class TestConnectClose:
    async def test_connect_creates_client(self, ha, mocker):
        # Mock the connection test call to /api/
        mock_resp = _mock_response(200, {"message": "API running."})
        mock_resp.raise_for_status = MagicMock()

        # We need to intercept httpx.AsyncClient creation
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mocker.patch("ha_client.httpx.AsyncClient", return_value=mock_client)

        await ha.connect()
        assert ha._client is mock_client

    async def test_connect_handles_connection_failure_gracefully(self, ha, mocker):
        """If the HA connection test fails, connect() should not raise — it warns."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.RequestError("refused")
        mocker.patch("ha_client.httpx.AsyncClient", return_value=mock_client)

        await ha.connect()  # Should not raise
        assert ha._client is mock_client  # client was still created

    async def test_close_closes_client(self, ha_connected):
        await ha_connected.close()
        ha_connected._client.aclose.assert_called_once()

    async def test_close_when_not_connected_is_noop(self, ha):
        await ha.close()  # _client is None — should not raise


# ── get_entity_state (public wrapper) ─────────────────────────────────────────


class TestGetEntityStatePublic:
    async def test_delegates_to_private_method(self, ha_connected):
        ha_connected._client.get.return_value = _mock_response(
            200, {"state": "kitchen"}
        )
        result = await ha_connected.get_entity_state("sensor.kitchen_sensor")
        assert result == "kitchen"
