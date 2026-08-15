"""Normalises and hashes core sections to lock and verify their identity."""

from __future__ import annotations

import re
import unicodedata

# Curly/smart quote variants -> straight ASCII equivalents.
_QUOTE_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
}

# Dash-family characters editors substitute for one another via smart-dash
# autocorrect (hyphen-minus, hyphen, non-breaking hyphen, figure dash,
# en dash, em dash, minus sign) -> one canonical hyphen-minus.
_DASH_CHARS = "-‐‑‒–—−"
_DASH_RE = re.compile(f"[{_DASH_CHARS}]")

# Non-breaking / figure / thin / narrow-no-break space variants -> a regular space.
_SPACE_CHARS = "    "
_SPACE_RE = re.compile(f"[{_SPACE_CHARS}]")

_LIST_MARKER_RE = re.compile(r"^([ \t]*)[-*•][ \t]+", re.MULTILINE)
_BLANK_RUN_RE = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)*")
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_INLINE_WS_RE = re.compile(r"[ \t]+")


def normalise(text: str) -> str:
    """Canonicalise text so cosmetic round-trip noise never registers as a change.

    Used at lock time and at verify time, and nowhere else in this codebase.
    The contract:

    1. Unicode-normalise to NFC, so an editor's combining-character
       re-encoding of an accented letter compares equal to the original.
    2. Collapse all line-ending styles (\\r\\n, \\r) to \\n.
    3. Map curly/smart quotes to straight ASCII quotes.
    4. Map all dash-family characters (hyphen-minus, en dash, em dash,
       minus sign) to one canonical hyphen-minus, since editors' smart-dash
       autocorrect substitutes freely between them.
    5. Map non-breaking and other Unicode space variants to a regular space.
    6. Canonicalise a line-leading list marker (-, *, or bullet, plus
       whitespace) to "- ", preserving indentation.
    7. Collapse any run of blank lines to exactly one blank line.
    8. Strip trailing whitespace from every line.
    9. Collapse runs of horizontal whitespace within a line to one space.
    10. Strip leading and trailing whitespace from the whole text.

    Case is deliberately left untouched: a capitalisation change may be a
    real edit (a defined term losing its capital, for example) and must
    stay detectable.

    What this gives up: a change that is *purely* one of the above — a
    quote-style swap, a dash-glyph swap, a bullet-marker swap, a
    whitespace-only edit, or an NFC/NFD re-encoding — is indistinguishable
    from no edit at all once normalised. Any change to actual wording,
    numbers, or word order leaves the alphanumeric content stream untouched
    and is still detected.
    """
    normalised = unicodedata.normalize("NFC", text)
    normalised = normalised.replace("\r\n", "\n").replace("\r", "\n")
    for curly, straight in _QUOTE_MAP.items():
        normalised = normalised.replace(curly, straight)
    normalised = _DASH_RE.sub("-", normalised)
    normalised = _SPACE_RE.sub(" ", normalised)
    normalised = _LIST_MARKER_RE.sub(r"\1- ", normalised)
    normalised = _BLANK_RUN_RE.sub("\n\n", normalised)
    normalised = _TRAILING_WS_RE.sub("", normalised)
    normalised = _INLINE_WS_RE.sub(" ", normalised)
    return normalised.strip()
