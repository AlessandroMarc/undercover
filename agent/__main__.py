"""Work one claim with the UnderCover Agent: uv run -m agent CLM-1001"""

import argparse
import sys

from dotenv import load_dotenv

from agent import api
from agent.console import show_reports
from agent.harness import checkpoint_pool, claim_graphs, model, work_claim


def main(args: list[str]) -> None:
    """Work the claim named on the command line, with no run."""
    parser = argparse.ArgumentParser(
        prog="uv run -m agent", description="Work one claim in the queue."
    )
    parser.add_argument("claim_id", help="the claim to work")
    options = parser.parse_args(args)
    with checkpoint_pool() as pool:
        graph = claim_graphs(model(), pool)()
        try:
            work_claim(options.claim_id, None, graph)
        except api.Refused as refusal:
            parser.exit(1, f"{options.claim_id}  not started: {refusal}\n")


if __name__ == "__main__":
    load_dotenv(override=True)
    show_reports()
    main(sys.argv[1:])
