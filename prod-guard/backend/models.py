"""Pydantic models for the Productivity Guard API."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AccessRequest(BaseModel):
    """Incoming request from the browser extension."""
    url: str
    reason: str
    device_ip: Optional[str] = None  # Optional — can be detected from request source


class AccessResponse(BaseModel):
    """Response sent back to the browser extension."""
    approved: bool
    scope: Optional[str] = None          # Path pattern like "/r/esp32/*"
    duration_minutes: Optional[int] = None
    message: str
    domain: Optional[str] = None


class LLMDecision(BaseModel):
    """Parsed decision from the Claude API response."""
    approved: bool
    scope: str = "/*"
    duration_minutes: int = 15
    message: str = ""


class DomainStatus(BaseModel):
    """Status of a temporarily unblocked domain."""
    domain: str
    device_ip: str
    device_name: Optional[str] = None
    scope: Optional[str] = None
    unblocked_at: datetime
    expires_at: datetime
    reason: str


class StatusResponse(BaseModel):
    """Response for the /status endpoint."""
    active_unblocks: list[DomainStatus]
    force_blocked_devices: list[str]


class HistoryEntry(BaseModel):
    """A single request history entry."""
    id: int
    timestamp: str
    device_ip: str
    device_name: Optional[str] = None
    url: str
    domain: str
    reason: str
    room: Optional[str] = None
    approved: bool
    scope: Optional[str] = None
    duration_minutes: Optional[int] = None
    llm_message: Optional[str] = None
    request_number_today: int


class ForceBlockRequest(BaseModel):
    """Request to force-block a device (from HA automation)."""
    device_ip: str


class ForceUnblockRequest(BaseModel):
    """Request to remove force-block from a device."""
    device_ip: str
