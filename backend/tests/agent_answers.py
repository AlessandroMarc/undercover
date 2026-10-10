"""How the tests' stand-in for the agent answers the backend's calls when the agent
doesn't take the work."""

import httpx


def unreachable(request):
    raise httpx.ConnectError("Connection refused")


def slow(request):
    raise httpx.ReadTimeout("Timed out")


def refusing(request):
    detail = "Claim CLM-1002 isn't paused for a handler"
    return httpx.Response(409, json={"detail": detail})


def broken(request):
    return httpx.Response(500, text="Internal Server Error")
