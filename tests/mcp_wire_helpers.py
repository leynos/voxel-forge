"""Helpers for assertions made against the MCP protocol rather than the Python API.

The boundary tests drive a real in-memory MCP client session, so what they
assert on is what a client receives: a list of content blocks per call, a list
of tool descriptors per listing. This module holds the readers those tests
share, so each test module states its own claims without restating how the
protocol wraps them.

Keeping these here rather than in ``conftest.py`` is deliberate. They are not
fixtures -- they build no state and restore nothing -- and putting them in the
plugin namespace would make them available to modules that do not touch the
protocol, which is how a helper ends up used somewhere it does not belong.
"""

from __future__ import annotations

import asyncio
import typing as typ

from mcp.shared.memory import create_connected_server_and_client_session

from voxel_forge import server

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import mcp.types as mcp_types


def wire_text(result: mcp_types.CallToolResult) -> str:
    """Return the text a client received from a tool call, as one string.

    The SDK delivers a tool's return value as a list of content blocks, so the
    client-visible text is their concatenation rather than any single block.
    Reading them here keeps the callers asserting on what a caller reads rather
    than on the block structure that happens to carry it.

    Parameters
    ----------
    result : mcp.types.CallToolResult
        The result of ``ClientSession.call_tool``.

    Returns
    -------
    str
        The concatenated ``text`` of every content block; blocks without a
        ``text`` attribute contribute nothing.

    Examples
    --------
    >>> from mcp.types import CallToolResult, TextContent
    >>> result = CallToolResult(
    ...     content=[TextContent(type="text", text="ok")], isError=False
    ... )
    >>> wire_text(result)
    'ok'
    """
    return "".join(getattr(block, "text", "") for block in result.content)


def fetch_tools() -> list[mcp_types.Tool]:
    """Return the tools one connected client is offered.

    Returns
    -------
    list[mcp.types.Tool]
        The tool descriptors returned by ``list_tools``, in the order the
        server sent them.

    Examples
    --------
    >>> any(t.name == "voxelforge_preview" for t in fetch_tools())
    True
    """

    async def listed() -> list[mcp_types.Tool]:
        async with create_connected_server_and_client_session(server.mcp) as client:
            return list((await client.list_tools()).tools)

    return asyncio.run(listed())


def call_scene_tool(
    scene_name: str,
    tool: str,
    arguments: cabc.Mapping[str, typ.Any],
) -> mcp_types.CallToolResult:
    """Create ``scene_name`` over the protocol, then call ``tool`` on it.

    Every response-shape test needs the same precondition: a scene that exists
    *in the session the client is talking to*. Creating it through the client
    rather than through ``server.store`` is what makes the round trip a real
    one -- a scene registered behind the protocol's back would prove the tool
    reads a store, not that a caller can establish the state it then reads.

    ``arguments`` are passed to the tool verbatim. A tool that addresses a
    scene by name gets it as usual; a tool that acts on the current scene omits
    it, because ``create_scene`` has just made the new scene current. Either
    way the scene under test is one this helper created.

    The result is returned rather than reduced to text so the caller can assert
    on ``isError`` -- a failure test needs to know the call failed, and a text
    reader would otherwise have to infer it from an empty string.

    Parameters
    ----------
    scene_name : str
        Name of the scene to create before the call.
    tool : str
        Name of the tool to call afterwards.
    arguments : collections.abc.Mapping[str, typing.Any]
        Named arguments passed to ``tool`` unchanged; include ``scene_name``
        when an explicit scene target is needed.

    Returns
    -------
    mcp.types.CallToolResult
        The result of the tool call; ``isError`` reports whether it failed.

    Examples
    --------
    >>> result = call_scene_tool("demo", "voxelforge_get_info", {"scene_name": "demo"})
    >>> result.isError
    False
    """

    async def flow() -> mcp_types.CallToolResult:
        async with create_connected_server_and_client_session(server.mcp) as client:
            created = await client.call_tool(
                "voxelforge_create_scene", {"name": scene_name}
            )
            assert created.isError is False, "create_scene must succeed"
            return await client.call_tool(tool, dict(arguments))

    return asyncio.run(flow())
