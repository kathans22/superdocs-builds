"""Generates per-country packs by batching the annex replacement into one call."""

from __future__ import annotations

import base64
import re
import time
from pathlib import Path

import httpx2

from . import config as config_module
from . import corelock
from . import sections as sections_module
from .ledger import Ledger, ops_from_response
from .mcp_client import SuperDocsClient, SuperDocsClientError, parse_proposed_changes

ROOT = Path(__file__).resolve().parents[2]
POLICY_MASTER_PATH = config_module.CONFIG_DIR / "policy-master.md"
OUT_DIR = ROOT / "out"


class PackIntegrityError(RuntimeError):
    """Raised when an exported pack fails core or annex verification.

    A pack that raises this is quarantined per CLAUDE.md rule 3: it is never
    written to disk as a finished pack, and the run does not report success.
    """

_LANGUAGE_NAMES = {"en": "English", "fr": "French", "pt": "Portuguese"}


def _render_reporting(country: dict) -> str:
    reporting = country["reporting"]
    external = "; ".join(f"{item['name']} ({item['detail']})" for item in reporting["external"])
    return (
        f"internal contact reachable at {reporting['internal_email']} or "
        f"{reporting['internal_phone']}; external channels are {external}"
    )


def _render_legal(country: dict) -> str:
    return "; ".join(country["legal"])


def _render_escalation(country: dict) -> str:
    escalation = country["escalation"]
    return (
        f"tier 1 — {escalation['tier_1']}; tier 2 — {escalation['tier_2']}; "
        f"tier 3 — {escalation['tier_3']}; regulator notification — "
        f"{escalation['regulator_notification']}"
    )


def _render_acknowledgement(country: dict) -> str:
    return (
        f"office {country['office']!r} in {country['country']!r}, safeguarding lead "
        f"{country['safeguarding_lead']!r}, with blank fields for recipient name, role, "
        "date, and signature"
    )


_SLOT_RENDERERS = {
    "reporting": _render_reporting,
    "legal": _render_legal,
    "escalation": _render_escalation,
    "acknowledgement": _render_acknowledgement,
}


def build_instruction(manifest: dict, country: dict) -> str:
    """Build the single instruction that replaces every annex section in one call.

    A multi-section edit sent as one chat request is one operation; the same
    edits as four separate calls would cost four. This function is what makes
    generate_pack's chat call batched rather than looped per section, and that
    batching is deliberate — it is the reason a pack costs 1 operation, not 4.
    """
    annex_sections = [s for s in manifest["sections"] if s["role"] == "annex"]
    language_name = _LANGUAGE_NAMES.get(country["language"], country["language"])

    lines = [
        f"Localise this policy for {country['country']} ({country['office']}), writing "
        f"all replaced text in {language_name}. Replace each of the following annex "
        "sections independently with the content given for it. Do not add, remove, or "
        "reword anything outside these sections; every other section must be left "
        "exactly as it is.",
        "",
    ]
    for section in annex_sections:
        content = _SLOT_RENDERERS[section["slot"]](country)
        lines.append(f'Section {section["number"]} "{section["heading"]}": {content}')
    return "\n".join(lines)


_SECTION_MENTION_RE = re.compile(r"\bsection\s+(\d+)\b", re.IGNORECASE)
_PARTIAL_APPLY_RE = re.compile(r"updated\s+(\d+)\s+of\s+(\d+)\s+sections?", re.IGNORECASE)


def _master_annex_placeholders(manifest: dict) -> dict[int, str]:
    """The unedited annex body text in policy-master.md, per annex section number.

    Used as the corruption signal in verify_pack: if an exported pack's
    annex section still contains this placeholder text, that section was
    never cleanly localised — whether because the edit never landed, or
    because a concurrent-merge response spliced the old body back in
    alongside the new content. Observed live: a single-section retry after
    a partial batch apply collided with the settling batched edit and the
    merged, exported result kept both the placeholder sentence and the new
    content in Section 8.
    """
    master_sections = sections_module.parse_sections(POLICY_MASTER_PATH.read_text(encoding="utf-8"))
    annex_numbers = {s["number"] for s in manifest["sections"] if s["role"] == "annex"}
    return {
        s["number"]: corelock.normalise(s["body"])
        for s in master_sections
        if s["number"] in annex_numbers
    }


