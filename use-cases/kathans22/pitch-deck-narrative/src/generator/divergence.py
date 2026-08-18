"""Pairwise lexical-overlap scoring for narrative section texts.

Measurement first, generation second — zero SuperDocs operations. Arithmetic only.
"""

from __future__ import annotations

import re
from itertools import combinations
from statistics import mean
from typing import Any, Mapping

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")

SectionKey = int | str
Narratives = Mapping[str, Mapping[SectionKey, str]]
SectionWeights = Mapping[SectionKey, str]


def normalize_tokens(text: str) -> frozenset[str]:
    """Lowercase alphanumeric tokens; punctuation stripped. No stemming, no stopword list."""
    if not text:
        return frozenset()
    return frozenset(_TOKEN_RE.findall(text.lower()))


def score_pair(text_a: str, text_b: str) -> float:
    """Return word-level Jaccard similarity between two section texts.

    Why Jaccard (not embeddings / cosine over TF-IDF):
    - Dependency-light — stdlib only; no model call and no ops cost.
    - Interpretable — |A∩B| / |A∪B| is a number a reviewer can recompute by hand.
    - Sensitive to template-and-swap — noun-swapped scripts share most function and
      structure words, so the union barely grows while the intersection stays large;
      genuinely different objections and proof points shrink the intersection.

    Returns 0.0 when both sides are empty (no signal). Returns 0.0 when only one side
    has tokens (no shared vocabulary to claim overlap). Otherwise a float in [0.0, 1.0].
    """
    tokens_a = normalize_tokens(text_a)
    tokens_b = normalize_tokens(text_b)
    if not tokens_a and not tokens_b:
        return 0.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _section_keys(narratives: Narratives) -> list[SectionKey]:
    keys: set[SectionKey] = set()
    for sections in narratives.values():
        keys.update(sections.keys())
    return sorted(keys, key=lambda k: (str(type(k)), k))


def score_all(
    narratives: Narratives,
    section_weights: SectionWeights,
) -> dict[str, Any]:
    """Score every vertical pair on every section; aggregate means by weight tag.

    Parameters
    ----------
    narratives:
        ``{vertical_name: {section_key: section_text}}``. Section keys must align
        with ``section_weights`` (typically section numbers from the deck manifest).
    section_weights:
        ``{section_key: \"shared\" | \"vertical\"}`` from the deck manifest.

    Returns
    -------
    report dict with:
      - ``pairs``: list of {vertical_a, vertical_b, sections: {section: score}}
      - ``aggregates``: mean overlap across all pair×section cells tagged
        ``vertical`` vs ``shared``
      - ``per_pair_aggregates``: same means broken out per vertical pair
    """
    verticals = sorted(narratives.keys())
    if len(verticals) < 2:
        raise ValueError("score_all requires at least two verticals")

    unknown = set(section_weights.values()) - {"shared", "vertical"}
    if unknown:
        raise ValueError(f"section_weights values must be shared|vertical, got {unknown}")

    sections = _section_keys(narratives)
    pairs: list[dict[str, Any]] = []
    vertical_scores: list[float] = []
    shared_scores: list[float] = []
    per_pair_aggregates: list[dict[str, Any]] = []

    for va, vb in combinations(verticals, 2):
        section_scores: dict[str, float] = {}
        pair_vertical: list[float] = []
        pair_shared: list[float] = []
        for section in sections:
            text_a = narratives[va].get(section, "")
            text_b = narratives[vb].get(section, "")
            score = score_pair(text_a, text_b)
            section_scores[str(section)] = score

            weight = section_weights.get(section)
            if weight is None:
                # try int/str coercion for manifest numbers loaded as int
                alt = int(section) if isinstance(section, str) and section.isdigit() else str(section)
                weight = section_weights.get(alt)  # type: ignore[arg-type]
            if weight == "vertical":
                vertical_scores.append(score)
                pair_vertical.append(score)
            elif weight == "shared":
                shared_scores.append(score)
                pair_shared.append(score)
            else:
                raise ValueError(
                    f"missing weight for section {section!r}; "
                    f"every scored section must be tagged shared|vertical"
                )

        pairs.append(
            {
                "vertical_a": va,
                "vertical_b": vb,
                "sections": section_scores,
            }
        )
        per_pair_aggregates.append(
            {
                "vertical_a": va,
                "vertical_b": vb,
                "mean_vertical_overlap": mean(pair_vertical) if pair_vertical else None,
                "mean_shared_overlap": mean(pair_shared) if pair_shared else None,
            }
        )

    return {
        "method": "word_jaccard",
        "verticals": verticals,
        "pairs": pairs,
        "aggregates": {
            "mean_vertical_overlap": mean(vertical_scores) if vertical_scores else None,
            "mean_shared_overlap": mean(shared_scores) if shared_scores else None,
            "vertical_cells": len(vertical_scores),
            "shared_cells": len(shared_scores),
        },
        "per_pair_aggregates": per_pair_aggregates,
    }
