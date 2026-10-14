"""Scene-name prompts shared by desktop creation actions.

Use ``prompt_scene_name(window, "New scene", default="my_model")`` to obtain
one stripped name or ``None`` when the user cancels or submits whitespace.
"""

from __future__ import annotations

import typing as typ

from PySide6.QtWidgets import QInputDialog

if typ.TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


def prompt_scene_name(
    parent: QWidget, title: str, *, default: str, label: str = "ชื่อ:"
) -> str | None:
    """Prompt for a scene name, e.g. ``" tree "`` becomes ``"tree"``."""
    name, accepted = QInputDialog.getText(parent, title, label, text=default)
    return name.strip() if accepted and name.strip() else None
