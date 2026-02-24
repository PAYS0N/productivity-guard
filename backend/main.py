"""Productivity Guard — FastAPI backend.

This is the central API that:
- Receives access requests from the Firefox extension
- Queries Home Assistant for device room data (Bermuda)
- Calls Claude API to evaluate requests
- Manages the dnsmasq blocklist for DNS-level blocking
- Logs all requests to SQLite for history/pattern tracking
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from blocklist import BlocklistManager
from database import Database
from ha_client import HAClient
from llm_gatekeeper import LLMGatekeeper
from backend.models import (
    AccessRequest,
    AccessResponse,
    DomainStatus,
    ForceBlockRequest,
    ForceUnblockRequest,
    HistoryEntry,
    StatusResponse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Load config ──────────────────────────────────────────────────────────────

CONFIG_PATH = os.environ.get("PG_CONFIG", str(Path(__file__).parent / "config.yaml"))

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

# Allow env var override for secrets
anthropic_key = os.environ.get("ANTHROPIC_API_KEY", config["anthropic"]["api_key"])
ha_token = os.environ.get("HA_TOKEN", config["homeassistant"]["token"])

# ── Initialize components ────────────────────────────────────────────────────

db = Database(config["database"]["path"])

blocklist = BlocklistManager(
    blocked_hosts_path=config["dnsmasq"]["blocked_hosts_path"],
    conditional_domains=config["domains"]["conditional"],
    always_blocked_domains=config["domains"].get("always_blocked", []),
)

ha_client = HAClient(
    ha_url=config["homeassistant"]["url"],
    token=ha_token,
    device_map=config.get("devices", {}),
)

llm = LLMGatekeeper(
    api_key=anthropic_key,
    model=config["anthropic"].get("model", "claude-sonnet-4-20250514"),
    max_tokens=config["anthropic"].get("max_tokens", 500),
    temperature=config["anthropic"].get("temperature", 0.2),
    system_prompt_path=str(Path(__file__).parent / "system_prompt.txt"),
    relax_schedule=config.get("schedule", {}),
)

# Track force-blocked devices (from HA automations, e.g., phone in bedroom)
force_blocked_devices: set[str] = set()


# ── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect DB, HA, write initial blocklist. Shutdown: cleanup."""
    await db.connect()
    await ha_client.connect()
    await blocklist.initialize()
    logger.info("Productivity Guard started on port %d", config["api"]["port"])
    yield
    await blocklist.reblock_all()
    await ha_client.close()
    await db.close()
    logger.info("Productivity Guard shut down — all domains re-blocked")


app = FastAPI(
    title="Productivity Guard",
    description="LLM-gated web access control",
    lifespan=lifespan,
)

# CORS: allow extension from any origin (it runs as moz-extension://)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helper ───────────────────────────────────────────────────────────────────

def extract_domain(url: str) -> str:
    """Extract the domain from a URL."""
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0]


