"""Executable contract for the MCP tool responses that are documents, not prose.

Most tool confirmations are one English sentence, and the sentence is the
contract. A few are not: ``voxelforge_list_scenes``,
``voxelforge_get_info``, and ``voxelforge_default_palette`` return JSON;
``voxelforge_preview`` returns a summary plus an ASCII rendering; and the
statistics and editor tools return several labelled lines. A client parses
those instead of reading them.

That distinction is what this module guards, and it is a separate concern from
``test_mcp_inventory.py``, which checks what a client is *offered* -- the
instructions, descriptions, and schemas. The split is not cosmetic: the two
fail independently. A description can be right while the payload it describes
is the wrong shape, and a payload can be the right shape while its description
is missing. Keeping them in one module also pushed it past the project's file
size limit, which is a fair sign they were two responsibilities.

Run with ``uv run pytest -q``.
"""

from __future__ import annotations

import asyncio
import json
import typing as typ

from mcp.shared.memory import create_connected_server_and_client_session
from mcp_wire_helpers import call_scene_tool, wire_text

from voxel_forge import server

if typ.TYPE_CHECKING:
    from pathlib import Path

# The scene these tests create over the protocol. Named here so the
# precondition a real client would set up is stated once.
_SCENE = "response-scene"


def test_list_scenes_returns_both_listings_as_structured_data(
    scene_directory: Path,
) -> None:
    """``list_scenes`` must deliver its two listings as parseable JSON.

    This is the only tool whose confirmation is a *document* rather than a
    sentence, and the JSON shape is the contract a client parses -- so a
    regression that turned it back into prose, dropped a key, or concatenated
    the two listings would leave every direct-call test passing. Asserting on
    the parsed payload rather than on the raw string is what makes the check
    about the contract rather than about whitespace.

    Both listings are established for real: a scene registered in the session
    and a file written to the temporary scene directory by the tool itself. A
    test that stubbed either side would not prove the tool reads both.
    """

    async def listing() -> str:
        """Create and save a scene, then return the list_scenes response text."""
        async with create_connected_server_and_client_session(server.mcp) as client:
            created = await client.call_tool(
                "voxelforge_create_scene", {"name": _SCENE}
            )
            assert created.isError is False, "create_scene must succeed"
            saved = await client.call_tool("voxelforge_save", {"scene_name": _SCENE})
            assert saved.isError is False, "save must succeed"
            return wire_text(await client.call_tool("voxelforge_list_scenes", {}))

    payload = json.loads(asyncio.run(listing()))

    assert set(payload) == {"active_session", "saved_on_disk"}, (
        "a client parses these two keys by name; a renamed or extra key breaks "
        "every reader of the listing"
    )
    assert payload["active_session"] == [_SCENE], (
        "a scene created in this session must be listed as active"
    )
    assert payload["saved_on_disk"] == [_SCENE], (
        "a scene saved through the tool must appear in the on-disk listing"
    )
    assert scene_directory.is_dir(), (
        "the on-disk listing must have read the temporary scene directory, not "
        "a developer's real ~/.voxel-forge"
    )


def test_default_palette_returns_the_palette_as_structured_data() -> None:
    """``default_palette`` must deliver the palette, as JSON, over the wire.

    The response is JSON rather than prose, so a client parses it and the
    values matter as much as the shape. Comparing against
    ``server.DEFAULT_PALETTE`` rather than against a literal copy makes the
    test fail when the palette changes *and* the response does not follow --
    which is the drift it exists to catch. A hard-coded literal would instead
    have to be edited in step with the palette, and would then pass whatever
    the tool returned.
    """

    async def palette_over_the_wire() -> str:
        """Return the default palette tool response, as text, from the server."""
        async with create_connected_server_and_client_session(server.mcp) as client:
            return wire_text(await client.call_tool("voxelforge_default_palette", {}))

    payload = json.loads(asyncio.run(palette_over_the_wire()))
    expected = {key: list(value) for key, value in server.DEFAULT_PALETTE.items()}

    assert payload == expected, (
        "the palette a client receives must be the server's current palette; "
        "a stale or partial copy would silently change exported colours"
    )


def test_get_info_returns_the_scene_as_json() -> None:
    """``get_info`` must deliver scene state as JSON, not as a sentence.

    Its sibling ``default_palette`` returns a document with no scene involved,
    so it cannot catch a regression in how a *scene* is serialized. This test
    creates one over the protocol and reads it back the same way, which is what
    makes the round trip a client would actually perform.
    """
    result = call_scene_tool(_SCENE, "voxelforge_get_info", {"scene_name": _SCENE})
    assert result.isError is False, "get_info must succeed for a created scene"

    payload = json.loads(wire_text(result))

    assert isinstance(payload, dict), (
        "a client parses this response, so an object is the contract; prose "
        "here would fail json.loads on every caller"
    )
    assert payload["name"] == _SCENE, (
        "the document must describe the scene that was asked for"
    )
    assert "layers" in payload, (
        "the scene document must carry its layers, or a client cannot read the "
        "structure it just created"
    )
