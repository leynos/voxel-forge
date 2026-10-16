"""Executable contract for the MCP protocol surface this release translated.

The tests elsewhere in the suite call the tool functions directly, which
exercises the behaviour but not the *protocol*: it never proves that the
translated instruction text, tool descriptions, and schema reach a client at
all. A description could be dropped, an argument renamed, or the server
instructions left untranslated, and every direct-call test would still pass.

This module drives the real MCP boundary with an in-memory client session, so
the assertions are made against what a client receives over the protocol
rather than against what the Python objects contain. That distinction is the
point: the discovery surface is the protocol's, and only the protocol can
confirm what a client is shown.

Run with ``uv run pytest -q``.
"""

from __future__ import annotations

import asyncio
import typing as typ

import anyio
from mcp.client.session import ClientSession
from mcp.shared.memory import (
    create_client_server_memory_streams,
    create_connected_server_and_client_session,
)

from voxel_forge import server

if typ.TYPE_CHECKING:
    import mcp.types as mcp_types

# Thai script, used to detect text a translation pass missed. The Unicode Thai
# block runs from U+0E00 to U+0E7F; both bounds are named here rather than
# inlined so the intent is readable at the assertion below.
_THAI_START = "฀"
_THAI_END = "๿"

# The tools whose descriptions were translated from Thai in this release. Each
# names itself, so the loop below is a real check that the description reaches
# the client rather than a restatement of the tool name.
_TRANSLATED_DESCRIPTIONS = {
    "voxelforge_create_scene": "Create a new voxel scene",
    "voxelforge_select_scene": "Select the scene being edited",
    "voxelforge_place_block": "Place a single voxel",
    "voxelforge_save": "Save a scene to",
    "voxelforge_load": "Load a scene from a file",
    "voxelforge_about": "Describe VoxelForge",
}


def _fetch_tools() -> list[mcp_types.Tool]:
    """Return the tools one connected client is offered."""

    async def listed() -> list[mcp_types.Tool]:
        async with create_connected_server_and_client_session(server.mcp) as client:
            return list((await client.list_tools()).tools)

    return asyncio.run(listed())


def test_server_instructions_reach_the_client_in_english() -> None:
    """The server-level instructions must arrive, and must not be in Thai.

    These instructions are the client's first description of what the server
    is for, and they are read before any tool is called. An untranslated string
    here would leave a client reasoning about the tool surface in a language it
    was not asked to work in, and nothing else in the suite would notice --
    ``server.mcp`` holds them, but only the protocol shows what a client got.

    The handshake is driven through the raw memory streams rather than through
    ``create_connected_server_and_client_session``, because that helper
    performs ``initialize()`` internally and discards the result. The
    instructions are a field of the initialize *result*, so the session has to
    be built here to observe them.
    """

    async def initialize() -> mcp_types.InitializeResult:
        async with create_client_server_memory_streams() as (
            client_streams,
            server_streams,
        ):
            client_read, client_write = client_streams
            server_read, server_write = server_streams
            # Reaching the low-level server is what the SDK's own in-memory
            # helper does; it has no public accessor for this. The run is
            # driven here rather than through that helper because the helper
            # discards the initialize result this test asserts on.
            lowlevel = server.mcp._mcp_server
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    lambda: lowlevel.run(
                        server_read,
                        server_write,
                        lowlevel.create_initialization_options(),
                    )
                )
                try:
                    async with ClientSession(client_read, client_write) as client:
                        return await client.initialize()
                finally:
                    tg.cancel_scope.cancel()

    result = asyncio.run(initialize())
    instructions = result.instructions or ""

    assert instructions, "the server must send initialization instructions"
    assert "VoxelForge" in instructions, (
        "the instructions must name the server they describe"
    )
    assert not any(_THAI_START <= ch <= _THAI_END for ch in instructions), (
        "the instructions must be translated; Thai script here means the "
        "client is being briefed in the wrong language"
    )


def test_tool_descriptions_reach_the_client_in_english() -> None:
    """Every translated tool description must arrive, in English, over the wire.

    The description is part of the contract because a client chooses which tool
    to call from it. Checking the whole inventory at once also catches a tool
    whose description was translated in the source but dropped from the schema,
    which a direct call cannot detect.
    """
    tools = {tool.name: tool for tool in _fetch_tools()}

    missing = sorted(set(_TRANSLATED_DESCRIPTIONS) - set(tools))
    assert not missing, f"tools absent from the client's inventory: {missing}"

    for name, expected_opening in _TRANSLATED_DESCRIPTIONS.items():
        description = (tools[name].description or "").strip()
        assert description.startswith(expected_opening), (
            f"{name} must describe itself to a client starting with "
            f"{expected_opening!r}; the client reads this to choose the tool"
        )
        assert not any("฀" <= ch <= "๿" for ch in description), (
            f"{name} carries Thai script in the description a client reads"
        )


def test_tool_schemas_expose_the_argument_names_callers_use() -> None:
    """The published schemas must name the arguments the tools accept.

    A renamed or dropped argument is invisible to a direct call -- the function
    signature still accepts it -- but breaks every client that passes it by
    name. ``scene_name`` is checked in particular because the translation pass
    touched the surrounding prose and it is the one argument this suite's
    message contract depends on being addressable.
    """
    tools = {tool.name: tool for tool in _fetch_tools()}

    scene_name_users = [
        "voxelforge_add_layer",
        "voxelforge_set_active_layer",
        "voxelforge_preview",
        "voxelforge_get_info",
        "voxelforge_merge_stats",
        "voxelforge_set_voxel_size",
        "voxelforge_clear",
    ]
    for name in scene_name_users:
        properties = tools[name].inputSchema.get("properties", {})
        assert "scene_name" in properties, (
            f"{name} must publish a scene_name argument, or a client cannot "
            "address a scene by name"
        )

    many = tools["voxelforge_place_many"].inputSchema.get("properties", {})
    assert "blocks_json" in many, (
        "place_many must publish the JSON payload argument under the name its "
        "callers use"
    )


def test_a_tool_schema_change_names_the_scene_argument_as_optional() -> None:
    """``scene_name`` must publish as optional, matching the tools' signatures.

    Every tool that takes a scene name defaults it to the current scene, so a
    schema marking it required would force clients to name a scene they are
    entitled to omit. The default is what makes ``voxelforge_create_scene``
    followed by an unnamed edit a valid sequence.
    """
    tools = {tool.name: tool for tool in _fetch_tools()}

    assert "scene_name" not in tools["voxelforge_preview"].inputSchema.get(
        "required", []
    ), "scene_name must not be required, since the tool defaults it"
    assert "name" in tools["voxelforge_create_scene"].inputSchema.get("required", []), (
        "create_scene must require a name, since it has no current scene to fall "
        "back on"
    )