def domain_to_conditional(domain: str) -> str | None:
    """Map a domain (possibly with www) to its conditional domain entry.

    Returns the matching conditional domain, or None if not found.
    """
    conditional = set(config["domains"]["conditional"])
    if domain in conditional:
        return domain
    # Try adding/removing www
    if domain.startswith("www."):
        base = domain[4:]
        if base in conditional:
            return base
    else:
        www = f"www.{domain}"
        if www in conditional:
            return www
    return None


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/request-access", response_model=AccessResponse)
async def request_access(body: AccessRequest, request: Request):
    """Main endpoint: evaluate an access request via the LLM gatekeeper."""

    # Determine device IP — prefer body, fall back to request source
    device_ip = body.device_ip or request.client.host
    domain = extract_domain(body.url)

    # Check if device is force-blocked
    if device_ip in force_blocked_devices:
        return AccessResponse(
            approved=False,
            message="Your device is currently force-blocked (location restriction). Access denied.",
            domain=domain,
        )

    # Validate domain is in our conditional list
    conditional_domain = domain_to_conditional(domain)
    if not conditional_domain:
        # Check always-blocked
        always = set(config["domains"].get("always_blocked", []))
        if domain in always or domain.lstrip("www.") in always:
            return AccessResponse(
                approved=False,
                message="This domain is permanently blocked. No exceptions.",
                domain=domain,
            )
        # Not a managed domain — shouldn't normally reach here
        return AccessResponse(
            approved=False,
            message="This domain is not in the managed blocklist.",
            domain=domain,
        )

    # Gather context
    device_info = ha_client.get_device_info(device_ip)
    device_name = device_info["name"] if device_info else None
    device_type = device_info.get("type") if device_info else None
    room = await ha_client.get_device_room(device_ip)
    request_count = await db.get_today_count(device_ip)
    recent = await db.get_recent_requests(limit=5, device_ip=device_ip)

    # Call the LLM
    decision = await llm.evaluate_request(
        url=body.url,
        reason=body.reason,
        device_name=device_name,
        device_type=device_type,
        room=room,
        request_count_today=request_count,
        recent_requests=recent,
    )

    # Act on the decision
    if decision.approved:
        success = await blocklist.unblock_domain(
            domain=conditional_domain,
            device_ip=device_ip,
            device_name=device_name,
            scope=decision.scope,
            reason=body.reason,
            duration_minutes=decision.duration_minutes,
        )
        if not success:
            decision.approved = False
            decision.message = "Failed to unblock domain at DNS level. " + decision.message

    # Log to database
    await db.log_request(
        device_ip=device_ip,
        device_name=device_name,
        url=body.url,
        domain=domain,
        reason=body.reason,
        room=room,
        approved=decision.approved,
        scope=decision.scope if decision.approved else None,
        duration_minutes=decision.duration_minutes if decision.approved else None,
        llm_message=decision.message,
        request_number_today=request_count + 1,
    )

    return AccessResponse(
        approved=decision.approved,
        scope=decision.scope if decision.approved else None,
        duration_minutes=decision.duration_minutes if decision.approved else None,
        message=decision.message,
        domain=domain,
    )


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Return current state: active unblocks and force-blocked devices."""
    active = blocklist.get_active_unblocks()
    return StatusResponse(
        active_unblocks=[
            DomainStatus(
                domain=u.domain,
                device_ip=u.device_ip,
                device_name=u.device_name,
                scope=u.scope,
                unblocked_at=u.unblocked_at,
                expires_at=u.expires_at,
                reason=u.reason,
            )
            for u in active
        ],
        force_blocked_devices=list(force_blocked_devices),
    )


@app.post("/revoke/{domain}")
async def revoke_domain(domain: str):
    """Immediately re-block a domain."""
    await blocklist.reblock_domain(domain)
    return {"status": "re-blocked", "domain": domain}


@app.post("/revoke-all")
async def revoke_all():
    """Re-block all domains immediately."""
    await blocklist.reblock_all()
    return {"status": "all domains re-blocked"}


@app.get("/history")
async def get_history():
    """Return today's request history."""
    rows = await db.get_today_history()
    return {"requests": rows}


@app.post("/force-block")
async def force_block_device(body: ForceBlockRequest):
    """Force-block a device (called by HA automations, e.g., phone in bedroom).

    This revokes any active approvals and auto-denies all new requests.
    """
    force_blocked_devices.add(body.device_ip)
    # Revoke any active unblocks for this device
    for domain, unblock in list(blocklist.active_unblocks.items()):
        if unblock.device_ip == body.device_ip:
            await blocklist.reblock_domain(domain)
    logger.info("Force-blocked device %s", body.device_ip)
    return {"status": "force-blocked", "device_ip": body.device_ip}


@app.post("/force-unblock")
async def force_unblock_device(body: ForceUnblockRequest):
    """Remove force-block from a device (called by HA automations)."""
    force_blocked_devices.discard(body.device_ip)
    logger.info("Removed force-block for device %s", body.device_ip)
    return {"status": "force-block removed", "device_ip": body.device_ip}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Run with uvicorn ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=config["api"]["host"],
        port=config["api"]["port"],
        log_level="info",
    )
