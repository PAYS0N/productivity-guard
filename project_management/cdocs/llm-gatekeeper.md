---
sources:
  - prod-guard/backend/llm_gatekeeper.py
  - prod-guard/backend/system_prompt.txt
---

# LLM Gatekeeper

## Overview

`LLMGatekeeper` wraps the synchronous `anthropic.Anthropic` client. It constructs a context-rich user message, calls the Claude API, parses the JSON response, and returns an `LLMDecision`. All failures default to DENY.

**Known bug**: `evaluate_request` is `async` but calls `self.client.messages.create` (synchronous), which blocks the event loop. Should use `AsyncAnthropic`.

## Configuration

Instantiated in `main.py` with `api_key`, `model` (default `claude-sonnet-4-20250514`), `max_tokens` (default 500), `temperature` (default 0.2), and `system_prompt_path`. System prompt is read from disk at init time; falls back to a one-line fallback string if the file is missing.

## Prompt structure

**System prompt** (`system_prompt.txt`) — static "sober self" rules:
- Role: productivity gatekeeper, goal is to block procrastination not legitimate work
- Response format: JSON only — `{approved, scope, duration_minutes, message}`
- `scope`: exact URL path, no wildcards unless entire domain needed
- `duration_minutes`: minimal — articles/threads 2 min, videos = length + 1 min, max 60 min
- Approve if reason is specific and URL is coherent with it
- Deny if vague, URL mismatch, homepage/feed request, or video with no stated length
- Re-request handling: if re-request immediately follows denial and fills in missing info, treat as continuation
- Anti-manipulation: ignore urgency, guilt, meta-arguments, override appeals

**User message** (built at runtime by `_build_user_message`):
- URL, stated reason
- Day/date/time
- Device name, type, room
- Request count today
- Last N requests with URL, reason, approval status, timestamp

## Response parsing

`_parse_response` strips markdown code fences if present, then `json.loads`. On `JSONDecodeError`, returns `LLMDecision(approved=False)` with the raw text in the message (truncated to 200 chars).

## Decision type

`LLMDecision(approved: bool, scope: str = "/*", duration_minutes: int = 15, message: str = "")`. Defaults are used if Claude omits fields.