def verify_pack(markdown_text: str, manifest: dict, language: str) -> dict:
    """Verify an exported pack: the core is untouched and every annex section landed.

    Two independent checks, both must pass:
    - core: recompute the core hash from the export and compare it to the
      locked hash for this core_version/language (corelock.verify) — the
      enforcement half of CLAUDE.md rule 3.
    - annex: no annex section may still contain the master's unedited
      placeholder text. This is the annex-side counterpart of the core hash
      check: it catches an edit that silently didn't land, and it catches a
      corrupted merge that spliced the old body back in next to the new one
      (a hash comparison alone would not have caught the latter, since the
      corrupted section is neither core nor byte-identical to anything
      previously locked).
    """
    all_sections = sections_module.parse_sections(markdown_text)
    core_numbers = {s["number"] for s in manifest["sections"] if s["role"] == "core"}
    core_sections = [s for s in all_sections if s["number"] in core_numbers]

    lock_data = corelock.load_lock(manifest["core_version"], language)
    core_result = corelock.verify(core_sections, lock_data)

    placeholders = _master_annex_placeholders(manifest)
    section_by_number = {s["number"]: s for s in all_sections}
    unlocalised = []
    for number, placeholder in placeholders.items():
        section = section_by_number.get(number)
        if section is None or placeholder in corelock.normalise(section["body"]):
            unlocalised.append(number)

    return {
        "passed": core_result["passed"] and not unlocalised,
        "core": core_result,
        "unlocalised_annex_sections": unlocalised,
    }


def assert_no_core_sections_named(instruction: str, manifest: dict) -> None:
    """Raise if a core section number is named anywhere in an outbound instruction.

    Core sections are never named in any instruction sent to SuperDocs — that
    is the intent half of the core's protection (CLAUDE.md rule 3); the hash
    check in corelock.verify after export is the enforcement half. This is a
    hard stop, not a warning: a violating instruction is never sent.
    """
    core_numbers = {s["number"] for s in manifest["sections"] if s["role"] == "core"}
    named_numbers = {int(match) for match in _SECTION_MENTION_RE.findall(instruction)}
    violating = sorted(named_numbers & core_numbers)
    if violating:
        raise ValueError(
            f"Instruction names core section number(s) {violating} — core sections "
            "must never be named in an instruction sent to SuperDocs. This is a bug "
            "in the instruction builder; the call is not sent."
        )


def _content_key(country_code: str, core_version: int) -> str:
    return f"pack:{country_code}:v{core_version}"


def _pack_files_exist(pack_dir: Path) -> bool:
    return all((pack_dir / filename).exists() for _, filename in _EXPORT_FILES)


_TEXT_EXPORT_FORMATS = {"markdown", "html", "txt"}
_TEXT_EXPORT_KEYS = ("text", "markdown", "content")
_EXPORT_FILES = (("markdown", "policy-pack.md"), ("docx", "policy-pack.docx"))


async def _default_downloader(url: str) -> bytes:
    async with httpx2.AsyncClient() as http:
        response = await http.get(url)
        response.raise_for_status()
        return response.content


