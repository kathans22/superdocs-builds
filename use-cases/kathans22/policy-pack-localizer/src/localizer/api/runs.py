"""In-process background run tracking for long SuperDocs operations.

A rollout or amendment can legitimately take minutes (CLAUDE.md: "never add
an aggressive timeout"). Routes must not block a request for that long, so
a run is scheduled, given an id immediately, and executed in the background;
the caller polls for status instead of waiting on the connection.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import service
from ..ledger import Ledger


def _jsonable(value: Any) -> Any:
    """Recursively convert Path objects to strings so a run's result can be
    returned as JSON. Ledger objects are excluded deliberately — their
    entries are exposed through the dedicated ledger endpoint, not
    embedded in a run's result."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Ledger):
        return None
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


@dataclass
class Run:
    run_id: str
    kind: str  # "rollout" | "amendment"
    status: str = "pending"  # pending | running | done | error
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None
    ledger_entries: list[dict] = field(default_factory=list)

    def to_summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


# In-process only: a run's status does not survive a restart. Acceptable
# here because the operations themselves (locks, packs, notices) are the
# durable, idempotent state — a lost run record just means re-polling
# fails and the run must be kicked off again, which costs nothing extra
# per CLAUDE.md's idempotency rule (already-charged work is skipped).
_RUNS: dict[str, Run] = {}


def create_run(kind: str) -> Run:
    run = Run(run_id=uuid.uuid4().hex, kind=kind)
    _RUNS[run.run_id] = run
    return run


def get_run(run_id: str) -> Run | None:
    return _RUNS.get(run_id)


async def execute_rollout(run_id: str, country_codes: list[str], limit: int | None) -> None:
    run = _RUNS[run_id]
    run.status = "running"
    baseline = len(Ledger.load().entries)
    try:
        outcome = await service.run(country_codes, limit=limit)
        run.result = _jsonable({"results": outcome["results"]})
        run.ledger_entries = [asdict(e) for e in outcome["ledger"].entries[baseline:]]
        run.status = "done"
    except Exception as exc:  # noqa: BLE001 — a run's own failure must not crash the process
        run.status = "error"
        run.error = str(exc)
    finally:
        run.finished_at = datetime.now(timezone.utc).isoformat()


async def execute_amendment(run_id: str, country_codes: list[str]) -> None:
    run = _RUNS[run_id]
    run.status = "running"
    baseline = len(Ledger.load().entries)
    try:
        outcome = await service.run_amendment(country_codes)
        run.result = _jsonable(
            {
                "diff": outcome["diff"],
                "notices": outcome["notices"],
                "verification": outcome["verification"],
            }
        )
        run.ledger_entries = [asdict(e) for e in outcome["ledger"].entries[baseline:]]
        run.status = "done"
    except Exception as exc:  # noqa: BLE001 — a run's own failure must not crash the process
        run.status = "error"
        run.error = str(exc)
    finally:
        run.finished_at = datetime.now(timezone.utc).isoformat()
