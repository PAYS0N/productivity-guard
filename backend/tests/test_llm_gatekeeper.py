"""Unit tests for LLMGatekeeper.

The Anthropic API is stubbed throughout — no real API calls are made.

Known issue this file documents:
- evaluate_request() is `async` but calls the SYNCHRONOUS anthropic.Anthropic
  client (messages.create), not AsyncAnthropic. This blocks the event loop.
  Tests verify the sync method is called, not an async variant.
"""

import pytest
import httpx
from unittest.mock import MagicMock, patch
from freezegun import freeze_time

import anthropic

from llm_gatekeeper import LLMGatekeeper
from models import LLMDecision


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def system_prompt_file(tmp_path):
    """A minimal system prompt file."""
    p = tmp_path / "system_prompt.txt"
    p.write_text("You are a strict productivity gatekeeper. Default to DENY.")
    return str(p)


@pytest.fixture
def gatekeeper(system_prompt_file):
    """LLMGatekeeper with a weekday 20:00–23:00 and weekend 15:00–23:00 schedule."""
    return LLMGatekeeper(
        api_key="test-fake-key",
        model="claude-test",
        max_tokens=100,
        temperature=0.0,
        system_prompt_path=system_prompt_file,
        relax_schedule={
            "relax_windows": {
                "weekday": {"start": "20:00", "end": "23:00"},
                "weekend": {"start": "15:00", "end": "23:00"},
            },
            "relax_rooms": ["living_room"],
        },
    )


def _mock_llm_response(json_text: str) -> MagicMock:
    """Build a fake Anthropic API response object containing json_text."""
    block = MagicMock()
    block.type = "text"
    block.text = json_text
    resp = MagicMock()
    resp.content = [block]
    return resp


# ── _parse_response ───────────────────────────────────────────────────────────


class TestParseResponse:
    def test_clean_json_approved(self, gatekeeper):
        result = gatekeeper._parse_response(
            '{"approved": true, "scope": "/r/esp32/*", "duration_minutes": 12, "message": "Approved for work"}'
        )
        assert result.approved is True
        assert result.scope == "/r/esp32/*"
        assert result.duration_minutes == 12
        assert result.message == "Approved for work"

    def test_clean_json_denied(self, gatekeeper):
        result = gatekeeper._parse_response(
            '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "Not productive"}'
        )
        assert result.approved is False
        assert result.message == "Not productive"

    def test_markdown_fenced_with_language_tag(self, gatekeeper):
        raw = '```json\n{"approved": true, "scope": "/*", "duration_minutes": 15, "message": "ok"}\n```'
        result = gatekeeper._parse_response(raw)
        assert result.approved is True
        assert result.scope == "/*"

    def test_markdown_fenced_without_language_tag(self, gatekeeper):
        raw = '```\n{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "denied"}\n```'
        result = gatekeeper._parse_response(raw)
        assert result.approved is False

    def test_invalid_json_returns_deny(self, gatekeeper):
        result = gatekeeper._parse_response("not valid json at all")
        assert result.approved is False
        assert "Could not parse" in result.message

    def test_empty_string_returns_deny(self, gatekeeper):
        result = gatekeeper._parse_response("")
        assert result.approved is False

    def test_missing_approved_key_defaults_to_false(self, gatekeeper):
        # data.get("approved", False) — should default to False when key absent
        result = gatekeeper._parse_response(
            '{"scope": "/*", "duration_minutes": 10, "message": "something"}'
        )
        assert result.approved is False

    def test_missing_scope_uses_default(self, gatekeeper):
        result = gatekeeper._parse_response('{"approved": true, "message": "ok"}')
        assert result.scope == "/*"
        assert result.duration_minutes == 15

    def test_backtick_inside_string_value_preserved(self, gatekeeper):
        """A backtick inside a JSON string value should survive fence stripping."""
        raw = '{"approved": true, "message": "use `curl` to test", "scope": "/*", "duration_minutes": 5}'
        result = gatekeeper._parse_response(raw)
        assert result.approved is True
        assert "`curl`" in result.message

    def test_fenced_response_strips_outer_fences_only(self, gatekeeper):
        """Fence lines (``` or ```json) should be stripped but other content kept."""
        raw = '```json\n{"approved": true, "scope": "/test/*", "duration_minutes": 10, "message": "fine"}\n```'
        result = gatekeeper._parse_response(raw)
        assert result.approved is True
        assert result.scope == "/test/*"

    def test_extra_whitespace_handled(self, gatekeeper):
        """Leading/trailing whitespace around the JSON block."""
        raw = '  \n  {"approved": false, "message": "denied", "scope": "/*", "duration_minutes": 0}  \n  '
        result = gatekeeper._parse_response(raw)
        assert result.approved is False

    def test_boolean_false_not_overridden(self, gatekeeper):
        """Ensure approved=false is preserved and not treated as missing."""
        result = gatekeeper._parse_response(
            '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
        )
        assert result.approved is False
        assert isinstance(result, LLMDecision)


