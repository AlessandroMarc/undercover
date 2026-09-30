"""Work the queue with the UnderCover Agent: uv run -m agent [--cap 5 | CLM-1001]"""

import argparse
import logging
import sys

from dotenv import load_dotenv

from agent import api
from agent.harness import claim_agent, model, run_queue, work_claim


def positive(text: str) -> int:
    """Read a whole number of at least 1."""
    number = int(text)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def main(args: list[str]) -> None:
    """Work the claim named on the command line, or the queue up to a cap."""
    parser = argparse.ArgumentParser(
        prog="uv run -m agent", description="Work the claims queue."
    )
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("claim_id", nargs="?", help="work this one claim")
    choice.add_argument("--cap", type=positive, help="the most claims the run works")
    options = parser.parse_args(args)
    if not options.claim_id:
        run_queue(options.cap, model(), model())
        return
    try:
        work_claim(options.claim_id, claim_agent(model()))
    except api.Refused as refusal:
        parser.exit(1, f"{options.claim_id}  not started: {refusal}\n")


if __name__ == "__main__":
    load_dotenv(override=True)
    logging.basicConfig(format="%(message)s", stream=sys.stdout)
    logging.getLogger("agent").setLevel(logging.INFO)
    main(sys.argv[1:])
