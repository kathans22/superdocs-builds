"""Assertions that an export cannot be confused with a slide file.

Structural enforcement of the Build 2 card constraint — not a prose reminder.
"""

from __future__ import annotations

import re
from pathlib import Path

# Substrings forbidden in filenames and titles (case-insensitive).
_FORBIDDEN_NAME_TOKENS = (
    "deck",
    "slides",
    "slide-deck",
    "presentation",
    "powerpoint",
    "keynote",
)

# Extensions that imply a slide-producing surface. SuperDocs has none of these
# for this build; rejecting them is defence in depth.
_FORBIDDEN_EXTENSIONS = (
    ".pptx",
    ".ppt",
    ".ppsx",
    ".pps",
    ".odp",
    ".key",
)

_ALLOWED_DOCUMENT_EXTENSIONS = (
    ".md",
    ".markdown",
    ".docx",
    ".pdf",
    ".html",
    ".htm",
    ".txt",
)

_ALLOWED_EXPORT_FORMATS = frozenset(
    {"markdown", "md", "docx", "pdf", "html", "txt", "doc"}
)


class FormatGuardError(ValueError):
    """Raised when an export fails a format-guard check. Message names the check."""


def _lower(text: str) -> str:
    return (text or "").lower()


def assert_filename_not_deck(exported_path: str | Path) -> None:
    """Filename must not carry deck/slide/presentation signatures or slide extensions."""
    path = Path(exported_path)
    name = path.name
    stem = path.stem
    suffix = path.suffix.lower()

    if suffix in _FORBIDDEN_EXTENSIONS:
        raise FormatGuardError(
            f"format_guard.filename: refused slide-adjacent extension {suffix!r} "
            f"on {name!r}. Fix: export as .docx/.md (speaking script), never a "
            "presentation file."
        )
    if suffix and suffix not in _ALLOWED_DOCUMENT_EXTENSIONS:
        raise FormatGuardError(
            f"format_guard.filename: unsupported export extension {suffix!r} on "
            f"{name!r}. Fix: use a document format "
            f"({', '.join(_ALLOWED_DOCUMENT_EXTENSIONS)})."
        )

    haystack = _lower(f"{stem} {name}")
    for token in _FORBIDDEN_NAME_TOKENS:
        # Allow the word "slide-equivalent" in body, but not in the filename.
        if token in haystack:
            raise FormatGuardError(
                f"format_guard.filename: {name!r} contains forbidden token "
                f"{token!r}. Fix: name exports pitch-script-<vertical>-<product>."
            )


def assert_title_not_deck(title: str) -> None:
    """Document title must not read as a deck / slides / presentation."""
    haystack = _lower(title)
    if not haystack.strip():
        raise FormatGuardError(
            "format_guard.title: title is empty. Fix: pass the document H1 / title "
            "that names a speaking script."
        )
    for token in _FORBIDDEN_NAME_TOKENS:
        if token in haystack:
            raise FormatGuardError(
                f"format_guard.title: title {title!r} contains forbidden token "
                f"{token!r}. Fix: title must name a speaking script, not a deck."
            )
