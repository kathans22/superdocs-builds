"""Thin FastAPI routes over service.py — no SuperDocs, no network."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import generator.api.app as api_mod
from generator.api.app import app


def test_list_verticals() -> None:
    client = TestClient(app)
    response = client.get("/verticals")
    assert response.status_code == 200
    body = response.json()
    assert set(body["verticals"]) >= {"legal", "fintech", "healthcare", "edtech"}
    assert body["product"] == "ClarityDocs"


def test_generate_unknown_vertical_is_404() -> None:
    client = TestClient(app)
    response = client.post("/generate", params={"vertical": "not-a-vertical"})
    assert response.status_code == 404


def test_generate_calls_service(monkeypatch) -> None:
    async def fake_run_verticals(vertical, **kwargs):
        return {"requested": vertical, "verticals": [vertical], "results": [], "ops_total": 0}

    monkeypatch.setattr(api_mod, "run_verticals", fake_run_verticals)
    client = TestClient(app)
    response = client.post("/generate", params={"vertical": "legal"})
    assert response.status_code == 200
    assert response.json()["requested"] == "legal"


def test_fetch_narrative_export(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "pitch-script-legal-claritydocs.md"
    script.write_text(
        "# ClarityDocs — Pitch Speaking Script\n\n**Speaking script — not a slide deck.**\n",
        encoding="utf-8",
    )

    def fake_path(vertical_code: str, fmt: str = "markdown", **kwargs) -> Path:
        assert vertical_code == "legal"
        return script

    monkeypatch.setattr(api_mod, "narrative_export_path", fake_path)
    client = TestClient(app)
    response = client.get("/narratives/legal")
    assert response.status_code == 200
    assert "Speaking script" in response.text


def test_divergence_and_ledger_routes() -> None:
    client = TestClient(app)
    div = client.get("/divergence")
    assert div.status_code == 200
    body = div.json()
    assert "verticals" in body or body.get("status") == "deferred"
    led = client.get("/ledger")
    assert led.status_code == 200
    snap = led.json()
    assert "total_operations" in snap
    assert "entries" in snap
    assert isinstance(snap["entries"], list)
