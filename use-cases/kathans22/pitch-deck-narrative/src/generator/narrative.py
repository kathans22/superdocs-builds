"""generate_narrative(vertical) — batched section fill from knowledge files.

Produces a speaking-script document (never a slide deck) for one vertical.
"""

from __future__ import annotations

import base64
import html
import logging
import re
import uuid
from typing import Any

from .manifest import load_deck_manifest, load_product, load_validated
from .mcp_client import (
    SuperDocsClient,
    SuperDocsClientError,
    chat_batch_cap,
    chunk_section_numbers,
    landed_check,
)

logger = logging.getLogger(__name__)


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


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def build_batch_instruction(
    product: dict[str, Any],
    vertical: dict[str, Any],
    sections: list[dict[str, Any]],
) -> str:
    """Instruction for one batch: draw substance from the vertical knowledge file."""
    product_block = product.get("product") or product
    product_name = _text(product_block.get("name"))
    positioning = _text(product_block.get("positioning"))
    capabilities = product_block.get("capabilities") or []
    differentiator = _text(product_block.get("differentiator"))
    terms = ", ".join(_text(t) for t in (vertical.get("terminology") or []))

    section_blocks: list[str] = []
    for section in sections:
        number = int(section["number"])
        title = _text(section["title"])
        weight = section.get("weight")
        section_blocks.append(
            f"""
### Slide-equivalent {number} — {title} (weight: {weight})
- Keep the heading as: Slide-equivalent {number} — {title}
- Write one clear **Talking point** (one sentence the presenter says first).
- Write **full speaker notes** (multiple paragraphs — this is the product; not bullets-only).
- Replace PLACEHOLDER_TALKING_POINT_{number} and PLACEHOLDER_SPEAKER_NOTES_{number} completely.
- Do not invent a slide layout, slide numbers as a deck, or anything confusable with a .pptx.
""".strip()
        )

    return f"""
You are filling a SPEAKING SCRIPT document for {product_name} aimed at the
{_text(vertical.get('display_name') or vertical.get('vertical'))} vertical.

CRITICAL: This is a speaking script — not a slide deck. Never imply a presentation
file comes out. Use the label "slide-equivalent" only as a section name.

Product (held constant — do not reinvent the product):
- Name: {product_name}
- Positioning: {positioning}
- Capabilities: {"; ".join(_text(c) for c in capabilities)}
- Differentiator: {differentiator}

Vertical knowledge (substance — draw from this, do NOT use a generic {{industry}} template):
- Buyer role: {_text(vertical.get("buyer_role"))}
- Regulatory trigger: {_text(vertical.get("regulatory_trigger"))}
- Document pain: {_text(vertical.get("document_pain"))}
- Typical objection: {_text(vertical.get("typical_objection"))}
- Proof point: {_text(vertical.get("proof_point"))}
- Terminology to use naturally: {terms}

Fill ONLY these sections:
{chr(10).join(section_blocks)}

For shared-weight sections, keep product framing consistent but still write real notes.
For vertical-weight sections, the talking point and notes MUST reflect this vertical's
specific buyer, pain, objection, and proof — not a noun-swapped generic pitch.
""".strip()


