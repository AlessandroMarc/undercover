"""Work the claims: uv run -m agent.work [--limit N | CLAIM_ID ...]."""

import argparse
from uuid import uuid4

from langchain_core.language_models import BaseChatModel

from agent.harness import work_claim
from agent.main import ClaimError
from agent.queue_agent import RunFailed, run_queue


def positive(text: str) -> int:
    number = int(text)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent.work", description=__doc__)
    parser.add_argument("claim_ids", nargs="*", help="work just these claims")
    parser.add_argument("--limit", type=positive, help="work at most this many claims")
    args = parser.parse_args(argv)
    if args.claim_ids and args.limit:
        parser.error("give claim ids or --limit, not both")
    return args


def main(argv: list[str], llm: BaseChatModel | None = None) -> None:
    """Work the named claims, or the whole queue with the queue agent."""
    args = parse(argv)
    try:
        for claim_id in args.claim_ids:
            print(f"{claim_id}: working")
            print(work_claim(claim_id, llm))
        if not args.claim_ids:
            print(run_queue(args.limit, f"queue-{uuid4().hex[:8]}", llm))
    except (ClaimError, RunFailed) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])
