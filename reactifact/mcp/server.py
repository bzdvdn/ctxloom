"""MCP server: exposes reactifact `Tool`s as MCP tools, and a `Context`'s
artifacts as MCP resources — so any MCP client (Claude Desktop, Claude Code,
another agent) can call into a running reactifact app. Requires the `mcp`
extra.

Tool schemas come from `Tool.schema` (already a JSON schema — every `Tool`
has one, hand-written or `@tool`-derived). The `mcp` SDK's own `add_tool`
only accepts a plain Python function and derives the schema from its
*signature*, so each `Tool` is bridged through a small function synthesized
from its schema (`exec`, §below) rather than reduced to a single opaque
`**kwargs` parameter — the point of serving these over MCP is that a caller
sees real argument names and types, not a blind bag of kwargs.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .._extras import require_extra
from ..context import Context
from ..tools import Tool

_JSON_TYPE_TO_PY = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
}


def create_mcp_server(
    tools: Sequence[Tool] = (),
    *,
    context: Context | None = None,
    name: str = "reactifact",
    instructions: str = "",
) -> Any:
    """Builds an `mcp.server.mcpserver.MCPServer` exposing `tools`.

    With `context=`, two read-only resources are added so an MCP client can
    inspect a running Context: `context://artifacts/{artifact_type}` (list,
    e.g. `context://artifacts/Answer`) and `context://artifact/{artifact_id}`
    (one artifact, its current data and version).

    Run it with `server.run_stdio_async()`, or mount `server.streamable_http_app()`
    on a FastAPI app alongside `create_trace_router` / `create_chat_router`.
    """
    require_extra("create_mcp_server", "mcp", "mcp")
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(name=name, instructions=instructions or None)
    for t in tools:
        _register_tool(server, t)
    if context is not None:
        _register_context_resources(server, context)
    return server


def _register_tool(server: Any, t: Tool) -> None:
    from mcp.types import ToolAnnotations

    fn = _bridge_function(t)
    annotations = ToolAnnotations(destructive_hint=True) if t.destructive else None
    server.add_tool(fn, name=t.name, description=t.description, annotations=annotations)


def _bridge_function(t: Tool) -> Callable[..., Any]:
    """Synthesizes a real Python function matching `t.schema`'s properties,
    so `add_tool`'s signature-introspection publishes `t`'s actual argument
    names and types instead of one opaque `**kwargs`.
    """
    properties: dict[str, Any] = t.schema.get("properties", {}) or {}
    required = set(t.schema.get("required", []) or [])
    param_names = list(properties.keys())

    params = []
    dict_entries = []
    for pname in param_names:
        json_type = (properties[pname] or {}).get("type")
        py_type = (
            _JSON_TYPE_TO_PY.get(json_type, "Any")
            if isinstance(json_type, str)
            else "Any"
        )
        if pname in required:
            params.append(f"{pname}: {py_type}")
        else:
            params.append(f"{pname}: {py_type} | None = None")
        dict_entries.append(f"{pname!r}: {pname}")
    signature = ", ".join(params)
    call_dict = "{" + ", ".join(dict_entries) + "}"
    src = f"async def _bridge({signature}):\n    return await _call({call_dict})\n"

    async def _call(args: dict[str, Any]) -> Any:
        from mcp.server.mcpserver.exceptions import ToolError

        # optional params default to None above; drop unset ones so `Tool`s
        # with real (non-None) defaults in their own schema see those instead
        args = {k: v for k, v in args.items() if v is not None or k in required}
        result = await t.execute(args)
        if result.error:
            # `ToolError`, not a bare exception: an anticipated `Tool` failure
            # reaches the MCP client as `is_error=True` with this message —
            # any other exception type is masked to "Error executing tool …".
            raise ToolError(result.error)
        return result.data or result.text

    namespace: dict[str, Any] = {"_call": _call, "Any": Any}
    exec(src, namespace)  # noqa: S102 — schema-derived source, no user input
    fn: Callable[..., Any] = namespace["_bridge"]
    fn.__name__ = t.name
    fn.__doc__ = t.description
    return fn


def _register_context_resources(server: Any, context: Context) -> None:
    import json

    async def list_artifacts_resource(artifact_type: str) -> str:
        matches = [
            a
            for a in context.list_artifacts()
            if type(a.data).__name__ == artifact_type
        ]
        return json.dumps(
            [
                {
                    "id": a.id,
                    "type": artifact_type,
                    "version": a.version,
                    "data": a.data.model_dump(),
                }
                for a in matches
            ],
            default=str,
        )

    async def get_artifact_resource(artifact_id: str) -> str:
        artifact = context.get(artifact_id)
        if artifact is None:
            return json.dumps({"error": f"no artifact with id {artifact_id!r}"})
        return json.dumps(
            {
                "id": artifact.id,
                "type": type(artifact.data).__name__,
                "version": artifact.version,
                "data": artifact.data.model_dump(),
            },
            default=str,
        )

    server.resource(
        "context://artifacts/{artifact_type}",
        description="Lists artifacts of one type currently in the Context, newest first.",
    )(list_artifacts_resource)
    server.resource(
        "context://artifact/{artifact_id}",
        description="Reads one artifact by id: its type, version, and current data.",
    )(get_artifact_resource)
