"""generate_narrative(vertical) — batched section fill from knowledge files.

Produces a speaking-script document (never a slide deck) for one vertical.
"""

from __future__ import annotations

import base64
import html
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx2

from .format_guard import FormatGuardError, assert_not_deck
from .ledger import Ledger, ops_from_response, parse_ops_ceiling
from .manifest import load_deck_manifest, load_product, load_validated, project_root
from .mcp_client import (
    SuperDocsClient,
    SuperDocsClientError,
    chat_batch_cap,
    chunk_section_numbers,
    landed_check,
)

logger = logging.getLogger(__name__)

OUT_DIR = project_root() / "out"


def build_skeleton_html(
    manifest: dict[str, Any] | None = None,
    product: dict[str, Any] | None = None,
) -> str:
    """Build an empty nine-section speaking-script skeleton from the deck manifest."""
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
    vertical_label = _text(vertical.get("display_name") or vertical.get("vertical"))

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
  Those placeholder strings must not appear anywhere in the finished section.
- Do not invent a slide layout or anything confusable with a presentation file.
- Do not leave a second leftover Speaker notes / Talking point block under the real one.
""".strip()
        )

    return f"""
You are filling a SPEAKING SCRIPT document for {product_name} aimed at the
{vertical_label} vertical.

CRITICAL: This is a speaking script — not a slide deck. Never imply a presentation
file comes out. Use the label "slide-equivalent" only as a section name.

Product (held constant — do not reinvent the product):
- Name: {product_name}
- Positioning: {positioning}
- Capabilities: {"; ".join(_text(c) for c in capabilities)}
- Differentiator: {differentiator}

Vertical knowledge (substance — draw from this, do NOT use a generic industry template):
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


async def _download_bytes(url: str) -> bytes:
    async with httpx2.AsyncClient(timeout=None) as http:
        response = await http.get(url)
        response.raise_for_status()
        return response.content


def _script_title(product_name: str) -> str:
    return f"{product_name} — Pitch Speaking Script"


def _guard_export_or_raise(
    path: Path,
    *,
    title: str,
    export_format: str,
) -> None:
    """Run format_guard; on failure remove the file so a bad export never lands."""
    try:
        assert_not_deck(path, title, export_format=export_format)
    except FormatGuardError as exc:
        if path.exists():
            path.unlink()
        raise FormatGuardError(f"export blocked — {exc}") from exc


async def export_narrative_files(
    client: SuperDocsClient,
    session_id: str,
    vertical_code: str,
    product_name: str = "ClarityDocs",
    out_dir: Path | None = None,
) -> dict[str, Path]:
    """Export speaking script to markdown + docx under out/. Never a presentation path.

    No export completes without passing format_guard.assert_not_deck. A guard
    failure blocks the export and names which check failed.
    """
    dest = out_dir or OUT_DIR
    dest.mkdir(parents=True, exist_ok=True)
    slug = product_name.lower().replace(" ", "")
    base = f"pitch-script-{vertical_code}-{slug}"
    title = _script_title(product_name)

    md_export = await client.export(
        session_id=session_id,
        format="markdown",
        filename=base,
    )
    markdown = (
        md_export.get("text")
        or md_export.get("markdown")
        or md_export.get("content")
        or ""
    )
    md_path = dest / f"{base}.md"
    md_path.write_text(markdown, encoding="utf-8")
    _guard_export_or_raise(md_path, title=title, export_format="markdown")

    docx_export = await client.export(
        session_id=session_id,
        format="docx",
        filename=base,
    )
    download_url = docx_export.get("download_url")
    if not download_url:
        raise SuperDocsClientError(
            "docx export returned no download_url. Fix: binary exports are documented "
            "to return a signed download_url — check the response shape."
        )
    docx_path = dest / f"{base}.docx"
    docx_path.write_bytes(await _download_bytes(download_url))
    _guard_export_or_raise(docx_path, title=title, export_format="docx")
    return {"markdown": md_path, "docx": docx_path}