def parse_script_sections(markdown: str) -> dict[int, str]:
    """Parse slide-equivalent section bodies from exported markdown."""
    bodies: dict[int, str] = {}
    pattern = re.compile(
        r"^##\s+Slide-equivalent\s+(\d+)[^\n]*\n(.*?)(?=^##\s+Slide-equivalent|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for match in pattern.finditer(markdown or ""):
        bodies[int(match.group(1))] = match.group(2).strip()
    return bodies


async def _export_markdown_text(client: SuperDocsClient, session_id: str) -> str:
    export = await client.export(session_id=session_id, format="markdown")
    return (
        export.get("text")
        or export.get("markdown")
        or export.get("content")
        or ""
    )


async def fill_narrative_sections(
    client: SuperDocsClient,
    session_id: str,
    product: dict[str, Any],
    vertical: dict[str, Any],
    manifest: dict[str, Any],
    pre_edit: dict[int, str],
) -> dict[str, Any]:
    """Batched chat fill (config batch cap) with landed-check and split-retry."""
    sections = list(manifest.get("sections") or [])
    numbers = [int(s["number"]) for s in sections]
    by_number = {int(s["number"]): s for s in sections}
    batches = chunk_section_numbers(numbers, max_batch=chat_batch_cap())
    responses: list[dict] = []
    landed_all: list[int] = []
    failed_all: list[int] = []

    async def fetch_post(sid: str) -> dict[int, str]:
        md = await _export_markdown_text(client, sid)
        return parse_script_sections(md)

    for batch in batches:
        batch_sections = [by_number[n] for n in batch]
        instruction = build_batch_instruction(product, vertical, batch_sections)
        result = await client.chat_with_landed_check(
            message=instruction,
            session_id=session_id,
            section_numbers=batch,
            pre_edit=pre_edit,
            fetch_post_edit=fetch_post,
            max_batch=len(batch),  # already sized to cap
            response_mode="compact",
        )
        responses.extend(result.get("responses") or [])
        landed_all.extend(result.get("landed") or [])
        failed_all.extend(result.get("failed") or [])
        logger.info(
            "batch %s ready_to_approve=%s landed=%s failed=%s",
            batch,
            result.get("ready_to_approve"),
            result.get("landed"),
            result.get("failed"),
        )

    # Deduplicate while preserving order
    def _uniq(items: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for i in items:
            if i not in seen:
                seen.add(i)
                out.append(i)
        return out

    landed_u = _uniq(landed_all)
    failed_u = [n for n in _uniq(failed_all) if n not in set(landed_u)]

    # Approve any pending changes if the platform returned a HITL job.
    for response in responses:
        job_id = response.get("job_id") or (response.get("job") or {}).get("id")
        if not job_id:
            continue
        try:
            await client.approve(
                session_id=session_id,
                job_id=str(job_id),
                approved=True,
                changes=[{"approved": True}],
            )
        except SuperDocsClientError as exc:
            logger.warning("approve skipped/failed for job %s: %s", job_id, exc)

    post = await fetch_post(session_id)
    final = landed_check(pre_edit, post, numbers)
    return {
        "session_id": session_id,
        "responses": responses,
        "landed": final["landed"],
        "failed": final["failed"],
        "post_edit": post,
        "ready": len(final["failed"]) == 0,
    }


async def generate_narrative(
    vertical_code: str,
    *,
    client: SuperDocsClient | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Upload skeleton, fill from vertical knowledge, landed-check, approve path.

    Export to files is layered in a later commit; this returns fill status + markdown.
    """
    bundle = load_validated()
    manifest = bundle["manifest"]
    product = bundle["product"]
    verticals = bundle["verticals"]
    if vertical_code not in verticals:
        raise KeyError(
            f"unknown vertical {vertical_code!r}; known: {sorted(verticals)}"
        )
    vertical = verticals[vertical_code]
    skeleton = build_skeleton_html(manifest, product)
    # Stamp vertical name into skeleton for the presenter.
    skeleton = skeleton.replace(
        "Vertical: (to be filled).",
        f"Vertical: {_text(vertical.get('display_name') or vertical_code)}.",
    )
    pre_edit = skeleton_pre_edit_bodies(manifest)
    sid = session_id or f"pitch-script-{vertical_code}-{uuid.uuid4().hex[:8]}"
    file_b64 = base64.b64encode(skeleton.encode("utf-8")).decode("ascii")

    owns_client = client is None
    if owns_client:
        client = SuperDocsClient()
        await client.connect()
    assert client is not None
    try:
        await client.upload(
            filename=f"pitch-script-{vertical_code}-skeleton.html",
            file_base64=file_b64,
            session_id=sid,
            return_html=False,
        )
        fill = await fill_narrative_sections(
            client, sid, product, vertical, manifest, pre_edit
        )
        markdown = await _export_markdown_text(client, sid)
        return {
            "vertical": vertical_code,
            "session_id": sid,
            "markdown": markdown,
            "landed": fill["landed"],
            "failed": fill["failed"],
            "ready": fill["ready"],
            "responses": fill["responses"],
        }
    finally:
        if owns_client:
            await client.close()
