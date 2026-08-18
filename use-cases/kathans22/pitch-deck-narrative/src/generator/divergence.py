"""Pairwise lexical-overlap scoring for narrative section texts.

Measurement first, generation second — zero SuperDocs operations. Arithmetic only.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")


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
