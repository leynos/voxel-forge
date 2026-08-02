"""Locale resolution and message lookup for the desktop application.

The desktop user interface is bilingual: Thai locales see Thai text and
every other locale sees English. The language is resolved from the
environment on each lookup, so this module holds no mutable state and
imports no Qt symbols — it stays importable (and testable) without the
optional ``desktop`` extra.

Resolution order: the ``VOXELFORGE_LANG`` override, then the POSIX
``LANGUAGE``, ``LC_ALL``, ``LC_MESSAGES`` and ``LANG`` variables, and
finally :func:`locale.getlocale` for platforms (such as Windows) that do
not set the POSIX variables.
"""

from __future__ import annotations

import contextlib
import locale
import os
import typing as typ

from voxel_forge.desktop.translations import MESSAGES

if typ.TYPE_CHECKING:
    import collections.abc as cabc

SUPPORTED_LANGUAGES: typ.Final = ("en", "th")
DEFAULT_LANGUAGE: typ.Final = "en"

_OVERRIDE_VARIABLE: typ.Final = "VOXELFORGE_LANG"
_POSIX_VARIABLES: typ.Final = ("LC_ALL", "LC_MESSAGES", "LANG")


def _match_language(tag: str) -> str | None:
    """Map a locale tag to a supported language, or ``None`` if neither."""
    normalised = tag.strip().lower().replace("-", "_")
    normalised = normalised.split(".")[0].split("@")[0]
    for language in SUPPORTED_LANGUAGES:
        if normalised.startswith(language):
            return language
    return None


def _language_from_preference_list(value: str) -> str | None:
    """Pick the first supported language from a colon-separated list."""
    for entry in value.split(":"):
        language = _match_language(entry)
        if language is not None:
            return language
    return None


def _system_locale_tag() -> str:
    """Read the platform locale tag, degrading to an empty string."""
    with contextlib.suppress(ValueError):
        tag, _encoding = locale.getlocale()
        return tag or ""
    return ""


def resolve_language(env: cabc.Mapping[str, str] | None = None) -> str:
    """Resolve the user-interface language from the environment.

    Parameters
    ----------
    env
        Environment mapping to consult; defaults to :data:`os.environ`.

    Returns
    -------
    str
        ``"th"`` for Thai locales, otherwise ``"en"``. An unrecognized
        ``VOXELFORGE_LANG`` override is ignored and resolution falls
        through to the locale variables.
    """
    if env is None:
        env = os.environ

    override = _match_language(env.get(_OVERRIDE_VARIABLE, ""))
    if override is not None:
        return override

    preference = _language_from_preference_list(env.get("LANGUAGE", ""))
    if preference is not None:
        return preference

    for variable in _POSIX_VARIABLES:
        value = env.get(variable, "").strip()
        if value:
            return _match_language(value) or DEFAULT_LANGUAGE

    return _match_language(_system_locale_tag()) or DEFAULT_LANGUAGE


def tr(key: str, **params: object) -> str:
    """Return the message for a key in the active language.

    Parameters
    ----------
    key
        Catalogue key registered in
        :data:`voxel_forge.desktop.translations.MESSAGES`.
    params
        Named values substituted into ``{placeholder}`` fields.

    Returns
    -------
    str
        The localized, formatted message.

    Raises
    ------
    KeyError
        If the key is not in the catalogue.
    """
    try:
        entry = MESSAGES[key]
    except KeyError:
        msg = f"unknown desktop message key: {key!r}"
        raise KeyError(msg) from None
    text = entry[resolve_language()]
    return text.format(**params) if params else text
