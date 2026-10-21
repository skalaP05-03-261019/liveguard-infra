"""Run inside the Compose network with .env supplied (never prints credentials)."""
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4
import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from app.clients.business_mcp import BusinessMcpReadClient, BusinessMcpSettings, AgentToolError

async def main():
    report = {"checks": [], "blockers": []}
    async with httpx.AsyncClient(timeout=10) as http:
        assert (await http.get("http://frontend:8080")).status_code == 200
        assert (await http.get("http://frontend:8080/api/auth/me")).status_code == 401
        assert (await http.get("http://backend:8080/internal/cases/" + str(uuid4()))).status_code == 403
        report["checks"].extend(["frontend serves API build", "nginx forwards session API", "BE rejects missing service token"])
        case = await http.get("http://backend:8080/internal/cases/" + str(uuid4()),
                              headers={"X-Service-Token": os.environ["INTERNAL_SERVICE_TOKEN"]})
        assert case.status_code == 501
        report["blockers"].append({"path": "GET /internal/cases/{id}", "status": case.status_code})
        health = (await http.get("http://agent:8001/health")).json()
        assert health["readyForTasks"] is False
        task_url = "http://agent:8001/agent/tasks/" + str(uuid4())
        assert (await http.get(task_url)).status_code == 401
        assert (await http.get(task_url, headers={"Authorization": "Bearer " + os.environ["AGENT_SERVICE_TOKEN"]})).status_code == 503
        report["checks"].append("Agent authenticates and fails closed without gateway")
        report["blockers"].append({"service": "agent", "health": health})
        rag_health = (await http.get("http://rag-mcp:8003/health")).json()
        assert rag_health["readyForTasks"] is False
        report["blockers"].append({"service": "rag-mcp", "health": rag_health})
        for service, port, name in (("business-mcp", 8002, "BUSINESS_MCP_AGENT_TOKEN"),
                                    ("rag-mcp", 8003, "RAG_MCP_AGENT_TOKEN")):
            url = f"http://{service}:{port}/mcp"
            assert (await http.post(url, json={})).status_code == 401
            async with create_mcp_http_client(headers={"Authorization": "Bearer " + os.environ[name]}) as client:
                async with Client(streamable_http_client(url, http_client=client)) as mcp:
                    tools = await mcp.list_tools()
                    assert tools
                    report["checks"].append(f"{service} real MCP handshake and tools/list; anonymous blocked")
        business = BusinessMcpReadClient(BusinessMcpSettings("http://business-mcp:8002/mcp", os.environ["BUSINESS_MCP_AGENT_TOKEN"]))
        try:
            await business.call("get_chat_context", {"caseId": str(uuid4()), "traceId": str(uuid4())})
            raise AssertionError("Random absent case must not fabricate context")
        except AgentToolError as error:
            assert error.code == "NOT_FOUND", error.code
        report["checks"].append("Agent SDK → Business MCP → real BE context query (absent case NOT_FOUND)")
        for name, expected in (("get_moderation_case", "NOT_IMPLEMENTED"),
                               ("get_security_facts", "NOT_IMPLEMENTED"),
                               ("get_user_history", "NOT_IMPLEMENTED"),
                               ("get_stream_info", "NOT_FOUND"),
                               ("get_official_links", "NOT_FOUND")):
            try:
                await business.call(name, {"caseId": str(uuid4()), "traceId": str(uuid4())})
                raise AssertionError("Absent/unimplemented case must not fabricate a response")
            except AgentToolError as error:
                assert error.code == expected, (name, error.code)
        report["checks"].append("dedicated BE routes return their real NOT_IMPLEMENTED/NOT_FOUND errors instead of obsolete view= 400")
    report["status"] = "PASS_WITH_BACKEND_BLOCKERS"
    destination = Path("/integration/evidence/services.json")
    destination.parent.mkdir(exist_ok=True, parents=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))

asyncio.run(main())
