"""Thin HTTP routes over service.py / config.py.

No route computes anything the CLI (__main__.py) or a script could not
already get from the same underlying functions. A route's job is to load
config, call service.py, and shape the response as JSON.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import config as config_module
from .. import packs
from .. import service

router = APIRouter()


def _generated_country_codes() -> list[str]:
    """Country codes with a complete exported pack on disk, per packs.OUT_DIR.

    A pack "exists" only if every file packs._EXPORT_FILES lists is present
    — the same completeness check packs.generate_pack itself uses before
    treating a pack as already produced (idempotency), so this list never
    reports a half-written pack as generated.
    """
    codes = []
    for code in sorted(config_module.load_all_countries()):
        pack_dir = packs.OUT_DIR / code
        if all((pack_dir / filename).exists() for _, filename in packs._EXPORT_FILES):
            codes.append(code)
    return codes


@router.get("/countries")
def list_countries() -> list[dict]:
    """Every configured country — a data change (a new YAML file) is all it
    takes for one to appear here, per CLAUDE.md rule 5."""
    countries = config_module.load_all_countries()
    return [
        {
            "code": country["code"],
            "country": country["country"],
            "language": country["language"],
            "office": country["office"],
            "safeguarding_lead": country["safeguarding_lead"],
        }
        for country in countries.values()
    ]


@router.get("/packs")
def list_packs() -> list[dict]:
    """Every configured country, with whether its pack has actually been
    generated (files present in out/) — not just requested."""
    countries = config_module.load_all_countries()
    generated = set(_generated_country_codes())
    return [
        {"code": code, "country": country["country"], "language": country["language"], "generated": code in generated}
        for code, country in countries.items()
    ]


@router.get("/packs/{code}")
def get_pack(code: str) -> dict:
    """Re-verify one country's already-generated pack against its locked
    core — the same check packs.verify_pack runs after generation, run
    again here on demand rather than trusting a cached result."""
    if code not in config_module.load_all_countries():
        raise HTTPException(status_code=404, detail=f"No configured country {code!r}.")
    if code not in _generated_country_codes():
        raise HTTPException(status_code=404, detail=f"No generated pack for {code!r} yet.")
    return service.verify(code)


@router.get("/integrity")
def integrity_report(countries: str | None = None) -> dict:
    """The core-identity + annex-divergence report: proof, not assertion,
    that protected core text is identical across every generated pack in a
    language and that annexes genuinely diverge per country.

    `countries` is an optional comma-separated filter (e.g. `IN,KE`);
    defaults to every country with a generated pack on disk.
    """
    if countries:
        codes = [code.strip() for code in countries.split(",") if code.strip()]
        missing = [code for code in codes if code not in _generated_country_codes()]
        if missing:
            raise HTTPException(status_code=404, detail=f"No generated pack for {missing!r} yet.")
    else:
        codes = _generated_country_codes()
    if not codes:
        raise HTTPException(status_code=404, detail="No generated packs yet — run a rollout first.")
    return service.integrity_report(codes)
