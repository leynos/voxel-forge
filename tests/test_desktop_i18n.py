"""Contract tests for the desktop language catalogue and locale resolution.

These tests exercise :mod:`voxel_forge.desktop.i18n` and its message
catalogue without Qt, so they run in environments where the optional
``desktop`` extra is not installed.
"""

from __future__ import annotations

import string

import pytest

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
