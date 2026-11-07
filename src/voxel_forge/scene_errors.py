"""Typed scene-lookup failures.

These are domain conditions rather than adapter failures: a caller named a
scene that was not there, or named nothing while nothing was current. They
live apart from :mod:`voxel_forge.model_validation` because that module is
about *field* validity -- palette values, name length, voxel size bounds -- and
a registry or a tool that raises a lookup failure should not have to import
those to spell it. Splitting them keeps each module's imports saying what it
actually depends on.

Nothing here names an MCP tool, a log field, or any message a client should
read. The domain states the condition; the adapter in
:mod:`voxel_forge.scene_boundary` names the operation that hit it and turns it
into a recovery instruction. That split is what keeps the model free of the
tool surface.
"""

from __future__ import annotations


class NoCurrentSceneError(KeyError):
    """No scene is current in this session.

    A domain condition, distinct from :class:`UnknownSceneError`: the caller
    named nothing and nothing was current. Both are ``KeyError`` so existing
    callers keep working, but they are separate types so the adapter can give
    each its own recovery instruction instead of inferring intent from a
    message string.

    The message is deliberately transport-neutral. Naming an MCP tool here
    would make the domain model depend on the tool surface, which is the
    adapter's concern; the boundary in ``scene_boundary`` attaches the
    caller-facing wording.
    """

    def __init__(self) -> None:
        """Set the transport-neutral message for a session with no current scene."""
        super().__init__("no scene is current in this session")


class UnknownSceneError(KeyError):
    """A named scene is not registered in this session.

    Separate from :class:`NoCurrentSceneError` because a caller who named a
    scene has already created one and needs a different remedy: load a saved
    scene, or correct the name. ``select`` raises this too, since a selection
    target is named.

    The name is carried in the message and as an attribute so the failure is
    diagnosable from a log, where no adapter has translated it yet.
    """

    def __init__(self, name: str) -> None:
        """Store the missing name and build a message that names it."""
        super().__init__(f"scene {name!r} is not registered in this session")
        self.name = name
