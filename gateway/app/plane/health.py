"""Direct, read-only Plane connectivity check.

This is the ONE place allowed to call Plane's REST API directly instead of
through MCP -- design rule 2.2 explicitly carves out "health checking,
bootstrap validation, connectivity checks" as acceptable direct-API uses.
Business-level questions ("list my projects") must never go through here.
"""

from __future__ import annotations

import httpx

from app.config import Settings


async def check_plane(settings: Settings) -> bool:
    if not settings.plane_is_configured():
        return False
    base_url = settings.plane_internal_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{base_url}/api/v1/users/me/",
                headers={"x-api-key": settings.plane_api_key},
            )
            return response.status_code == 200
    except httpx.HTTPError:
        return False


async def check_plane_mcp(settings: Settings) -> bool:
    """The MCP server has no unauthenticated liveness route, so a GET against
    the header-auth MCP path is used purely as a "process is up and speaking
    HTTP" probe: any response (even 405/401) means it's alive, only a
    connection-level failure means it's down."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get(settings.plane_mcp_url)
            return True
    except httpx.HTTPError:
        return False
