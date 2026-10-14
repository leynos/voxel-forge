"""Guard the public MCP inventory after splitting registration across modules."""

import asyncio

from mcp.shared.memory import create_connected_server_and_client_session

from voxel_forge import server

EXPECTED_TOOLS = frozenset({
    "voxelforge_about",
    "voxelforge_create_scene",
    "voxelforge_select_scene",
    "voxelforge_add_layer",
    "voxelforge_set_active_layer",
    "voxelforge_set_palette",
    "voxelforge_preview",
    "voxelforge_get_info",
    "voxelforge_merge_stats",
    "voxelforge_set_voxel_size",
    "voxelforge_default_palette",
    "voxelforge_launch_editor",
    "voxelforge_place_block",
    "voxelforge_place_many",
    "voxelforge_fill_box",
    "voxelforge_remove_block",
    "voxelforge_clear",
    "voxelforge_build_tree",
    "voxelforge_build_chibi_bear",
    "voxelforge_save",
    "voxelforge_load",
    "voxelforge_list_scenes",
    "voxelforge_import_vox",
    "voxelforge_export_vox",
    "voxelforge_export_obj",
    "voxelforge_export_obj_legacy",
    "voxelforge_export_roblox_merged",
})


def test_split_modules_preserve_registered_tools_and_public_facade() -> None:
    """An MCP client and Python callers must retain the entire tool inventory."""

    async def registered_names() -> set[str]:
        """Inspect the tool inventory through the protocol client."""
        async with create_connected_server_and_client_session(server.mcp) as client:
            result = await client.list_tools()
            return {tool.name for tool in result.tools}

    assert asyncio.run(registered_names()) == EXPECTED_TOOLS, (
        "all established tools must remain registered after the module split"
    )
    assert all(callable(getattr(server, name, None)) for name in EXPECTED_TOOLS), (
        "Python callers must retain each callable on the server facade"
    )
