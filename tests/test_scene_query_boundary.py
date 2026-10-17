"""Executable contract for the MCP boundary around a read tool's lookup.

The read handlers are queries: ``preview``, ``get_info`` and ``merge_stats``
call ``lookup_scene`` and render the scene. The typed domain failure crosses
each handler unchanged, and the registration decorator
``recover_lookup_failures`` turns it into the recovery instruction a client
reads. Keeping those two facts apart is the point of the split, so they are
asserted in two separate tests here: one reaches the undecorated handler
through ``functools.wraps`` and requires the domain's own exception type, and
one calls the decorated tool and requires the full recovery message.

A single test asserting only the decorated message would pass for a handler
that worded its own failures and left the decorator decorative -- the query
would carry presentation policy after all, which is the defect this boundary
exists to prevent.

Run with ``uv run pytest -q``.
"""

from __future__ import annotations

import typing as typ

import pytest

from voxel_forge import server
from voxel_forge.scene_errors import NoCurrentSceneError, UnknownSceneError

if typ.TYPE_CHECKING:
    # Annotates the ``scene_store`` fixture parameter, which this module
    # requests by name and never constructs; the import therefore never runs.
    from voxel_forge.model import SceneStore

# The scene the shared ``scene_store`` fixture registers, named here because
# the success-direction test below asks for it by name. It matches the ``SCENE``
# in ``conftest.py``; the fixture is what creates it.
_SCENE = "house"

# The scene every tool is asked for when it must be missing. It is absent from
# the shared fixture, so each call takes the unknown-scene branch.
_ABSENT = "absent"

# The read-only tools this boundary covers. They are named here rather than
# imported from the logging module: that table also describes the command
# surface, and a boundary test that borrowed it would drag the other contract
# into this module's failure messages.
_QUERY_TOOLS = {
    "voxelforge_preview": server.voxelforge_preview,
    "voxelforge_get_info": server.voxelforge_get_info,
    "voxelforge_merge_stats": server.voxelforge_merge_stats,
}


@pytest.mark.parametrize("tool", sorted(_QUERY_TOOLS))
def test_the_read_handler_keeps_the_domain_failure_typed(
    empty_server_store: SceneStore,
    tool: str,
) -> None:
    """The handler itself must fail in the domain's types, not in MCP prose.

    This reaches past the boundary decorator, which ``functools.wraps`` makes
    possible, and drives the undecorated handler. That is the point: if the
    handler worded its own failures, the decorator would be redundant and the
    query would carry presentation policy after all. Asserting the typed
    failures here is what keeps the two layers honest -- the handler knows the
    condition, and the decorator is the only thing that knows the wording.

    ``UnknownSceneError.name`` is asserted too, so the handler cannot pass by
    raising a correctly typed error that has lost which scene was missing.
    """
    handler = getattr(server, tool).__wrapped__

    with pytest.raises(NoCurrentSceneError):
        handler("")

    empty_server_store.create(_SCENE)
    with pytest.raises(UnknownSceneError) as caught:
        handler(_ABSENT)

    assert caught.value.name == _ABSENT, (
        f"{tool} must let the registry's own failure through, carrying the name"
    )


@pytest.mark.parametrize("tool", sorted(_QUERY_TOOLS))
def test_the_read_boundary_words_both_lookup_failures(
    empty_server_store: SceneStore,
    tool: str,
) -> None:
    """The decorator must word each failure as the step that resolves it.

    The two branches are distinct situations: a session with no scene has to
    create one, while a caller who named a scene has one and must load or
    correct the name. Both messages are compared in full, because a substring
    check would accept a message that names the right tool and then gives the
    wrong instruction. ``args[0]`` is read rather than ``str()`` because
    ``KeyError`` repr-quotes its argument.
    """
    decorated = getattr(server, tool)

    with pytest.raises(KeyError) as no_current:
        decorated("")

    assert no_current.value.args[0] == (
        "no scene yet — call voxelforge_create_scene first"
    ), f"{tool} must send a session with no scene to create one"

    empty_server_store.create(_SCENE)
    with pytest.raises(KeyError) as unknown:
        decorated(_ABSENT)

    assert unknown.value.args[0] == (
        f"scene '{_ABSENT}' is not loaded in this session — call voxelforge_load "
        "for a saved scene, or use the name of an existing session scene"
    ), f"{tool} must send a caller with a mistyped name to the same remedy"
