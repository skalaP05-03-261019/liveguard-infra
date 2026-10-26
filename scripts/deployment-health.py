"""Read-only probes executed inside the deployed Agent image; never calls a model."""
import asyncio
import json
import logging
import os
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

logging.disable(logging.CRITICAL)


def require_policy_versions(body: dict, active: str) -> None:
    required = {"v3.1", "v3.2", active}
    if not required.issubset(body.get("indexedPolicyVersions", [])):
        raise RuntimeError("RAG must index both v3.1 and v3.2 and the active policy version")


def endpoint(url: str, status: int = 200) -> bytes:
    try:
        with urlopen(url, timeout=5) as response:
            actual, body = response.status, response.read()
    except HTTPError as error:
        actual, body = error.code, error.read()
    if actual != status:
        raise RuntimeError(f"Unexpected HTTP status at {url}: {actual}")
    return body


async def check() -> None:
    from app.clients.business_mcp import AgentToolError, BusinessMcpReadClient, BusinessMcpSettings
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client

    endpoint("http://frontend:8080")
    endpoint("http://frontend:8080/api/auth/me", 401)
    endpoint("http://backend:8080/api/auth/me", 401)
    endpoint("http://business-mcp:8002/ready")
    for name in ("business-mcp-1", "business-mcp-2"):
        endpoint(f"http://{name}:8002/ready")
    for service, port in (("agent", 8001), ("rag-mcp", 8003)):
        body = json.loads(endpoint(f"http://{service}:{port}/health"))
        if body.get("readyForTasks") is not True:
            raise RuntimeError(f"{service}: readyForTasks is not true")
        if service == "rag-mcp":
            require_policy_versions(body, os.environ["DEPLOYMENT_POLICY_VERSION"])
    for service, port, token in (
        ("business-mcp", 8002, "BUSINESS_MCP_AGENT_TOKEN"),
        ("rag-mcp", 8003, "RAG_MCP_AGENT_TOKEN"),
    ):
        async with create_mcp_http_client(
            headers={"Authorization": "Bearer " + os.environ[token]}
        ) as http:
            async with Client(streamable_http_client(
                f"http://{service}:{port}/mcp", http_client=http
            )) as client:
                if not await client.list_tools():
                    raise RuntimeError(f"{service}: no tools registered")
    for service in ("business-mcp", "business-mcp-1", "business-mcp-2"):
        client = BusinessMcpReadClient(BusinessMcpSettings(
            f"http://{service}:8002/mcp", os.environ["BUSINESS_MCP_AGENT_TOKEN"]))
        try:
            await client.call("get_moderation_case", {
                "caseId": str(uuid4()), "traceId": str(uuid4())})
        except AgentToolError as error:
            if error.code != "NOT_FOUND":
                raise RuntimeError(f"{service}: authenticated Backend probe failed ({error.code})") from None
        else:
            raise RuntimeError(f"{service}: nonexistent case unexpectedly found")
    print("PASS: frontend, Backend, Agent/RAG readiness, MCP authentication and Backend connectivity")


if __name__ == "__main__":
    try:
        asyncio.run(check())
    except Exception as error:
        # HTTP/SDK exceptions may contain credentials, response bodies or tool inputs.
        if isinstance(error, RuntimeError):
            print("HEALTH_ERROR: " + str(error))
        else:
            print(f"HEALTH_ERROR: {type(error).__name__}; sensitive details withheld")
        raise SystemExit(1) from None