async def fill_narrative_sections(
    client: SuperDocsClient,
    session_id: str,
    product: dict[str, Any],
    vertical: dict[str, Any],
    manifest: dict[str, Any],
    pre_edit: dict[int, str],
    *,
    vertical_code: str,
    ledger: Ledger | None = None,
) -> dict[str, Any]:
    """Batched chat fill (config batch cap) with landed-check and split-retry."""
    sections = list(manifest.get("sections") or [])
    numbers = [int(s["number"]) for s in sections]
    by_number = {int(s["number"]): s for s in sections}
    batches = chunk_section_numbers(numbers, max_batch=chat_batch_cap())
    responses: list[dict] = []
    ceiling = parse_ops_ceiling()

    async def fetch_post(sid: str) -> dict[int, str]:
        md = await _export_markdown_text(client, sid)
        return parse_script_sections(md)

    for batch in batches:
        batch_sections = [by_number[n] for n in batch]
        instruction = build_batch_instruction(product, vertical, batch_sections)
        started = time.monotonic()
        result = await client.chat_with_landed_check(
            message=instruction,
            session_id=session_id,
            section_numbers=batch,
            pre_edit=pre_edit,
            fetch_post_edit=fetch_post,
            max_batch=len(batch),
            response_mode="compact",
        )
        elapsed = time.monotonic() - started
        batch_responses = result.get("responses") or []
        responses.extend(batch_responses)
        ops = sum(ops_from_response(r) if isinstance(r, dict) else 0 for r in batch_responses)
        if ops == 0 and batch_responses:
            # Compact apply path may omit usage; charge 1 per chat call in the batch.
            ops = len(batch_responses)
        if ledger is not None:
            ledger.record(
                step="chat",
                vertical=f"{vertical_code} sections {batch}",
                chat_calls=ops,
                wall_time=elapsed,
                content_key=f"narrative:{vertical_code}:batch:{batch}:v{manifest.get('manifest_version', 1)}",
                output_exists=False,
            )
            ledger.enforce_ceiling(ceiling)
        logger.info(
            "batch %s ready_to_approve=%s landed=%s failed=%s ops=%s",
            batch,
            result.get("ready_to_approve"),
            result.get("landed"),
            result.get("failed"),
            ops,
        )

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
    out_dir: Path | None = None,
    ledger: Ledger | None = None,
) -> dict[str, Any]:
    """Upload skeleton, fill from vertical knowledge, landed-check, export md+docx."""
    bundle = load_validated()
    manifest = bundle["manifest"]
    product = bundle["product"]
    verticals = bundle["verticals"]
    if vertical_code not in verticals:
        raise KeyError(
            f"unknown vertical {vertical_code!r}; known: {sorted(verticals)}"
        )
    vertical = verticals[vertical_code]
    product_block = product.get("product") or product
    product_name = _text(product_block.get("name") or "ClarityDocs")
    skeleton = build_skeleton_html(manifest, product)
    skeleton = skeleton.replace(
        "Vertical: (to be filled).",
        f"Vertical: {_text(vertical.get('display_name') or vertical_code)}.",
    )
    pre_edit = skeleton_pre_edit_bodies(manifest)
    sid = session_id or f"pitch-script-{vertical_code}-{uuid.uuid4().hex[:8]}"
    file_b64 = base64.b64encode(skeleton.encode("utf-8")).decode("ascii")
    if ledger is None:
        ledger = Ledger()

    owns_client = client is None
    if owns_client:
        client = SuperDocsClient()
        await client.connect()
    assert client is not None
    try:
        started = time.monotonic()
        await client.upload(
            filename=f"pitch-script-{vertical_code}-skeleton.html",
            file_base64=file_b64,
            session_id=sid,
            return_html=False,
        )
        ledger.record(
            step="upload",
            vertical=vertical_code,
            chat_calls=0,
            wall_time=time.monotonic() - started,
            content_key=f"narrative:{vertical_code}:upload:v{manifest.get('manifest_version', 1)}",
            output_exists=False,
        )

        fill = await fill_narrative_sections(
            client,
            sid,
            product,
            vertical,
            manifest,
            pre_edit,
            vertical_code=vertical_code,
            ledger=ledger,
        )
        started = time.monotonic()
        paths = await export_narrative_files(
            client,
            sid,
            vertical_code,
            product_name=product_name,
            out_dir=out_dir,
        )
        ledger.record(
            step="export",
            vertical=vertical_code,
            chat_calls=0,
            wall_time=time.monotonic() - started,
            content_key=f"narrative:{vertical_code}:export:v{manifest.get('manifest_version', 1)}",
            output_exists=False,
        )
        ledger.save()
        ledger.report()
        markdown = paths["markdown"].read_text(encoding="utf-8")
        return {
            "vertical": vertical_code,
            "session_id": sid,
            "markdown": markdown,
            "paths": {k: str(v) for k, v in paths.items()},
            "landed": fill["landed"],
            "failed": fill["failed"],
            "ready": fill["ready"],
            "responses": fill["responses"],
            "ops_total": ledger.total_operations,
        }
    finally:
        if owns_client:
            await client.close()
