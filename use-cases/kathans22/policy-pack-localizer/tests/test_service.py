"""Proves the integrity report aggregates per-language core identity from
each pack's actual exported core, not merely asserted from the lock."""

from __future__ import annotations

from localizer import config as config_module
from localizer import corelock
from localizer import packs
from localizer import sections as sections_module
from localizer import service


def _valid_pack_markdown(manifest: dict, country: dict) -> str:
    master_sections = sections_module.parse_sections(packs.POLICY_MASTER_PATH.read_text(encoding="utf-8"))
    body_by_number = {s["number"]: s["body"] for s in master_sections}
    lines = []
    for section in manifest["sections"]:
        lines.append(f"## {section['number']} {section['heading']}")
        lines.append("")
        if section["role"] == "core":
            lines.append(body_by_number[section["number"]])
        else:
            lines.append(packs._SLOT_RENDERERS[section["slot"]](country))
        lines.append("")
    return "\n".join(lines)


def _write_pack(out_dir, code: str, markdown: str) -> None:
    pack_dir = out_dir / code
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "policy-pack.md").write_text(markdown, encoding="utf-8")


def _lock_english_core(manifest: dict) -> None:
    master_sections = sections_module.parse_sections(packs.POLICY_MASTER_PATH.read_text(encoding="utf-8"))
    core_numbers = {s["number"] for s in manifest["sections"] if s["role"] == "core"}
    core_sections = [s for s in master_sections if s["number"] in core_numbers]
    corelock.save_lock(corelock.lock(core_sections, manifest["core_version"], "en"))


def test_integrity_report_marks_identical_core_across_two_english_packs(tmp_path, monkeypatch):
    manifest = config_module.load_manifest()
    monkeypatch.setattr(corelock, "STATE_DIR", tmp_path / "state")
    _lock_english_core(manifest)

    in_country = config_module.load_country(config_module.COUNTRIES_DIR / "IN.yaml")
    ke_country = config_module.load_country(config_module.COUNTRIES_DIR / "KE.yaml")
    out_dir = tmp_path / "out"
    _write_pack(out_dir, "IN", _valid_pack_markdown(manifest, in_country))
    _write_pack(out_dir, "KE", _valid_pack_markdown(manifest, ke_country))

    report = service.integrity_report(["IN", "KE"], manifest=manifest, out_dir=out_dir)

    assert report["core_version"] == manifest["core_version"]
    assert report["packs"] == 2
    assert report["languages"] == {"en": 2}
    assert report["core_identity"]["en"]["identical"] is True
    assert report["core_identity"]["en"]["packs"] == ["IN", "KE"]
    assert report["all_packs_pass"] is True


def test_integrity_report_flags_a_diverged_core_as_not_identical(tmp_path, monkeypatch):
    manifest = config_module.load_manifest()
    monkeypatch.setattr(corelock, "STATE_DIR", tmp_path / "state")
    _lock_english_core(manifest)

    in_country = config_module.load_country(config_module.COUNTRIES_DIR / "IN.yaml")
    ke_country = config_module.load_country(config_module.COUNTRIES_DIR / "KE.yaml")
    out_dir = tmp_path / "out"
    _write_pack(out_dir, "IN", _valid_pack_markdown(manifest, in_country))
    corrupted = _valid_pack_markdown(manifest, ke_country).replace(
        "Meridian Relief Trust (MRT) exists", "Meridian Relief Trust (MRT) no longer exists", 1
    )
    _write_pack(out_dir, "KE", corrupted)

    report = service.integrity_report(["IN", "KE"], manifest=manifest, out_dir=out_dir)

    assert report["core_identity"]["en"]["identical"] is False
    assert report["all_packs_pass"] is False
