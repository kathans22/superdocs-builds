"""Propagates a core amendment to affected languages and countries."""

from __future__ import annotations

import base64
import time

from . import config as config_module
from . import corelock
from . import sections as sections_module
from .ledger import Ledger, ops_from_response
from .mcp_client import SuperDocsClient, SuperDocsClientError

POLICY_MASTER_PATH = config_module.CONFIG_DIR / "policy-master.md"

# Falls back to the raw ISO code when a language isn't listed — adding a
# language must never require a code change here (CLAUDE.md rule 5); this
# dict only makes the instruction read naturally for the languages we know.
_LANGUAGE_NAMES = {"fr": "French", "pt": "Portuguese"}


def diff_core_versions(manifest: dict, language: str, from_version: int, to_version: int) -> dict:
    """Which core sections changed between two locked versions, for one language.

    Compares only the persisted section hashes from
    state/core-lock-v{version}-{lang}.json — no document is read and no
    SuperDocs call is made. Zero operations: this is hash comparison, not
    intelligence. A section is "changed" only if its own locked hash
    differs; every other core section is scoped out before any later step
    (re-translation, notice generation) ever looks at it.
    """
    from_lock = corelock.load_lock(from_version, language)
    to_lock = corelock.load_lock(to_version, language)

    core_numbers = sorted(s["number"] for s in manifest["sections"] if s["role"] == "core")

    changed_sections = []
    unchanged_sections = []
    for number in core_numbers:
        key = str(number)
        from_hash = from_lock["section_hashes"].get(key)
        to_hash = to_lock["section_hashes"].get(key)
        if from_hash is None or to_hash is None:
            raise ValueError(
                f"section {number} is not covered by both the v{from_version} and "
                f"v{to_version} {language!r} locks — a core section was added or "
                "removed, not just edited; diff_core_versions only compares "
                "sections present in both locks."
            )
        if from_hash != to_hash:
            changed_sections.append(number)
        else:
            unchanged_sections.append(number)

    return {
        "language": language,
        "from_version": from_version,
        "to_version": to_version,
        "core_sections_total": len(core_numbers),
        "changed_sections": changed_sections,
        "unchanged_sections": unchanged_sections,
    }


def _join_numbers(numbers: list[int]) -> str:
    return ", ".join(str(n) for n in numbers)


def format_diff_report(diff: dict) -> str:
    """"Section 4 changed, 1 of 5" — and name every section that did not.

    Naming what did NOT change is not decoration: it is what lets a country
    office trust a change notice built from this diff without re-reading
    the whole core. `changed_sections` and `unchanged_sections` are already
    disjoint and exhaustive over every core section (diff_core_versions
    enforces that every core section lands in exactly one), so this only
    formats what is already known — no new comparison happens here.
    """
    changed = diff["changed_sections"]
    unchanged = diff["unchanged_sections"]
    total = diff["core_sections_total"]

    if not changed:
        return (
            f"No core sections changed between v{diff['from_version']} and "
            f"v{diff['to_version']} ({diff['language']}). All {total} unchanged."
        )

    changed_label = "section" if len(changed) == 1 else "sections"
    header = (
        f"{changed_label.capitalize()} {_join_numbers(changed)} changed, "
        f"{len(changed)} of {total}."
    )
    if not unchanged:
        return header

    return f"{header} Section{'s' if len(unchanged) != 1 else ''} {_join_numbers(unchanged)} unchanged."


def _build_retranslation_instruction(manifest: dict, language: str, changed_numbers: list[int]) -> str:
    """The one instruction in this module that legitimately names core section
    numbers — mirrors translate.py's _build_translation_instruction, but
    scoped to only the sections that changed in this amendment, not every
    core section. Every section not listed, core or annex, must be left
    exactly as it is including its language: re-translating a section that
    did not change would produce different bytes for identical meaning and
    would silently break the "unchanged sections carry forward byte for
    byte" guarantee this module exists to protect.

    Like translate.py, this module deliberately never imports packs.py, so
    packs.assert_no_core_sections_named — the guard built to reject an
    instruction naming a core section — is structurally unreachable from
    this path, not just unused.
    """
    heading_by_number = {s["number"]: s["heading"] for s in manifest["sections"]}
    language_name = _LANGUAGE_NAMES.get(language, language)
    lines = [
        f"Translate ONLY the following section(s) of this policy into {language_name}, "
        "preserving their legal meaning exactly and keeping each section's clause "
        "numbering (its leading section number) unchanged. Do not add, remove, or "
        "reword anything in any other section — every section not listed below must "
        "be left exactly as it is in the source document, including its language.",
        "",
    ]
    for number in changed_numbers:
        lines.append(f'Section {number} "{heading_by_number[number]}"')
    return "\n".join(lines)


async def _translate_changed_sections(
    manifest: dict,
    language: str,
    changed_numbers: list[int],
    *,
    ledger: Ledger,
    client_factory=SuperDocsClient,
) -> dict[int, dict]:
    """Send exactly one chat call translating `changed_numbers` into
    `language`, from the current (v2) policy-master.md, and return the
    translated section dicts keyed by number.

    Cost: one operation for this call, regardless of how many sections are
    in `changed_numbers` or how many countries share `language` — the same
    per-language, not per-country, economics as translate.derive_core. The
    caller (retranslate_changed_sections) is responsible for combining this
    with the unchanged sections carried forward from the prior lock; this
    function only ever touches the sections it was told changed.
    """
    instruction = _build_retranslation_instruction(manifest, language, changed_numbers)
    session_id = f"amend-translate-{language}-v{manifest['core_version']}"
    file_base64 = base64.b64encode(POLICY_MASTER_PATH.read_bytes()).decode("ascii")

    async with client_factory() as client:
        started = time.monotonic()
        await client.upload(filename="policy-master.md", file_base64=file_base64, session_id=session_id)
        ledger.record("upload", language, chat_calls=0, wall_time=time.monotonic() - started)

        started = time.monotonic()
        response = await client.chat(message=instruction, session_id=session_id, response_mode="compact")
        ledger.record(
            "chat", f"retranslate {language} sections {changed_numbers}",
            chat_calls=ops_from_response(response), wall_time=time.monotonic() - started,
        )

        started = time.monotonic()
        export = await client.export(session_id=session_id, format="markdown")
        ledger.record("export-markdown", language, chat_calls=0, wall_time=time.monotonic() - started)

    markdown_text = export.get("text") or export.get("markdown") or export.get("content")
    if not markdown_text:
        raise SuperDocsClientError(
            f"export_document response for the {language!r} section re-translation "
            "carried no text. Fix: check the response shape hasn't changed."
        )

    all_sections = sections_module.parse_sections(markdown_text)
    changed_set = set(changed_numbers)
    translated = {s["number"]: s for s in all_sections if s["number"] in changed_set}

    missing = changed_set - set(translated)
    if missing:
        raise SuperDocsClientError(
            f"Re-translation export for {language!r} is missing section(s) "
            f"{sorted(missing)} — requested {sorted(changed_set)}. Fix: the "
            "instruction named these sections; check the export text or retry."
        )
    return translated
