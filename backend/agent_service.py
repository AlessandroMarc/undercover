"""The agent's service, as the backend calls it: once after each sign-off."""

import logging
import os

import httpx

AGENT_URL = os.getenv("UNDERCOVER_AGENT", "http://127.0.0.1:8002")

agent = httpx.Client(base_url=f"{AGENT_URL}/api", timeout=10)

log = logging.getLogger(__name__)


def resume_claim(claim_id: str) -> None:
    """Ask the agent to pick a claim back up after its sign-off."""
    try:
        agent.post(f"/claims/{claim_id}/resume").raise_for_status()
    except httpx.HTTPError as error:  # the sign-off stands without the agent
        log.warning(
            "The agent didn't pick up %s after its sign-off: %s", claim_id, error
        )
