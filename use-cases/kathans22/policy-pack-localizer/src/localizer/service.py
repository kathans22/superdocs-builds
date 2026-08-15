"""Top-level orchestration entry points used by the API layer.

The single place lock/generate/verify are called from. The CLI (__main__.py)
and any future FastAPI route both call these functions; neither reimplements
the sequence itself.
"""

from __future__ import annotations

from pathlib import Path

from . import config as config_module
from . import corelock
from . import packs
from . import sections as sections_module
from .ledger import Ledger, apply_limit


def lock_core(manifest: dict | None = None, language: str | None = None) -> dict:
    """Lock policy-master.md's core sections for one language. 0 ops — arithmetic."""
    manifest = manifest if manifest is not None else config_module.load_manifest()
    language = language or manifest["source_language"]

    master_sections = sections_module.parse_sections(
        packs.POLICY_MASTER_PATH.read_text(encoding="utf-8")
    )
    sections_module.assert_matches_manifest(master_sections, manifest)

    core_numbers = {s["number"] for s in manifest["sections"] if s["role"] == "core"}
    core_sections = [s for s in master_sections if s["number"] in core_numbers]

    lock_data = corelock.lock(core_sections, manifest["core_version"], language)
    corelock.save_lock(lock_data)
    return lock_data


async def generate(
    country_code: str,
    *,
    ledger: Ledger,
    manifest: dict | None = None,
    out_dir: Path = packs.OUT_DIR,
) -> dict:
    """Generate one country's pack. Thin wrapper over packs.generate_pack —
    the entry point everything else calls, so nothing reimplements it."""
    manifest = manifest if manifest is not None else config_module.load_manifest()
    return await packs.generate_pack(country_code, ledger=ledger, manifest=manifest, out_dir=out_dir)


def verify(country_code: str, manifest: dict | None = None, out_dir: Path = packs.OUT_DIR) -> dict:
    """Re-verify an already-generated pack on disk against the locked core."""
    manifest = manifest if manifest is not None else config_module.load_manifest()
    country = config_module.load_country(config_module.COUNTRIES_DIR / f"{country_code}.yaml")
    markdown_filename = next(filename for fmt, filename in packs._EXPORT_FILES if fmt == "markdown")
    pack_path = out_dir / country_code / markdown_filename
    markdown_text = pack_path.read_text(encoding="utf-8")
    return packs.verify_pack(markdown_text, manifest, country["language"])


def integrity_report(
    country_codes: list[str], manifest: dict | None = None, out_dir: Path = packs.OUT_DIR
) -> dict:
    """Build the integrity report: core identity per language, proved from
    every generated pack's actual exported core, not assumed from the lock.

    For each language present in `country_codes`, `expected` is the locked
    core_hash (corelock.load_lock) and `identical` is True only if every
    pack in that language, re-hashed from its own export, matches it —
    the same mechanism packs.verify_pack uses per pack, aggregated here
    across the whole run.
    """
    manifest = manifest if manifest is not None else config_module.load_manifest()
    core_version = manifest["core_version"]
    markdown_filename = next(filename for fmt, filename in packs._EXPORT_FILES if fmt == "markdown")

    annex_slots = [s["slot"] for s in manifest["sections"] if s["role"] == "annex" and s["slot"] != "acknowledgement"]
    slot_by_number = {s["number"]: s["slot"] for s in manifest["sections"] if s["role"] == "annex"}
    annex_bodies: dict[str, dict[str, str]] = {slot: {} for slot in annex_slots}

    languages: dict[str, int] = {}
    core_identity: dict[str, dict] = {}
    all_pass = True

    for code in country_codes:
        country = config_module.load_country(config_module.COUNTRIES_DIR / f"{code}.yaml")
        language = country["language"]
        languages[language] = languages.get(language, 0) + 1

        markdown_text = (out_dir / code / markdown_filename).read_text(encoding="utf-8")
        verification = packs.verify_pack(markdown_text, manifest, language)
        all_pass = all_pass and verification["passed"]

        actual_hash = corelock.lock(
            verification["exported_core_sections"], core_version, language
        )["core_hash"]
        entry = core_identity.setdefault(
            language,
            {"expected": corelock.load_lock(core_version, language)["core_hash"], "packs": [], "identical": True},
        )
        entry["packs"].append(code)
        if actual_hash != entry["expected"]:
            entry["identical"] = False

        for section in sections_module.parse_sections(markdown_text):
            slot = slot_by_number.get(section["number"])
            if slot in annex_bodies:
                annex_bodies[slot][code] = corelock.normalise(section["body"])

    for entry in core_identity.values():
        entry["packs"].sort()

    # Counted, not claimed: the same normalise() lock/verify use, so a
    # cosmetic export difference never inflates the distinct count — only a
    # genuine content difference does. acknowledgement is excluded: it is
    # deterministic office/date/name fields, not a claim about country
    # specificity, and would trivially read as "N distinct" for the wrong
    # reason (every office name differs).
    annex_divergence = {
        slot: f"{len(set(bodies.values()))} distinct" for slot, bodies in annex_bodies.items()
    }

    return {
        "core_version": core_version,
        "packs": len(country_codes),
        "languages": languages,
        "core_identity": core_identity,
        "all_packs_pass": all_pass,
        "annex_divergence": annex_divergence,
    }


async def run(
    country_codes: list[str],
    *,
    limit: int | None = None,
    out_dir: Path = packs.OUT_DIR,
) -> dict:
    """Lock the core, then generate a pack per country (respecting --limit).

    Loads the persisted ledger so a resumed run does not double-count, and
    saves it back at the end. This is what the CLI's `run` command calls.
    """
    ledger = Ledger.load()
    manifest = config_module.load_manifest()

    lock_core(manifest=manifest)

    codes = apply_limit(country_codes, limit)
    results = {}
    for code in codes:
        results[code] = await generate(code, ledger=ledger, manifest=manifest, out_dir=out_dir)

    ledger.save()
    return {"results": results, "ledger": ledger}
