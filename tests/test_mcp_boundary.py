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
from voxel_forge.model import SceneStore

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    import mcp.types as mcp_types

    # Annotates ``_server_globals``. ``SceneStore`` above stays a runtime
    # import because ``test_a_confirmation_crosses_the_boundary_unchanged``
    # builds a second store directly, which is what makes its comparison a
    # protocol-versus-direct one rather than a comparison against a fixture.
    from voxel_forge.model import VoxelScene

# The scene the boundary tests establish over the protocol, and a name they
# deliberately ask for and do not have. Named here so the precondition a real
# client would set up is stated once rather than repeated per test.
_SCENE = "boundary-scene"
_ABSENT = "absent"

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


def _server_globals() -> tuple[SceneStore, cabc.Callable[[VoxelScene], None]]:
    """Return the registry and bridge notifier exactly as this module found them.

    Read once at import time, before any test in this file replaces either.
    The final test below compares against what this returned, which is why it
    has to be the last test here: it reports what the tests above it left
    behind.
    """
    return server.store, server._sync_bridge


_INITIAL_STORE, _INITIAL_SYNC_BRIDGE = _server_globals()


def _wire_text(result: mcp_types.CallToolResult) -> str:
    """Return the text a client received from a tool call, as one string.

    The SDK delivers a tool's return value as a list of content blocks, so the
    client-visible text is their concatenation rather than any single block.
    Reading them here keeps the tests below asserting on what a caller reads
    rather than on the block structure that happens to carry it.
    """
    return "".join(getattr(block, "text", "") for block in result.content)


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


def test_a_confirmation_crosses_the_boundary_unchanged(
    empty_server_store: SceneStore,
) -> None:
    """The text a caller acts on must survive the protocol, not just the call.

    Every other message test in the suite calls the tool function directly and
    asserts on its return value. That proves what the function *computes*; it
    does not prove the string reaches a client, and the two are different
    claims -- a response could be rewritten, truncated, or dropped by the
    protocol layer while the direct call stayed correct.

    The text is compared byte-for-byte across both surfaces rather than
    asserted against a fresh literal, so the test fails if the two ever
    disagree in either direction. The scene is created through the *client*
    for the same reason: it is the precondition a real caller would establish,
    and it exercises the round trip that the edit tools then read back.
    """

    async def exchange() -> tuple[str, str]:
        """Place one voxel over the wire and the same one directly."""
        async with create_connected_server_and_client_session(server.mcp) as client:
            created = await client.call_tool(
                "voxelforge_create_scene", {"name": _SCENE}
            )
            assert created.isError is False, "create_scene must succeed"
            return _wire_text(
                await client.call_tool(
                    "voxelforge_place_block",
                    {"x": 0, "y": 0, "z": 0, "color": "1"},
                )
            )

    # The same operation, run once through the protocol and once directly, on
    # two stores that start identically. Comparing the two strings is what
    # makes this a boundary assertion rather than a second copy of the
    # message-contract test.
    wire = asyncio.run(exchange())
    # Replacing the store again is safe here, unlike the assignments this file
    # used to make: ``empty_server_store`` has already recorded the real store
    # for restoration, so teardown still puts the original back. The direct
    # call needs a store of its own, freshly seeded, to be comparable with the
    # one the client filled in.
    server.store = SceneStore()
    server.store.create(_SCENE)
    direct = server.voxelforge_place_block(0, 0, 0, "1")

    assert wire == direct, (
        "a confirmation must reach the client unchanged; a client that reads a "
        "different sentence than the tool returned cannot act on it"
    )
    assert wire == "placed (0,0,0) colour '1' — 1 blocks total", (
        "the exchanged text must be the confirmation, not an empty payload"
    )


def test_a_lookup_failure_reaches_the_client_with_its_remedy(
    empty_server_store: SceneStore,
) -> None:
    """An error's recovery instruction must survive the boundary too.

    The SDK wraps a tool's exception rather than passing its message through,
    so what a client reads is the *server's* rendering of it. That rendering is
    what the caller has to act on, and it is not what a direct
    ``pytest.raises`` assertion inspects. The remedy is checked by its
    presence in the delivered text because the wrapper supplies the prefix,
    which this test does not control; the point is that the instruction
    reaches the client at all.
    """
    empty_server_store.create(_SCENE)

    async def lookup() -> str:
        async with create_connected_server_and_client_session(server.mcp) as client:
            result = await client.call_tool(
                "voxelforge_select_scene", {"name": _ABSENT}
            )
            assert result.isError is True, "an unknown scene name must fail"
            return _wire_text(result)

    text = asyncio.run(lookup())

    assert "voxelforge_load" in text, (
        "the client must receive the tool to call next, or the failure is not "
        "recoverable from what it was shown"
    )
    assert _ABSENT in text, "the failure must name the scene that was missing"


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


def test_this_module_leaves_the_server_globals_as_it_found_them() -> None:
    """Replacing a server global must be undone, not leaked to the next test.

    The tests above hand the server a store and a silent bridge so they do not
    touch a developer's session. Assigning those globals directly leaves them
    assigned: a test that runs afterwards inherits a store it did not create,
    and -- worse -- a ``_sync_bridge`` that silently discards notifications.
    ``test_scene_editing.py`` asserts on exactly that call, so under one
    collection order it would assert against another module's stub and pass
    locally while proving nothing.

    This test is the guard against that returning, and it is why the
    replacements go through ``monkeypatch`` rather than through assignment. It
    is placed last in the file deliberately: it reports what the tests above
    left behind, so moving it earlier would make it check nothing. The
    comparison is by identity, because restoring an equal-but-different store
    would not be restoration.
    """
    assert server.store is _INITIAL_STORE, (
        "server.store was replaced and not restored; a later test would run "
        "against this module's scene rather than its own"
    )
    assert server._sync_bridge is _INITIAL_SYNC_BRIDGE, (
        "server._sync_bridge was replaced and not restored; a later test "
        "asserting on bridge notification would silently assert against the "
        "stub this module installed"
    )