# ── _is_relax_window ──────────────────────────────────────────────────────────


class TestIsRelaxWindow:
    @freeze_time("2024-02-06 21:00:00")  # Tuesday 9 PM — inside window
    def test_inside_weekday_window(self, gatekeeper):
        assert gatekeeper._is_relax_window() is True

    @freeze_time("2024-02-06 19:59:00")  # Tuesday 7:59 PM — before window starts
    def test_outside_weekday_window_before(self, gatekeeper):
        assert gatekeeper._is_relax_window() is False

    @freeze_time("2024-02-06 23:01:00")  # Tuesday 11:01 PM — after window ends
    def test_outside_weekday_window_after(self, gatekeeper):
        assert gatekeeper._is_relax_window() is False

    @freeze_time("2024-02-10 16:00:00")  # Saturday 4 PM — inside weekend window
    def test_inside_weekend_window(self, gatekeeper):
        assert gatekeeper._is_relax_window() is True

    @freeze_time("2024-02-10 14:59:00")  # Saturday 2:59 PM — before weekend starts
    def test_outside_weekend_window_before(self, gatekeeper):
        assert gatekeeper._is_relax_window() is False

    @freeze_time("2024-02-06 20:00:00")  # Exactly at weekday start — inclusive
    def test_boundary_start_inclusive(self, gatekeeper):
        assert gatekeeper._is_relax_window() is True

    @freeze_time("2024-02-06 23:00:00")  # Exactly at weekday end — inclusive
    def test_boundary_end_inclusive(self, gatekeeper):
        assert gatekeeper._is_relax_window() is True

    def test_no_schedule_returns_false(self, system_prompt_file):
        gk = LLMGatekeeper(
            api_key="fake",
            system_prompt_path=system_prompt_file,
            relax_schedule={},
        )
        assert gk._is_relax_window() is False

    def test_missing_window_key_returns_false(self, system_prompt_file):
        """relax_schedule exists but has no relax_windows key."""
        gk = LLMGatekeeper(
            api_key="fake",
            system_prompt_path=system_prompt_file,
            relax_schedule={"relax_rooms": ["living_room"]},
        )
        assert gk._is_relax_window() is False

    @freeze_time("2024-02-11 21:00:00")  # Sunday — is_weekend check
    def test_sunday_uses_weekend_schedule(self, gatekeeper):
        assert gatekeeper._is_relax_window() is True  # Sunday 9 PM in 15:00–23:00


# ── _build_user_message ───────────────────────────────────────────────────────


