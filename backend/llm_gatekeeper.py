"""LLM Gatekeeper — builds context-rich prompts and calls the Claude API for access decisions."""

import json
import logging
from datetime import datetime, date
from typing import Optional
from pathlib import Path

import anthropic

from models import LLMDecision

logger = logging.getLogger(__name__)


class LLMGatekeeper:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 500,
        temperature: float = 0.2,
        system_prompt_path: str = "system_prompt.txt",
        relax_schedule: Optional[dict] = None,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.relax_schedule = relax_schedule or {}

        # Load system prompt
        prompt_path = Path(system_prompt_path)
        if prompt_path.exists():
            self.system_prompt = prompt_path.read_text().strip()
        else:
            logger.error("System prompt not found at %s, using fallback", system_prompt_path)
            self.system_prompt = self._fallback_system_prompt()

    def _fallback_system_prompt(self) -> str:
        return (
            "You are a strict productivity gatekeeper. Default to DENY. "
            "Respond in JSON format: {\"approved\": bool, \"scope\": str, "
            "\"duration_minutes\": int, \"message\": str}"
        )

    def _is_relax_window(self) -> bool:
        """Check if the current time falls within a configured relax window."""
        now = datetime.now()
        day_of_week = now.weekday()  # 0=Monday, 6=Sunday
        is_weekend = day_of_week >= 5

        schedule_key = "weekend" if is_weekend else "weekday"
        window = self.relax_schedule.get("relax_windows", {}).get(schedule_key)
        if not window:
            return False

        start_h, start_m = map(int, window["start"].split(":"))
        end_h, end_m = map(int, window["end"].split(":"))
        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m

        return start_minutes <= current_minutes <= end_minutes

    def _build_user_message(
        self,
        url: str,
        reason: str,
        device_name: Optional[str],
        device_type: Optional[str],
        room: Optional[str],
        request_count_today: int,
        recent_requests: list[dict],
    ) -> str:
        """Build the context-rich user message for the Claude API call."""
        now = datetime.now()
        day_name = now.strftime("%A")
        time_str = now.strftime("%I:%M %p")
        date_str = now.strftime("%Y-%m-%d")

        is_relax = self._is_relax_window()
        relax_rooms = self.relax_schedule.get("relax_rooms", [])

        parts = [
            f"## Access Request",
            f"- **URL**: {url}",
            f"- **Reason given**: {reason}",
            f"",
            f"## Context",
            f"- **Time**: {day_name}, {date_str} at {time_str}",
            f"- **Device**: {device_name or 'unknown'} ({device_type or 'unknown'})",
            f"- **Room**: {room or 'unknown'}",
            f"- **Relax window active**: {'YES' if is_relax else 'NO'}",
        ]

        if is_relax:
            in_relax_room = room and room.lower().replace(" ", "_") in [
                r.lower().replace(" ", "_") for r in relax_rooms
            ]
            parts.append(
                f"- **In relax-eligible room**: {'YES' if in_relax_room else 'NO'} "
                f"(eligible rooms: {', '.join(relax_rooms)})"
            )

        parts.append(f"- **Request #{request_count_today + 1} today**")

        if recent_requests:
            parts.append(f"")
            parts.append(f"## Recent Request History (last {len(recent_requests)})")
            for req in recent_requests:
                status = "APPROVED" if req.get("approved") else "DENIED"
                parts.append(
                    f"- [{status}] {req.get('url', '?')} — "
                    f"reason: \"{req.get('reason', '?')}\" "
                    f"(at {req.get('timestamp', '?')[:16]})"
                )

        parts.append(f"")
        parts.append(
            "Evaluate this request and respond with a JSON object. "
            "Remember: your default is DENY. You need a genuinely compelling, "
            "specific reason to approve."
        )

        return "\n".join(parts)

    async def evaluate_request(
        self,
        url: str,
        reason: str,
        device_name: Optional[str] = None,
        device_type: Optional[str] = None,
        room: Optional[str] = None,
        request_count_today: int = 0,
        recent_requests: Optional[list[dict]] = None,
    ) -> LLMDecision:
        """Call Claude API to evaluate an access request. Returns an LLMDecision."""

        user_message = self._build_user_message(
            url=url,
            reason=reason,
            device_name=device_name,
            device_type=device_type,
            room=room,
            request_count_today=request_count_today,
            recent_requests=recent_requests or [],
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            # Extract text from response
            raw_text = ""
            for block in response.content:
                if block.type == "text":
                    raw_text += block.text

            return self._parse_response(raw_text)

        except anthropic.APIError as e:
            logger.error("Claude API error: %s", e)
            return LLMDecision(
                approved=False,
                message=f"Gatekeeper API error: {e}. Defaulting to DENY.",
            )
        except Exception as e:
            logger.error("Unexpected error calling Claude API: %s", e)
            return LLMDecision(
                approved=False,
                message="Gatekeeper encountered an error. Defaulting to DENY.",
            )

    def _parse_response(self, raw_text: str) -> LLMDecision:
        """Parse the Claude API response text into an LLMDecision.

        Expects JSON, but handles markdown code fences and other wrapping.
        """
        text = raw_text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
            return LLMDecision(
                approved=data.get("approved", False),
                scope=data.get("scope", "/*"),
                duration_minutes=data.get("duration_minutes", 15),
                message=data.get("message", ""),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse LLM response as JSON: %s\nRaw: %s", e, raw_text)
            # If we can't parse, default to DENY
            return LLMDecision(
                approved=False,
                message=f"Could not parse gatekeeper response. Defaulting to DENY. Raw: {raw_text[:200]}",
            )
