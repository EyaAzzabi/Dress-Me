"""MCP client for the DressMe Purchase server (stdio)."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BACKEND = Path(__file__).resolve().parents[2]


def server_params() -> StdioServerParameters:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND) + os.pathsep + env.get("PYTHONPATH", "")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp.purchase_server"],
        cwd=str(BACKEND),
        env=env,
    )


class PurchaseMCPClient:
    def __init__(self, session: ClientSession) -> None:
        self.session = session

    async def list_tools(self) -> list[Any]:
        result = await self.session.list_tools()
        return list(result.tools)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return await self.session.call_tool(name, arguments or {})


@asynccontextmanager
async def open_session():
    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield PurchaseMCPClient(session)
