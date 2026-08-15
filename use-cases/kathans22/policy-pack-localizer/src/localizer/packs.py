"""Generates per-country packs by batching the annex replacement into one call."""

from __future__ import annotations

import base64
import re
import time
from pathlib import Path

from . import config as config_module
from .ledger import Ledger, ops_from_response
from .mcp_client import SuperDocsClient, SuperDocsClientError, parse_proposed_changes

ROOT = Path(__file__).resolve().parents[2]
POLICY_MASTER_PATH = config_module.CONFIG_DIR / "policy-master.md"
OUT_DIR = ROOT / "out"

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


async def generate_pack(
    country_code: str,
    *,
    ledger: Ledger | None = None,
    manifest: dict | None = None,
    country: dict | None = None,
    client_factory=SuperDocsClient,
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
    """
    ledger = ledger if ledger is not None else Ledger()
    manifest = manifest if manifest is not None else config_module.load_manifest()
    country = (
        country
        if country is not None
        else config_module.load_country(config_module.COUNTRIES_DIR / f"{country_code}.yaml")
    )

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

    return {"country_code": country_code, "session_id": session_id, "instruction": instruction}
