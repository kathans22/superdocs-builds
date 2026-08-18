"""Hand-made divergence fixtures — no SuperDocs, no network."""

from __future__ import annotations

from generator.divergence import score_pair


def test_identical_texts_score_maximum_overlap() -> None:
    text = (
        "ClarityDocs stages every finding for human approval before anything commits."
    )
    assert score_pair(text, text) == 1.0
    assert score_pair("", "") == 0.0