class TestBuildUserMessage:
    def _build(self, gatekeeper, **kwargs):
        defaults = dict(
            url="https://reddit.com/r/python",
            reason="reading documentation",
            device_name="laptop",
            device_type="laptop",
            room="office",
            request_count_today=0,
            recent_requests=[],
        )
        defaults.update(kwargs)
        return gatekeeper._build_user_message(**defaults)

    def test_url_present_in_message(self, gatekeeper):
        msg = self._build(gatekeeper, url="https://reddit.com/r/python")
        assert "https://reddit.com/r/python" in msg

    def test_reason_present_in_message(self, gatekeeper):
        msg = self._build(gatekeeper, reason="debugging a library issue")
        assert "debugging a library issue" in msg

    def test_unknown_device_shows_unknown(self, gatekeeper):
        msg = self._build(gatekeeper, device_name=None, device_type=None, room=None)
        assert "unknown" in msg.lower()

    def test_request_count_is_incremented(self, gatekeeper):
        msg = self._build(gatekeeper, request_count_today=3)
        assert "Request #4 today" in msg

    def test_first_request_shown_as_1(self, gatekeeper):
        msg = self._build(gatekeeper, request_count_today=0)
        assert "Request #1 today" in msg

    def test_recent_approved_request_labeled(self, gatekeeper):
        recent = [
            {
                "url": "https://youtube.com/watch?v=abc",
                "reason": "background music",
                "approved": True,
                "timestamp": "2024-02-06T20:00:00",
            }
        ]
        msg = self._build(gatekeeper, recent_requests=recent)
        assert "[APPROVED]" in msg
        assert "background music" in msg

    def test_recent_denied_request_labeled(self, gatekeeper):
        recent = [
            {
                "url": "https://reddit.com",
                "reason": "browsing",
                "approved": False,
                "timestamp": "2024-02-06T19:00:00",
            }
        ]
        msg = self._build(gatekeeper, recent_requests=recent)
        assert "[DENIED]" in msg

    def test_no_recent_requests_no_history_section(self, gatekeeper):
        msg = self._build(gatekeeper, recent_requests=[])
        assert "Recent Request History" not in msg

    @freeze_time("2024-02-06 21:30:00")  # Inside weekday relax window
    def test_relax_window_active_shown_when_in_window(self, gatekeeper):
        msg = self._build(gatekeeper, room="living_room")
        assert "YES" in msg  # "Relax window active: YES"

    @freeze_time("2024-02-06 19:00:00")  # Outside relax window
    def test_relax_window_inactive_shown_outside_window(self, gatekeeper):
        msg = self._build(gatekeeper)
        assert "NO" in msg  # "Relax window active: NO"

    @freeze_time("2024-02-06 21:30:00")  # Inside relax window
    def test_relax_room_eligibility_shown_in_window(self, gatekeeper):
        msg = self._build(gatekeeper, room="living_room")
        assert "In relax-eligible room" in msg

    @freeze_time("2024-02-06 19:00:00")  # Outside relax window
    def test_relax_room_info_absent_outside_window(self, gatekeeper):
        msg = self._build(gatekeeper, room="living_room")
        assert "In relax-eligible room" not in msg


# ── evaluate_request (async, LLM stubbed) ────────────────────────────────────