async def _write_export(
    export_response: dict, dest_path: Path, format: str, downloader=_default_downloader
) -> Path:
    """Write one export_document response to disk, text or binary as the format demands.

    Text formats (markdown/html/txt) return content inline; binary formats
    (docx/pdf) return a short-lived signed download_url that must be fetched
    to get the file, per SuperDocs' own tool documentation.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if format in _TEXT_EXPORT_FORMATS:
        text = next((export_response[k] for k in _TEXT_EXPORT_KEYS if export_response.get(k)), None)
        if text is None:
            raise SuperDocsClientError(
                f"export_document response for format={format!r} carried no text under "
                f"any of {_TEXT_EXPORT_KEYS}. Fix: check the response shape hasn't changed."
            )
        dest_path.write_text(text, encoding="utf-8")
    else:
        download_url = export_response.get("download_url")
        if not download_url:
            raise SuperDocsClientError(
                f"export_document response for format={format!r} carried no download_url. "
                "Fix: binary formats (docx/pdf) are documented to return a signed "
                "download_url — check the response shape hasn't changed."
            )
        dest_path.write_bytes(await downloader(download_url))
    return dest_path


async def generate_pack(
    country_code: str,
    *,
    ledger: Ledger | None = None,
    manifest: dict | None = None,
    country: dict | None = None,
    out_dir: Path = OUT_DIR,
    client_factory=SuperDocsClient,
    downloader=_default_downloader,
) -> dict:
    """Generate one country's pack: upload, one batched annex edit, approve.

    Flow: upload the master, send ONE chat call replacing every annex section
    at once, parse the proposed changes, then approve. approve_change only
    works against a chat_async job_id; a synchronous chat() preview never
    creates one (see PROGRESS.md, proven live in scripts/smoke.py), so when
    approve fails as documented, this falls back to a second chat call with
    the default approval_mode (approve_all) to actually apply the edit. The
    preview call is free, so the pack still costs the single operation
    CLAUDE.md's economics assume.

    Idempotent: if a pack for this country and core_version was already
    charged in `ledger` (its persisted state, loaded by the caller) and its
    exported files are still on disk, no SuperDocs call is made at all and
    the run is recorded as SKIPPED at 0 operations — CLAUDE.md's rule that
    an operation already bought for the same inputs is not re-bought.
    """
    ledger = ledger if ledger is not None else Ledger()
    manifest = manifest if manifest is not None else config_module.load_manifest()
    country = (
        country
        if country is not None
        else config_module.load_country(config_module.COUNTRIES_DIR / f"{country_code}.yaml")
    )

    pack_dir = out_dir / country_code
    content_key = _content_key(country_code, manifest["core_version"])

    if ledger.already_charged(content_key) and _pack_files_exist(pack_dir):
        ledger.record(
            "pack", country_code, chat_calls=0, wall_time=0.0,
            content_key=content_key, output_exists=True,
        )
        return {
            "country_code": country_code,
            "session_id": None,
            "instruction": None,
            "exports": {fmt: pack_dir / filename for fmt, filename in _EXPORT_FILES},
            "skipped": True,
        }

    instruction = build_instruction(manifest, country)
    assert_no_core_sections_named(instruction, manifest)

    session_id = f"pack-{country_code.lower()}"
    file_base64 = base64.b64encode(POLICY_MASTER_PATH.read_bytes()).decode("ascii")

    async with client_factory() as client:
        started = time.monotonic()
        await client.upload(filename="policy-master.md", file_base64=file_base64, session_id=session_id)
        ledger.record("upload", country_code, chat_calls=0, wall_time=time.monotonic() - started)

        started = time.monotonic()
        preview = await client.chat(
            message=instruction, session_id=session_id,
            approval_mode="ask_every_time", response_mode="compact",
        )
        ledger.record(
            "chat", f"{country_code} annex edit (preview)",
            chat_calls=ops_from_response(preview), wall_time=time.monotonic() - started,
        )
        changes = parse_proposed_changes(preview)

        started = time.monotonic()
        try:
            for change in changes:
                await client.approve(
                    session_id=session_id, job_id=session_id,
                    change_id=change["change_id"], approved=True,
                )
            ledger.record("approve", country_code, chat_calls=0, wall_time=time.monotonic() - started)
        except SuperDocsClientError:
            ledger.record(
                "approve", f"{country_code} (failed, falling back)",
                chat_calls=0, wall_time=time.monotonic() - started,
            )
            started = time.monotonic()
            apply_response = await client.chat(
                message=instruction, session_id=session_id, response_mode="compact"
            )
            ledger.record(
                "chat", f"{country_code} annex edit (apply)",
                chat_calls=ops_from_response(apply_response), wall_time=time.monotonic() - started,
            )

            match = _PARTIAL_APPLY_RE.search(apply_response.get("response") or "")
            if match and match.group(1) != match.group(2):
                # A partial batch apply is resolved by resending the identical
                # batched instruction, not by targeting only the missed
                # section: a single-section retry was observed live to
                # collide with the still-settling batched edit and produce a
                # merged section containing both the old and new text. One
                # bounded retry; whatever lands is caught by verify_pack below.
                started = time.monotonic()
                retry_response = await client.chat(
                    message=instruction, session_id=session_id, response_mode="compact"
                )
                ledger.record(
                    "chat", f"{country_code} annex edit (retry incomplete batch)",
                    chat_calls=ops_from_response(retry_response), wall_time=time.monotonic() - started,
                )

        started = time.monotonic()
        markdown_export = await client.export(session_id=session_id, format="markdown")
        ledger.record("export-markdown", country_code, chat_calls=0, wall_time=time.monotonic() - started)
        markdown_text = markdown_export.get("text") or markdown_export.get("markdown") or markdown_export.get("content")

        verification = verify_pack(markdown_text, manifest, country["language"])
        if not verification["passed"]:
            raise PackIntegrityError(
                f"{country_code} pack failed verification and was quarantined — "
                f"core: {verification['core']}, "
                f"unlocalised annex sections: {verification['unlocalised_annex_sections']}. "
                "Not exported; the run does not report success for this country."
            )

        markdown_filename = next(filename for fmt, filename in _EXPORT_FILES if fmt == "markdown")
        exports = {"markdown": await _write_export(markdown_export, pack_dir / markdown_filename, "markdown")}
        for fmt, filename in _EXPORT_FILES:
            if fmt == "markdown":
                continue
            started = time.monotonic()
            export_response = await client.export(session_id=session_id, format=fmt)
            dest = await _write_export(export_response, pack_dir / filename, fmt, downloader=downloader)
            ledger.record(f"export-{fmt}", country_code, chat_calls=0, wall_time=time.monotonic() - started)
            exports[fmt] = dest

    # Marks this content_key as charged for future idempotency checks (see the
    # early-return above), without adding to total_operations a second time —
    # the actual operation was already counted by the chat step(s) above.
    ledger.record(
        "pack", country_code, chat_calls=0, wall_time=0.0,
        content_key=content_key, output_exists=False,
    )

    return {
        "country_code": country_code,
        "session_id": session_id,
        "instruction": instruction,
        "exports": exports,
        "skipped": False,
    }
