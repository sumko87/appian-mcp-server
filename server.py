"""
Appian CSR Request MCP Server
==============================
An MCP server that exposes Appian CSR Request operations as tools.
Lets you create, retrieve, and delete requests, manage tasks, and view chatter.

Usage:
    uv run server.py                    # stdio transport (for Claude Desktop)
    uv run server.py --transport http   # streamable HTTP (for web clients)
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import httpx
from typing import Any
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration – reads from environment variables
# ---------------------------------------------------------------------------
APPIAN_API_KEY = os.environ.get("APPIAN_API_KEY", "")
APPIAN_BASE_URL = os.environ.get("APPIAN_BASE_URL", "")


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------
def _headers() -> dict[str, str]:
    """Return authorization headers for the Appian API."""
    return {
        "Authorization": f"Bearer {APPIAN_API_KEY}",
        "Content-Type": "application/json",
    }


async def _api_get(path: str, params: dict | None = None) -> dict[str, Any]:
    """Make an authenticated GET request to the Appian API."""
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        url = f"{APPIAN_BASE_URL}{path}"
        resp = await client.get(url, headers=_headers(), params=params)
        resp.raise_for_status()
        return resp.json()


async def _api_post(path: str, body: dict | None = None) -> dict[str, Any]:
    """Make an authenticated POST request to the Appian API."""
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        url = f"{APPIAN_BASE_URL}{path}"
        resp = await client.post(url, headers=_headers(), json=body or {})
        resp.raise_for_status()
        return resp.json()


async def _api_delete(path: str, body: dict | None = None) -> dict[str, Any]:
    """Make an authenticated DELETE request to the Appian API."""
    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        url = f"{APPIAN_BASE_URL}{path}"
        resp = await client.request("DELETE", url, headers=_headers(), json=body)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return {"status": "deleted"}
        return resp.json()


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "Appian CSR Requests",
    instructions=(
        "This server connects to the Appian CSR Request API. "
        "Use these tools to create, retrieve, and delete requests, "
        "manage tasks, and view chatter/event history for requests. "
        "There are four request types: Sponsor ID Creation (21), "
        "Delivery Team (30), PH Trust Accounting (42), and Activate (64)."
    ),
)


# ── 1. CREATE REQUEST ────────────────────────────────────────────────────────
@mcp.tool()
async def create_request(
    header: str,
    detail_key: str,
    detail: str,
) -> str:
    """Create a new request in the Appian CSR system.

    The request body is composed of a header object and exactly one
    request type-specific detail object.

    The header parameter is a JSON string with common request fields.
    Required header fields: RequesterID, RequestTypeID, Subject, Description,
    RequestedDueDate.
    Optional header fields: SFContactID, SponsorName, StatusID, Ordinal,
    IsExpedited, IsActive, relatedObjectTypeId, relatedObjectId, and others.

    Example header:
      {"RequesterID": "user@company.com", "SFContactID": "003xxx",
       "RequestTypeID": 26, "StatusID": 67,
       "Subject": "My Request", "Description": "Details here",
       "Ordinal": 1, "RequestedDueDate": "2026-04-30",
       "IsExpedited": "Standard", "IsActive": true,
       "relatedObjectTypeId": "CLAUDE", "relatedObjectId": 1}

    The detail_key is the name of the request type object, e.g.:
      "iaRequest", "sponsorIdCreationRequest", "deliveryTeamRequest",
      "phTrustAccountingRequest", "activateRequest"

    The detail parameter is a JSON string with type-specific fields.
    Example for iaRequest:
      {"IsActive": true, "IA_Request_Project_Type": "Bug",
       "IA_Request_Issue_Type": "DB Integration Issue",
       "IA_Request_Priority": "High",
       "IA_Owners": "owner@company.com"}

    Args:
        header: JSON string with header fields (RequesterID, RequestTypeID, Subject, etc.).
        detail_key: The request type object key (e.g. "iaRequest", "deliveryTeamRequest").
        detail: JSON string with request type-specific fields.
    """
    header_data = json.loads(header)
    detail_data = json.loads(detail)

    body = {
        "header": header_data,
        detail_key: detail_data,
    }

    data = await _api_post("/csrApiGatewayRequest", body)
    return json.dumps(data, indent=2)


# ── 2. GET REQUEST ───────────────────────────────────────────────────────────
@mcp.tool()
async def get_request(request_id: int) -> str:
    """Get a request by its unique identifier.

    Returns the header (common fields, status, timestamps) and the
    request type-specific detail record with auto-generated identifiers.

    Args:
        request_id: The unique identifier of the request.
    """
    data = await _api_get(f"/csrApiGatewayRequest/{request_id}")
    return json.dumps(data, indent=2)


# ── 3. DELETE REQUEST ────────────────────────────────────────────────────────
@mcp.tool()
async def delete_request(request_id: int, reason: str) -> str:
    """Delete a request by its unique identifier.

    A reason for deletion must be provided.

    Args:
        request_id: The unique identifier of the request to delete.
        reason: Reason for deleting the request.
    """
    body = {"Reason": reason}
    data = await _api_delete(f"/csrApiGatewayRequest/{request_id}", body)
    return json.dumps(data, indent=2)


# ── 4. GET CHATTER ──────────────────────────────────────────────────────────
@mcp.tool()
async def get_chatter(
    request_id: int,
    start_index: int = 1,
    batch_size: int = 50,
) -> str:
    """Get chatter messages (event history) for a request.

    Returns all chatter messages associated with a specific request ID,
    including event types, comments, timestamps, and reply threads.

    Args:
        request_id: The unique identifier of the request.
        start_index: Starting index for pagination (1-indexed, default 1).
        batch_size: Number of records per page (default 50).
    """
    params = {"startIndex": start_index, "batchSize": batch_size}
    data = await _api_get(f"/csrApiGatewayRequest/{request_id}/chatter", params=params)
    return json.dumps(data, indent=2)


# ── 5. GET TASKS FOR REQUEST ────────────────────────────────────────────────
@mcp.tool()
async def get_tasks(
    request_id: int,
    start_index: int = 1,
    batch_size: int = 50,
) -> str:
    """Get all tasks associated with a request.

    Returns task details including name, description, status, assigned
    worker, due date, and completion state.

    Args:
        request_id: The unique identifier of the request.
        start_index: Starting index for pagination (1-indexed, default 1).
        batch_size: Number of records per page (default 50).
    """
    params = {
        "requestId": request_id,
        "startIndex": start_index,
        "batchSize": batch_size,
    }
    data = await _api_get("/csrApiGatewayTasks", params=params)
    return json.dumps(data, indent=2)


# ── 6. GET TASK BY ID ───────────────────────────────────────────────────────
@mcp.tool()
async def get_task(task_id: int) -> str:
    """Get a single task by its unique identifier.

    Returns full task details including name, description, status,
    assigned worker, supervisor, due date, working notes, complexity
    score, and completion state.

    Args:
        task_id: The unique identifier of the task.
    """
    data = await _api_get(f"/csrApiGatewayTasks/{task_id}")
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]

    # When PORT env var is set (e.g. on Render), always use HTTP on that port
    render_port = os.environ.get("PORT")
    if render_port:
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=int(render_port),
        )
    elif transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
