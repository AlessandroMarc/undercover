"""How the tests' stand-in for the agent on the laptop answers when it doesn't take
the work: it can't be reached, it times out, it refuses, or it gives an error
answer."""

import httpx


def unreachable(request):
    raise httpx.ConnectError("Connection refused")


def slow(request):
    raise httpx.ReadTimeout("Timed out")


def refusing(request):
    refusal = "Claim CLM-1002 isn't paused for a handler"
    return httpx.Response(200, json={"refused": refusal})


def broken(request):
    return httpx.Response(500, json={"error": "The agent couldn't get ready"})
