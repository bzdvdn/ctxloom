"""MCP client: turns tools exposed by an external MCP server into `Tool`s, so
`ToolUse`/`ToolUseHITL`/`LLMAgent` call remote MCP tools the same way they
call local ones — no separate code path for "MCP tool" vs. `@tool`. Requires
the `mcp` extra.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from .._extras import require_extra
from ..tools import Tool, ToolOutput


class MCPTool(Tool):
    """One tool from a connected `mcp.ClientSession`, wrapped as a `Tool`."""

    def __init__(
        self,
        session: Any,
        *,
        name: str,
        description: str,
        schema: dict[str, Any],
        destructive: bool = False,
    ):
        self._session = session
        self.name = name
        self.description = description
        self.schema = schema
        self.destructive = destructive

    async def execute(self, args: dict[str, Any]) -> ToolOutput:
        result = await self._session.call_tool(self.name, args)
        return _to_tool_output(result)


def _to_tool_output(result: Any) -> ToolOutput:
    texts = [block.text for block in result.content if getattr(block, "text", None)]
    text = "\n".join(texts)
    if result.is_error:
        return ToolOutput(text=text, error=text or "MCP tool call failed")
    data = dict(result.structured_content) if result.structured_content else {}
    return ToolOutput(text=text, data=data)


async def mcp_tools(session: Any) -> list[Tool]:
    """Lists tools on a connected, initialized `mcp.ClientSession` and wraps each as a `Tool`."""
    listed = await session.list_tools()
    return [
        MCPTool(
            session,
            name=t.name,
            description=t.description or t.name,
            schema=t.input_schema,
            destructive=bool(t.annotations and t.annotations.destructive_hint),
        )
        for t in listed.tools
    ]


@asynccontextmanager
async def mcp_stdio_tools(
    command: str,
    args: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
) -> AsyncGenerator[list[Tool], None]:
    """Spawns an MCP server over stdio and yields its tools as `Tool`s.

    Example: `mcp_stdio_tools("npx", ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])`.
    The connection stays open for the `async with` block; tools called after
    it exits will fail.
    """
    require_extra("mcp_stdio_tools", "mcp", "mcp")
    from mcp.client.stdio import StdioServerParameters, stdio_client

    from mcp import ClientSession

    params = StdioServerParameters(command=command, args=args or [], env=env)
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield await mcp_tools(session)


@asynccontextmanager
async def mcp_http_tools(url: str) -> AsyncGenerator[list[Tool], None]:
    """Connects to an MCP server over streamable HTTP and yields its tools as `Tool`s."""
    require_extra("mcp_http_tools", "mcp", "mcp")
    from mcp.client.streamable_http import streamable_http_client

    from mcp import ClientSession

    async with (
        streamable_http_client(url) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield await mcp_tools(session)
