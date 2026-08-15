"""Records operation counts and idempotency state for cost accounting."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LedgerEntry:
    step: str
    subject: str
    operations: int
    wall_time: float
    status: str = "CHARGED"
    content_key: str | None = None


class Ledger:
    """The run's cost record: one entry per step, operations charged, wall time.

    Charging follows CLAUDE.md's economics section: a chat call is 1 operation;
    everything else (lock/hash, upload, export, download, ack rendering) is 0.
    Callers report the number of chat calls a step made via `chat_calls` —
    that count is exactly what gets charged.
    """

    def __init__(self):
        self.entries: list[LedgerEntry] = []

    def record(
        self,
        step: str,
        subject: str,
        chat_calls: int,
        wall_time: float,
    ) -> LedgerEntry:
        entry = LedgerEntry(step=step, subject=subject, operations=chat_calls, wall_time=wall_time)
        self.entries.append(entry)
        return entry

    @property
    def total_operations(self) -> int:
        return sum(e.operations for e in self.entries)
