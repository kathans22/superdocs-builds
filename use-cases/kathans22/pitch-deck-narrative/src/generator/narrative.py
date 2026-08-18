"""generate_narrative(vertical) — batched section fill from knowledge files.

Produces a speaking-script document (never a slide deck) for one vertical.
"""

from __future__ import annotations

import html
from typing import Any

from .manifest import load_deck_manifest, load_product, load_validated


def build_skeleton_html(
    manifest: dict[str, Any] | None = None,
    product: dict[str, Any] | None = None,
) -> str:
    """Build an empty nine-section speaking-script skeleton from the deck manifest.

    Headings only — bodies are placeholders filled later from vertical knowledge.
    Title and first line state plainly this is a speaking script, not a slide deck.
    """
    manifest = manifest or load_deck_manifest()
    product_doc = product or load_product()
    product_block = product_doc.get("product") or product_doc
    product_name = html.escape(str(product_block.get("name", "ClarityDocs")))
    notice = html.escape(
        str(manifest.get("script_notice") or "Speaking script — not a slide deck.")
    )
    sections = manifest.get("sections") or []
    if not sections:
        raise ValueError("deck manifest has no sections — cannot build skeleton")

    parts: list[str] = [
        "<html><body>",
        f"<h1>{product_name} — Pitch Speaking Script</h1>",
        f"<p><strong>{notice}</strong></p>",
        "<p>Vertical: (to be filled). Each slide-equivalent below is a speaking "
        "section with a talking point and full speaker notes — not a slide canvas.</p>",
    ]
    for section in sections:
        number = int(section["number"])
        title = html.escape(str(section["title"]))
        parts.append(f"<h2>Slide-equivalent {number} — {title}</h2>")
        parts.append(
            f"<p><em>Talking point:</em> PLACEHOLDER_TALKING_POINT_{number}</p>"
        )
        parts.append(
            f"<p><em>Speaker notes:</em> PLACEHOLDER_SPEAKER_NOTES_{number}</p>"
        )
    parts.append("</body></html>")
    return "\n".join(parts)


def skeleton_pre_edit_bodies(manifest: dict[str, Any] | None = None) -> dict[int, str]:
    """Pre-edit fingerprint text for landed-check (placeholder bodies)."""
    manifest = manifest or load_deck_manifest()
    bodies: dict[int, str] = {}
    for section in manifest.get("sections") or []:
        number = int(section["number"])
        bodies[number] = (
            f"PLACEHOLDER_TALKING_POINT_{number} PLACEHOLDER_SPEAKER_NOTES_{number}"
        )
    return bodies
