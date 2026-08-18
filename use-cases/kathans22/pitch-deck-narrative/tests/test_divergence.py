"""Hand-made divergence fixtures — no SuperDocs, no network."""

from __future__ import annotations

from generator.divergence import (
    VERTICAL_MEAN_MAX,
    VERTICAL_SECTION_MAX,
    evaluate_divergence,
    score_all,
    score_pair,
)


def test_identical_texts_score_maximum_overlap() -> None:
    text = (
        "ClarityDocs stages every finding for human approval before anything commits."
    )
    assert score_pair(text, text) == 1.0
    assert score_pair("", "") == 0.0


def test_template_and_swap_scores_high_and_is_caught() -> None:
    """Only the buyer noun changes — scorer must flag this as a swap failure."""
    legal = (
        "The legal team reviews every finding before it commits to the client pack."
    )
    compliance = (
        "The compliance team reviews every finding before it commits to the client pack."
    )
    overlap = score_pair(legal, compliance)
    assert overlap >= VERTICAL_SECTION_MAX, overlap
    assert overlap >= 0.7, overlap

    weights = {7: "vertical"}
    report = score_all(
        {
            "legal": {7: legal},
            "fintech": {7: compliance},
        },
        weights,
    )
    evaluation = evaluate_divergence(report, weights)
    assert evaluation["passed"] is False
    assert evaluation["mean_vertical_overlap"] >= VERTICAL_MEAN_MAX
    assert any("template-and-swap" in f or ">=" in f for f in evaluation["failures"])
