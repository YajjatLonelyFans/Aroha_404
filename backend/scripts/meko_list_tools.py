"""List the tools exposed by Meko's hosted MCP server (Stage 5 spike).

Usage (from backend/, venv active):  python -m scripts.meko_list_tools
Prints each tool's name, description and input schema. Never prints the API key.
"""

import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from app.core.settings import get_settings, is_configured


async def main() -> int:
    s = get_settings()
    if not is_configured(s.meko_api_key):
        print("MEKO_API_KEY is not set in .env")
        return 1
    headers = {"Authorization": f"Bearer {s.meko_api_key}"}
    async with (
        create_mcp_http_client(headers=headers) as http,
        streamable_http_client(s.meko_mcp_url, http_client=http) as (read, write),
        ClientSession(read, write) as session,
    ):
        info = (await session.initialize()).model_dump(by_alias=True)
        server = info.get("serverInfo") or {}
        print(f"Connected to {server.get('name')} {server.get('version')} (protocol {info.get('protocolVersion')})")
        if info.get("instructions"):
            print(f"\nServer instructions:\n{info['instructions']}\n")
        tools = [t.model_dump(by_alias=True) for t in (await session.list_tools()).tools]
        print(f"{len(tools)} tools:\n")
        for t in tools:
            print(f"## {t['name']}\n{(t.get('description') or '').strip()}")
            print(json.dumps(t.get("inputSchema"), indent=1))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
