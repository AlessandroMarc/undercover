"""The UnderCover Agent on AgentCore Runtime.

Each Runtime session runs the agent's own service, agent.service:app, inside its
microVM, as npm run dev runs it on the laptop, and passes it the request the app sent:
{"path": "/dispatches", "body": {"agents": 25}}. The answer is the service's status
code and JSON. Runtime counts the session as busy until the service's work is done, so
the session carries on after it has replied, until the dispatch or evaluation is done.

On its first request, a session reseeds Python's random numbers, fetches each of the
project's credentials from AgentCore Identity into the environment variable of the
same name, and starts the service, which opens its pool. None of this happens at
import: on platform version V2, every session starts from a snapshot taken after the
import, so anything made at import would be shared by every session.
"""

import os
import random
import re
import threading
import time
from functools import cache
from typing import Any

import httpx
import uvicorn
from bedrock_agentcore.identity.auth import requires_api_key
from bedrock_agentcore.runtime import BedrockAgentCoreApp, PingStatus

from agent.service import app as service

# The agent's service in the session, on the port npm run dev gives it on the laptop
SERVICE_PORT = 8002
# The CLI names each credential's provider in AGENTCORE_CREDENTIAL_<NAME>_NAME
CREDENTIAL = re.compile(r"AGENTCORE_CREDENTIAL_(\w+)_NAME")

app = BedrockAgentCoreApp()


class Busy:
    """The agent's service, counting its requests while they run, including the work a
    request carries on with after its reply."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.running = 0

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":  # the service's startup and shutdown
            await self.inner(scope, receive, send)
            return
        self.running += 1
        try:
            await self.inner(scope, receive, send)
        finally:
            self.running -= 1


busy = Busy(service)
_starting = threading.Lock()


def fetch(provider_name: str) -> str:
    """A credential's value from AgentCore Identity."""

    @requires_api_key(provider_name=provider_name)
    def value(api_key: str) -> str:
        return api_key

    return value()  # pyright: ignore[reportCallIssue]  the decorator passes api_key


@cache
def start_service() -> httpx.Client:
    """Reseed, fetch the secrets, start the agent's service and wait until it's up,
    once in a session."""
    # Sessions restored from one V2 snapshot would otherwise share random numbers
    random.seed()
    for name, provider_name in list(os.environ.items()):
        if match := CREDENTIAL.fullmatch(name):
            os.environ[match.group(1)] = fetch(provider_name)
    config = uvicorn.Config(
        busy, host="127.0.0.1", port=SERVICE_PORT, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            raise RuntimeError(
                "The agent's service didn't start: see the runtime's log"
            )
        time.sleep(0.1)
    # The service may check for the agent's key, as it does on a host of its own
    headers = {"X-API-Key": os.environ.get("UNDERCOVER_API_KEY", "")}
    return httpx.Client(
        base_url=f"http://127.0.0.1:{SERVICE_PORT}/api", headers=headers, timeout=60
    )


def agent_service() -> httpx.Client:
    """A client for the session's agent service, started on the first request."""
    with _starting:
        return start_service()


@app.ping
def ping() -> PingStatus:
    """Busy while the agent's service is working, so Runtime keeps the session."""
    return PingStatus.HEALTHY_BUSY if busy.running else PingStatus.HEALTHY


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any) -> dict[str, Any]:
    """Pass one request from the app to the agent's service, and return its answer."""
    method = payload.get("method", "POST")
    response = agent_service().request(
        method, payload["path"], json=payload.get("body")
    )
    return {"status": response.status_code, "body": response.json()}


if __name__ == "__main__":
    app.run()