class TestEvaluateRequest:
    async def test_approved_response_returned(self, gatekeeper):
        gatekeeper.client.messages.create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": true, "scope": "/r/python/*", "duration_minutes": 20, "message": "Approved"}'
            )
        )
        result = await gatekeeper.evaluate_request(
            url="https://reddit.com/r/python",
            reason="reading documentation",
        )
        assert result.approved is True
        assert result.scope == "/r/python/*"
        assert result.duration_minutes == 20

    async def test_denied_response_returned(self, gatekeeper):
        gatekeeper.client.messages.create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "Not productive"}'
            )
        )
        result = await gatekeeper.evaluate_request(
            url="https://youtube.com/watch?v=abc",
            reason="I want to watch videos",
        )
        assert result.approved is False

    async def test_fenced_response_still_parsed(self, gatekeeper):
        gatekeeper.client.messages.create = MagicMock(
            return_value=_mock_llm_response(
                '```json\n{"approved": true, "scope": "/*", "duration_minutes": 15, "message": "ok"}\n```'
            )
        )
        result = await gatekeeper.evaluate_request(
            url="https://reddit.com", reason="work research"
        )
        assert result.approved is True

    async def test_api_connection_error_returns_deny(self, gatekeeper):
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        gatekeeper.client.messages.create = MagicMock(
            side_effect=anthropic.APIConnectionError(request=request)
        )
        result = await gatekeeper.evaluate_request(
            url="https://reddit.com", reason="work"
        )
        assert result.approved is False
        assert "error" in result.message.lower()

    async def test_unexpected_exception_returns_deny(self, gatekeeper):
        gatekeeper.client.messages.create = MagicMock(
            side_effect=RuntimeError("Unexpected failure")
        )
        result = await gatekeeper.evaluate_request(
            url="https://reddit.com", reason="work"
        )
        assert result.approved is False
        assert result.message  # some message is set

    async def test_uses_synchronous_messages_create(self, gatekeeper):
        """evaluate_request calls the SYNC client (anthropic.Anthropic), not AsyncAnthropic.

        This documents the current design: the blocking sync HTTP call runs inside
        an async function, which blocks the event loop during each LLM request.
        """
        gatekeeper.client.messages.create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "denied"}'
            )
        )
        await gatekeeper.evaluate_request(url="https://reddit.com", reason="test")
        # The SYNC create was called exactly once
        gatekeeper.client.messages.create.assert_called_once()

    async def test_api_called_with_model_and_system_prompt(self, gatekeeper):
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(url="https://reddit.com", reason="test")

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "claude-test"
        assert call_kwargs["system"] == gatekeeper.system_prompt
        assert call_kwargs["messages"][0]["role"] == "user"

    async def test_api_called_with_max_tokens_and_temperature(self, gatekeeper):
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(url="https://reddit.com", reason="test")

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 100  # matches fixture (max_tokens=100)
        assert call_kwargs["temperature"] == 0.0  # matches fixture (temperature=0.0)

    async def test_user_message_contains_url_and_reason(self, gatekeeper):
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(
            url="https://reddit.com/r/python",
            reason="specific work task",
            device_name="my-laptop",
        )
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "https://reddit.com/r/python" in user_content
        assert "specific work task" in user_content
        assert "my-laptop" in user_content

    async def test_user_message_contains_room(self, gatekeeper):
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(
            url="https://reddit.com",
            reason="test",
            room="living_room",
        )
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "living_room" in user_content

    async def test_user_message_contains_request_count(self, gatekeeper):
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(
            url="https://reddit.com",
            reason="test",
            request_count_today=4,
        )
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "Request #5 today" in user_content

    async def test_user_message_contains_recent_requests(self, gatekeeper):
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(
            url="https://reddit.com",
            reason="test",
            recent_requests=[
                {
                    "url": "https://youtube.com",
                    "reason": "background music",
                    "approved": True,
                    "timestamp": "2024-02-06T20:00:00",
                }
            ],
        )
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "youtube.com" in user_content
        assert "background music" in user_content
        assert "[APPROVED]" in user_content

    @freeze_time("2024-02-06 21:00:00")  # Tuesday 9 PM — inside weekday window
    async def test_user_message_shows_relax_active_when_in_window(self, gatekeeper):
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(url="https://reddit.com", reason="test")
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "Relax window active" in user_content
        assert "YES" in user_content

    @freeze_time("2024-02-06 19:00:00")  # Tuesday 7 PM — outside window
    async def test_user_message_shows_relax_inactive_outside_window(self, gatekeeper):
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(url="https://reddit.com", reason="test")
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "Relax window active" in user_content
        assert "NO" in user_content

    @freeze_time("2024-02-06 21:00:00")  # Inside window
    async def test_user_message_shows_room_eligibility_when_in_window(self, gatekeeper):
        """When in relax window, the LLM sees whether the device is in an eligible room."""
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(
            url="https://reddit.com", reason="test", room="living_room"
        )
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "In relax-eligible room" in user_content
        assert "living_room" in user_content

    @freeze_time("2024-02-06 21:00:00")  # Inside window
    async def test_user_message_shows_not_in_eligible_room(self, gatekeeper):
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(
            url="https://reddit.com", reason="test", room="bedroom"
        )
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "In relax-eligible room" in user_content
        # bedroom is not in relax_rooms so it should show NO
        assert "NO" in user_content

    @freeze_time("2024-02-06 19:00:00")  # Outside window
    async def test_user_message_omits_room_eligibility_outside_window(self, gatekeeper):
        """Room eligibility is only shown when in a relax window — not otherwise."""
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(
            url="https://reddit.com", reason="test", room="living_room"
        )
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        # Room eligibility section not shown outside relax window
        assert "In relax-eligible room" not in user_content

    async def test_next_relax_window_not_in_prompt(self, gatekeeper):
        """The LLM is NOT told when the next relax window starts.

        The prompt only includes whether a relax window is currently active (YES/NO).
        The schedule start/end times are not forwarded to the LLM.
        """
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(url="https://reddit.com", reason="test")
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        # Schedule window times are not passed to the LLM
        assert "20:00" not in user_content
        assert "23:00" not in user_content

    async def test_user_message_contains_device_type(self, gatekeeper):
        mock_create = MagicMock(
            return_value=_mock_llm_response(
                '{"approved": false, "scope": "/*", "duration_minutes": 0, "message": "no"}'
            )
        )
        gatekeeper.client.messages.create = mock_create
        await gatekeeper.evaluate_request(
            url="https://reddit.com",
            reason="test",
            device_name="payson_s25",
            device_type="phone",
        )
        user_content = mock_create.call_args.kwargs["messages"][0]["content"]
        assert "phone" in user_content

    async def test_system_prompt_fallback_when_file_missing(self, tmp_path):
        """If system_prompt.txt doesn't exist, a fallback is used without crashing."""
        gk = LLMGatekeeper(
            api_key="fake",
            system_prompt_path=str(tmp_path / "nonexistent.txt"),
        )
        assert gk.system_prompt  # fallback is set
        assert "DENY" in gk.system_prompt
