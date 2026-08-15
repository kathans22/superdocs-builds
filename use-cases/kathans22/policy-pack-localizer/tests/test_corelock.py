"""Proves the core-lock mechanism: identity, sensitivity, and normalisation resilience."""

from __future__ import annotations

from pathlib import Path

from localizer import corelock, sections

FIXTURES = Path(__file__).parent / "fixtures"


def _core_sections(path: Path) -> list[dict]:
    return [s for s in sections.load_sections(path) if s["number"] <= 5]


def test_identical_core_in_two_different_files_produces_identical_hash():
    # fixture_a and fixture_b share byte-identical core sections 1-5 but have
    # completely different annex sections 6-9 — they are genuinely different files.
    core_a = _core_sections(FIXTURES / "policy_fixture_a.md")
    core_b = _core_sections(FIXTURES / "policy_fixture_b.md")

    lock_a = corelock.lock(core_a, core_version=1, language="en")
    lock_b = corelock.lock(core_b, core_version=1, language="en")

    assert lock_a["core_hash"] == lock_b["core_hash"]
    assert lock_a["section_hashes"] == lock_b["section_hashes"]
