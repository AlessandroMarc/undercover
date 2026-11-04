"""Work the claims queue: uv run -m agent.work [CLAIM_ID ...]."""

import sys
from uuid import uuid4

from langchain_core.language_models import BaseChatModel

from agent import main as core
from agent.main import ClaimError, run


def waiting_claim_ids() -> list[str]:
    """Return the ids of the claims still waiting, in queue order."""
    with core.backend() as client:
        claims = client.get("/api/claims").json()
    return [claim["claim_id"] for claim in claims if claim["status"] == "waiting"]


def main(claim_ids: list[str], llm: BaseChatModel | None = None) -> None:
    """Run the agent on the given claims, or on every waiting claim."""
    for claim_id in claim_ids or waiting_claim_ids():
        print(f"{claim_id}: working")
        try:
            reply = run(claim_id, f"{claim_id}-{uuid4().hex[:8]}", llm)
        except ClaimError as error:
            raise SystemExit(str(error)) from error
        print(f"{claim_id}: {reply}")


if __name__ == "__main__":
    main(sys.argv[1:])
