import os

import boto3
import httpx
from botocore.auth import SigV4Auth as BotocoreSigV4Auth
from botocore.awsrequest import AWSRequest
from langchain_mcp_adapters.client import MultiServerMCPClient


class SigV4Auth(httpx.Auth):
    """Sign each request with AWS Signature Version 4, as boto3 does for its own calls."""

    requires_request_body = True

    def __init__(self, session: boto3.Session, service: str = "bedrock-agentcore"):
        self.credentials = session.get_credentials()
        self.region = session.region_name
        self.service = service

    def auth_flow(self, request: httpx.Request):
        headers = {"Host": request.url.netloc.decode(), "Content-Type": request.headers.get("content-type", "")}
        aws_request = AWSRequest(method=request.method, url=str(request.url), data=request.content, headers=headers)
        BotocoreSigV4Auth(self.credentials.get_frozen_credentials(), self.service, self.region).add_auth(aws_request)
        for name in ("Authorization", "X-Amz-Date", "X-Amz-Security-Token"):
            if name in aws_request.headers:
                request.headers[name] = aws_request.headers[name]
        yield request


def get_streamable_http_mcp_client() -> MultiServerMCPClient | None:
    """Returns an MCP client for the UnderCover gateway, or None when no gateway is configured.

    Requests are signed with the credentials of whoever runs the agent: your own on
    your machine, the runtime's execution role on AgentCore.
    """
    gateway_url = os.getenv("UNDERCOVER_GATEWAY_URL")
    if not gateway_url:
        return None
    return MultiServerMCPClient(
        {
            "undercover_gateway": {
                "transport": "streamable_http",
                "url": gateway_url,
                "auth": SigV4Auth(boto3.Session()),
            }
        }
    )
