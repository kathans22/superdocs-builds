"""Propagates a core amendment to affected languages and countries."""

from __future__ import annotations

from . import corelock


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
