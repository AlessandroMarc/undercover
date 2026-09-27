"""Work one claim with the UnderCover Agent: uv run -m agent CLM-1001"""

import sys
import uuid

from agent.main import run


def main(args: list[str]) -> None:
    """Work the claim named on the command line and print the agent's reply."""
    print(run(args[0], str(uuid.uuid4())))


if __name__ == "__main__":
    main(sys.argv[1:])
