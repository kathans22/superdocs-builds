"""Thin FastAPI routes over ``generator.service`` — machine driver, optional UI later."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from generator.service import (
    divergence_report,
    ledger_snapshot,
    list_verticals,
    narrative_export_path,
    run_verticals,
)

app = FastAPI(
    title="ClarityDocs pitch-script generator",
    description=(
        "Machine driver for speaking-script narratives. "
        "Not a slide deck. Generation is SuperDocs-backed via service.py."
    ),
    version="0.1.0",
)


def create_app() -> FastAPI:
    return app


@app.get("/verticals")
def get_verticals() -> dict:
    return list_verticals()


@app.post("/generate")
async def post_generate(
    vertical: str = Query(..., description="Vertical code, or 'all'."),
    force: bool = Query(False),
) -> dict:
    try:
        return await run_verticals(vertical, force=force)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/narratives/{vertical_code}")
def get_narrative(
    vertical_code: str,
    fmt: str = Query("markdown", alias="format"),
) -> FileResponse:
    try:
        path = narrative_export_path(vertical_code, fmt)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media = (
        "text/markdown; charset=utf-8"
        if path.suffix.lower() in {".md", ".markdown"}
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path, media_type=media, filename=path.name)


@app.get("/divergence")
def get_divergence() -> dict:
    return divergence_report()


@app.get("/ledger")
def get_ledger() -> dict:
    return ledger_snapshot()
