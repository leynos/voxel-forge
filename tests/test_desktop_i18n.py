"""Contract tests for the desktop language catalogue and locale resolution.

These tests exercise :mod:`voxel_forge.desktop.i18n` and its message
catalogue without Qt, so they run in environments where the optional
``desktop`` extra is not installed.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import string
import subprocess  # ruff: ignore[suspicious-subprocess-import]  # tests spawn python instances with fixed args; shell=False
import sys
from pathlib import Path

import pytest

from voxel_forge import desktop
from voxel_forge.desktop import i18n
from voxel_forge.desktop.translations import MESSAGES

_THAI_BLOCK = range(0x0E00, 0x0E80)


def _contains_thai(text: str) -> bool:
    """Report whether any character falls in the Thai Unicode block."""
    return any(ord(char) in _THAI_BLOCK for char in text)


def _placeholders(text: str) -> set[str]:
    """Collect the named format placeholders used in a message."""
    return {field for _, field, _, _ in string.Formatter().parse(text) if field}


# ── Locale resolution ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"VOXELFORGE_LANG": "th"}, "th"),
        ({"VOXELFORGE_LANG": "en"}, "en"),
        ({"VOXELFORGE_LANG": "TH_th.UTF-8"}, "th"),
        ({"VOXELFORGE_LANG": "fr", "LANG": "th_TH.UTF-8"}, "th"),
        ({"LANGUAGE": "de:th:en"}, "th"),
        ({"LANGUAGE": "de:fr", "LANG": "th_TH.UTF-8"}, "th"),
        ({"LC_ALL": "en_GB.UTF-8", "LANG": "th_TH.UTF-8"}, "en"),
        ({"LC_MESSAGES": "th_TH.UTF-8"}, "th"),
        ({"LANG": "th-TH"}, "th"),
        ({"LANG": "de_DE.UTF-8"}, "en"),
        ({"LANG": "C"}, "en"),
    ],
)
def test_resolve_language_from_environment(env: dict[str, str], expected: str) -> None:
    """The environment chain must pick Thai for Thai locales only."""
    assert i18n.resolve_language(env) == expected, f"{env} must resolve to {expected}"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"VOXELFORGE_LANG": "thing", "LANG": "en_GB.UTF-8"}, "en"),
        ({"VOXELFORGE_LANG": "engineering", "LANG": "th_TH.UTF-8"}, "th"),
        ({"LANGUAGE": "thistle:en"}, "en"),
        ({"LANG": "then_DE.UTF-8"}, "en"),
        ({"LANG": "thai_TH.UTF-8"}, "th"),
    ],
)
def test_resolve_language_rejects_partial_subtags(
    env: dict[str, str], expected: str
) -> None:
    """A tag that merely begins with a subtag must not select its language.

    Prefix matching would make ``VOXELFORGE_LANG=thing`` a silent switch
    to Thai, so an unrecognized override has to fall through to the
    locale variables instead.
    """
    assert i18n.resolve_language(env) == expected, f"{env} must resolve to {expected}"


@pytest.mark.parametrize(
    ("locale_tag", "expected"),
    [
        (("th_TH", "UTF-8"), "th"),
        (("Thai_Thailand", "874"), "th"),
        (("English_United Kingdom", "1252"), "en"),
        ((None, None), "en"),
    ],
)
def test_resolve_language_falls_back_to_system_locale(
    monkeypatch: pytest.MonkeyPatch,
    locale_tag: tuple[str | None, str | None],
    expected: str,
) -> None:
    """Without locale variables, the platform locale decides the language."""
    monkeypatch.setattr(i18n.locale, "getlocale", lambda: locale_tag)
    assert i18n.resolve_language({}) == expected, (
        f"locale {locale_tag} must resolve to {expected}"
    )


# ── Message lookup ────────────────────────────────────────────


def test_tr_returns_english_for_english_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An English locale must yield the English catalogue text."""
    monkeypatch.setenv("VOXELFORGE_LANG", "en")
    assert i18n.tr("action.save") == "Save", (
        "English text expected under an English locale"
    )


def test_tr_returns_thai_for_thai_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Thai locale must yield the Thai catalogue text."""
    monkeypatch.setenv("VOXELFORGE_LANG", "th")
    assert i18n.tr("action.save") == "บันทึก", "Thai text expected under a Thai locale"


def test_tr_formats_named_placeholders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Named parameters must be substituted into the message."""
    monkeypatch.setenv("VOXELFORGE_LANG", "en")
    assert i18n.tr("file.saved", path="scene.json") == "Saved: scene.json", (
        "placeholder substitution failed"
    )


