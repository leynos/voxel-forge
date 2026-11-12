"""Executable contract for the tool surface a client is offered.

The tests elsewhere in the suite call the tool functions directly, which
exercises the behaviour but not the *discovery* surface: it never proves that
the translated instruction text, tool descriptions, and schema reach a client
at all. A description could be dropped, an argument renamed, or the server
instructions left untranslated, and every direct-call test would still pass.

This module drives the real MCP boundary for exactly that claim. What a call
*returns* is a different claim, checked in ``test_mcp_boundary.py`` (prose that
must survive the wire unchanged) and ``test_mcp_responses.py`` (the tools whose
reply is a document rather than a sentence).

Run with ``uv run pytest -q``.
"""

from __future__ import annotations

import asyncio
import typing as typ

import anyio
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from mcp_wire_helpers import fetch_tools

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
#
# The table lists every tool the branch touched, not a sample. All 27 were
# translated -- the voice, tone, and wording of each description is
# client-visible text that a language model reads before choosing a tool, and
# a sampling check would leave the untested remainder free to regress to Thai.
# A tool added to the server without a row here is caught by
# ``test_every_published_tool_is_covered_by_the_description_table`` below.
_TRANSLATED_DESCRIPTIONS = {
    "voxelforge_about": "Describe VoxelForge and its relationship to Goxel.",
    "voxelforge_add_layer": "Add a new layer (as in Goxel).",
    "voxelforge_build_chibi_bear": (
        "Build a chibi bear statue (resolution 2-4 recommended)."
    ),
    "voxelforge_build_tree": "Build a procedural tree at an adjustable resolution.",
    "voxelforge_clear": "Clear every voxel in every layer.",
    "voxelforge_create_scene": "Create a new voxel scene.",
    "voxelforge_default_palette": "Return the default colour palette.",
    "voxelforge_export_obj": "Export to Wavefront .obj",
    "voxelforge_export_obj_legacy": "Export to Wavefront .obj (as supported by Goxel).",
    "voxelforge_export_roblox_merged": "Export Luau for Roblox",
    "voxelforge_export_vox": "Export to .vox (opens in Goxel / MagicaVoxel).",
    "voxelforge_fill_box": "Fill a 3D box",
    "voxelforge_get_info": "Scene information as JSON.",
    "voxelforge_import_vox": (
        "Import a .vox file (the MagicaVoxel / Goxel export format)."
    ),
    "voxelforge_launch_editor": "Open the VoxelForge web editor in the browser",
    "voxelforge_list_scenes": (
        "List the scenes in this session and the scenes saved to disk."
    ),
    "voxelforge_load": "Load a scene from a file.",
    "voxelforge_merge_stats": "See how much merging voxels into boxes saves",
    "voxelforge_place_block": "Place a single voxel at grid coordinates (x,y,z).",
    "voxelforge_place_many": "Place many voxels from a JSON array.",
    "voxelforge_preview": "Show a summary plus an ASCII view of each Y slice",
    "voxelforge_remove_block": "Remove the voxel at the given coordinates.",
    "voxelforge_save": "Save a scene to",
    "voxelforge_select_scene": "Select the scene being edited.",
    "voxelforge_set_active_layer": "Set the active layer (0-based index).",
    "voxelforge_set_palette": "Set a palette colour (24-bit RGB).",
    "voxelforge_set_voxel_size": "Set the voxel size in world units",
}


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
        """Run the MCP initialize handshake and return the server's result."""
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
    tools = {tool.name: tool for tool in fetch_tools()}

    missing = sorted(set(_TRANSLATED_DESCRIPTIONS) - set(tools))
    assert not missing, f"tools absent from the client's inventory: {missing}"

    for name, expected_opening in _TRANSLATED_DESCRIPTIONS.items():
        description = (tools[name].description or "").strip()
        assert description.startswith(expected_opening), (
            f"{name} must describe itself to a client starting with "
            f"{expected_opening!r}; the client reads this to choose the tool"
        )
        assert not any(_THAI_START <= ch <= _THAI_END for ch in description), (
            f"{name} carries Thai script in the description a client reads"
        )


def test_every_published_tool_is_covered_by_the_description_table() -> None:
    """The description table must cover every tool the client is offered.

    The loop above can only check the rows it is given, so a tool published
    without a row would be untested rather than failing. This asserts the two
    sets are equal, which is what makes the table a specification of the tool
    surface rather than a snapshot of whichever rows someone remembered.

    The converse direction matters too: a row naming a tool the server does
    not publish would silently pass the ``missing`` check while claiming
    coverage of something a client cannot call.
    """
    published = set(_TRANSLATED_DESCRIPTIONS)
    advertised = {tool.name for tool in fetch_tools()}

    assert not advertised - published, (
        "these tools are advertised to clients but have no description row, "
        f"so nothing checks their translated text: {sorted(advertised - published)}"
    )
    assert not published - advertised, (
        "these rows name tools the server does not publish, so they check "
        f"nothing: {sorted(published - advertised)}"
    )


def test_tool_schemas_expose_the_argument_names_callers_use() -> None:
    """The published schemas must name the arguments the tools accept.

    A renamed or dropped argument is invisible to a direct call -- the function
    signature still accepts it -- but breaks every client that passes it by
    name. ``scene_name`` is checked in particular because the translation pass
    touched the surrounding prose and it is the one argument this suite's
    message contract depends on being addressable.
    """
    tools = {tool.name: tool for tool in fetch_tools()}

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
    tools = {tool.name: tool for tool in fetch_tools()}

    assert "scene_name" not in tools["voxelforge_preview"].inputSchema.get(
        "required", []
    ), "scene_name must not be required, since the tool defaults it"
    assert "name" in tools["voxelforge_create_scene"].inputSchema.get("required", []), (
        "create_scene must require a name, since it has no current scene to fall "
        "back on"
    )
