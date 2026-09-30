"""Work the queue with the UnderCover Agent: uv run -m agent [--cap 5] [CLM-1001]"""

import argparse
import sys

from agent.main import work_claim
from agent.queue import run_queue


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
    parser.add_argument("claim_id", nargs="?", help="work this one claim")
    parser.add_argument("--cap", type=positive, help="the most claims the run works")
    options = parser.parse_args(args)
    if options.claim_id:
        print(work_claim(options.claim_id))
    else:
        run_queue(options.cap)


if __name__ == "__main__":
    main(sys.argv[1:])