def test_tr_rejects_unknown_keys() -> None:
    """An unregistered key is a programming error and must raise."""
    with pytest.raises(KeyError, match="unknown desktop message key"):
        i18n.tr("no.such.key")


# ── Catalogue integrity ───────────────────────────────────────


def test_catalogue_entries_cover_both_languages() -> None:
    """Every key must provide exactly the supported languages, non-empty."""
    for key, entry in MESSAGES.items():
        assert set(entry) == set(i18n.SUPPORTED_LANGUAGES), (
            f"{key} must define exactly {i18n.SUPPORTED_LANGUAGES}"
        )
        for language, text in entry.items():
            assert isinstance(text, str), f"{key}/{language} must be a string"
            assert text, f"{key}/{language} must be non-empty"


def test_english_catalogue_contains_no_thai() -> None:
    """The English side of the catalogue must be fully translated."""
    offenders = [key for key, entry in MESSAGES.items() if _contains_thai(entry["en"])]
    assert not offenders, f"Thai text in English messages: {offenders}"


def test_placeholders_match_across_languages() -> None:
    """Both translations of a key must use the same format placeholders."""
    mismatched = [
        key
        for key, entry in MESSAGES.items()
        if _placeholders(entry["en"]) != _placeholders(entry["th"])
    ]
    assert not mismatched, f"placeholder mismatch between languages: {mismatched}"


# ── Desktop wiring ────────────────────────────────────────────


def _desktop_sources() -> dict[str, str]:
    """Map desktop module names (except the catalogue) to their source."""
    package_dir = Path(desktop.__file__).parent
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(package_dir.glob("*.py"))
        if path.name != "translations.py"
    }


def _tr_key_literals(source: str) -> set[str]:
    """Collect string literals passed as the first argument to ``tr``."""
    keys: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        match node:
            case ast.Call(
                func=ast.Name(id="tr"),
                args=[ast.Constant(value=str() as key), *_],
            ):
                keys.add(key)
    return keys


def _string_literals(source: str) -> set[str]:
    """Collect every string literal in a module's source."""
    return {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def test_every_tr_call_uses_a_registered_key() -> None:
    """Keys referenced from the desktop modules must exist in the catalogue."""
    for name, source in _desktop_sources().items():
        unknown = _tr_key_literals(source) - MESSAGES.keys()
        assert not unknown, f"{name} references unregistered keys: {unknown}"


def test_every_catalogue_key_is_referenced() -> None:
    """The catalogue must not accumulate dead keys."""
    referenced: set[str] = set()
    for source in _desktop_sources().values():
        referenced |= _string_literals(source)
    unused = set(MESSAGES) - referenced
    assert not unused, f"catalogue keys never referenced by the desktop: {unused}"


def test_no_thai_text_outside_the_catalogue() -> None:
    """Desktop modules must draw every localized string from the catalogue."""
    offenders = [
        name for name, source in _desktop_sources().items() if _contains_thai(source)
    ]
    assert not offenders, f"Thai text outside translations.py: {offenders}"


# ── Live window construction ──────────────────────────────────

_MENU_PROBE = """
from PySide6.QtWidgets import QApplication

from voxel_forge.desktop.app import MainWindow

app = QApplication([])
win = MainWindow()
print("\\x1f".join(action.text() for action in win.menuBar().actions()))
"""


def _menu_titles(language: str) -> list[str]:
    """Build the main window offscreen and report its menu titles.

    The probe fails whenever Qt cannot start, which most often means the
    host has PySide6 installed but not the shared objects Qt links
    against. Reporting the child's stderr distinguishes that from a real
    localization regression, which the exit status alone does not.
    """
    env = os.environ | {"QT_QPA_PLATFORM": "offscreen", "VOXELFORGE_LANG": language}
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]  # fixed interpreter and script; shell=False
        [sys.executable, "-c", _MENU_PROBE],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=env,
    )
    if result.returncode != 0:
        pytest.fail(
            f"the offscreen window probe failed for {language!r} "
            f"(exit {result.returncode}):\n{result.stderr.strip()}"
        )
    return result.stdout.strip().splitlines()[-1].split("\x1f")


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="the optional desktop extra is not installed",
)
@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", ["&File", "&Create", "&View", "&Tools", "&Help"]),
        ("th", ["ไฟล์ (&F)", "สร้าง (&C)", "มุมมอง (&V)", "เครื่องมือ (&T)", "ช่วยเหลือ (&H)"]),
    ],
)
def test_main_window_menus_follow_the_locale(
    language: str, expected: list[str]
) -> None:
    """The constructed window must present menus in the resolved language."""
    assert _menu_titles(language) == expected, (
        f"menu titles must be localized for {language}"
    )
