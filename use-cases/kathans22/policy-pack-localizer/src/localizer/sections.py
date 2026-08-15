"""Splits the master policy document into core and annex sections."""

from __future__ import annotations

import re
from pathlib import Path

HEADING_RE = re.compile(r"^## (\d+) (.+)$", re.MULTILINE)


def parse_sections(text: str) -> list[dict]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        raise ValueError("no numbered headings found")

    sections = []
    for i, match in enumerate(matches):
        number = int(match.group(1))
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append({"number": number, "heading": heading, "body": body})
    return sections


def load_sections(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    return parse_sections(text)


def assert_matches_manifest(sections: list[dict], manifest: dict) -> None:
    declared = manifest["sections"]
    if len(sections) != len(declared):
        raise ValueError(
            f"parsed {len(sections)} sections but manifest declares {len(declared)}"
        )
    for parsed, expected in zip(sections, declared):
        if parsed["number"] != expected["number"]:
            raise ValueError(
                f"section order mismatch: parsed number {parsed['number']}, "
                f"manifest expects {expected['number']}"
            )
        if parsed["heading"] != expected["heading"]:
            raise ValueError(
                f"section {parsed['number']} heading {parsed['heading']!r} "
                f"does not match manifest heading {expected['heading']!r}"
            )
