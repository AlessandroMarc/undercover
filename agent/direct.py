"""The direct route: the claim agent's tools and its payment straight to the app,
through the agent's API with its key."""

from typing import Any

from agent import api
from agent.routes import Target


class Direct:
    """The app's operations, called by their own names."""

    def name(self, target: Target, operation: str) -> str:
        return operation

    def call(self, target: Target, operation: str, inputs: dict[str, Any]) -> Any:
        """Call the app's operation through the agent's API, whose functions are
        named after the operations."""
        return getattr(api, operation)(**inputs)


def from_environment() -> Direct:
    """The direct route."""
    return Direct()
