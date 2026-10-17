"""Executable contract for what crosses the MCP wire when a tool is called.

The tests elsewhere in the suite call the tool functions directly, which
exercises the behaviour but not the *protocol*: it never proves that the text a
tool returned is the text a client receives. A response could be rewritten,
truncated, or dropped by the protocol layer while the direct call stayed
correct -- and a direct call cannot show that at all.

This module drives the real MCP boundary with an in-memory client session for
exactly that claim, in both directions: a successful confirmation and a failed
lookup must arrive intact. The surface a server *advertises* before any call
is made -- instructions, descriptions, schemas -- is checked in
``test_mcp_inventory.py``, and the tools whose response is a document rather
than a sentence are checked in ``test_mcp_responses.py``. Those are distinct
claims over the same protocol, and stating each one in its own module keeps
every failure message specific about what broke.

Run with ``uv run pytest -q``.
"""

from __future__ import annotations

import typing as typ

from mcp_wire_helpers import call_scene_tool, wire_text

from voxel_forge import server
from voxel_forge.model import SceneStore

if typ.TYPE_CHECKING:
    import collections.abc as cabc

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


def _server_globals() -> tuple[SceneStore, cabc.Callable[[VoxelScene], None]]:
    """Return the registry and bridge notifier exactly as this module found them.

    Read once at import time, before any test in this file replaces either.
    The final test below compares against what this returned, which is why it
    has to be the last test here: it reports what the tests above it left
    behind.
    """
    return server.store, server._sync_bridge


_INITIAL_STORE, _INITIAL_SYNC_BRIDGE = _server_globals()


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
    # The same operation, run once through the protocol and once directly, on
    # two stores that start identically. Comparing the two strings is what
    # makes this a boundary assertion rather than a second copy of the
    # message-contract test.
    result = call_scene_tool(
        _SCENE,
        "voxelforge_place_block",
        {"x": 0, "y": 0, "z": 0, "color": "1"},
    )
    assert result.isError is False, "placing a voxel must succeed"
    wire = wire_text(result)
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
    result = call_scene_tool(_SCENE, "voxelforge_select_scene", {"name": _ABSENT})
    assert result.isError is True, "an unknown scene name must fail"
    text = wire_text(result)

    assert "voxelforge_load" in text, (
        "the client must receive the tool to call next, or the failure is not "
        "recoverable from what it was shown"
    )
    assert _ABSENT in text, "the failure must name the scene that was missing"


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
