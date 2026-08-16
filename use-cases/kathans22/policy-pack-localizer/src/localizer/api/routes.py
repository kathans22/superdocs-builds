"""Thin HTTP routes over service.py / config.py.

No route computes anything the CLI (__main__.py) or a script could not
already get from the same underlying functions. A route's job is to load
config, call service.py, and shape the response as JSON.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from .. import config as config_module
from .. import packs
from .. import service
from . import runs as runs_module

router = APIRouter()


class RolloutRequest(BaseModel):
    countries: list[str]
    limit: int | None = None


class AmendmentRequest(BaseModel):
    countries: list[str]


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


def _reject_unknown_countries(codes: list[str]) -> None:
    unknown = [code for code in codes if code not in config_module.load_all_countries()]
    if unknown:
        label = "country" if len(unknown) == 1 else "countries"
        raise HTTPException(status_code=404, detail=f"Unknown {label}: {unknown!r}")


@router.post("/runs/rollout", status_code=202)
def start_rollout(request: RolloutRequest, background_tasks: BackgroundTasks) -> dict:
    """Kick off core-lock + pack generation for the given countries in the
    background and return immediately with a run id to poll — a rollout can
    legitimately take minutes per country (CLAUDE.md: no aggressive
    timeouts), so the request must not wait on it."""
    _reject_unknown_countries(request.countries)
    run = runs_module.create_run("rollout")
    background_tasks.add_task(runs_module.execute_rollout, run.run_id, request.countries, request.limit)
    return run.to_summary()


@router.post("/runs/amendment", status_code=202)
def start_amendment(request: AmendmentRequest, background_tasks: BackgroundTasks) -> dict:
    """Kick off core re-lock + per-country change-notice generation in the
    background and return immediately with a run id to poll. Zero packs are
    reissued by this — see service.run_amendment."""
    _reject_unknown_countries(request.countries)
    run = runs_module.create_run("amendment")
    background_tasks.add_task(runs_module.execute_amendment, run.run_id, request.countries)
    return run.to_summary()


@router.get("/runs/{run_id}")
def get_run_status(run_id: str) -> dict:
    """Poll a run's status without blocking — a run still `running` is not
    a failed run (CLAUDE.md: SuperDocs calls legitimately take 30s to
    several minutes with no visible progress; that is processing, not a
    crash). `result` is populated once `status` is `done`; `error` once
    `status` is `error`."""
    run = runs_module.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No run {run_id!r}.")
    return {**run.to_summary(), "result": run.result, "error": run.error}


@router.get("/runs/{run_id}/ledger")
def get_run_ledger(run_id: str) -> dict:
    """The operations this specific run actually spent, step by step — not
    the whole account's cumulative ledger. Entries are the slice of
    state/ledger.json written during this run only (runs.execute_rollout /
    execute_amendment record the entry count before the run starts and
    slice from there), so two runs never double-report each other's cost."""
    run = runs_module.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No run {run_id!r}.")
    total_operations = sum(entry["operations"] for entry in run.ledger_entries)
    return {"run_id": run_id, "status": run.status, "entries": run.ledger_entries, "total_operations": total_operations}
