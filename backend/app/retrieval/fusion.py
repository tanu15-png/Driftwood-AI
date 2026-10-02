"""Reciprocal Rank Fusion in pure Python.

Fuses ranked lists by rank, not score: BM25-style full-text scores are
unbounded while cosine similarities live in [0, 1], so averaging raw scores
is meaningless. RRF is score-scale-free (Cormack et al., SIGIR 2009; k=60 is
the value from the original paper and still the default in production).
"""

from __future__ import annotations

from collections import defaultdict

# Smoothing constant from the original RRF paper.
RRF_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    limit: int,
) -> list[tuple[str, float]]:
    """Fuse ranked id lists into one ranking.

    Each input list is an ordered list of ids, best first (duplicates within
    a list are ignored). Returns up to `limit` (id, fused_score) pairs,
    highest score first; ties break by first appearance.
    """
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        seen: set[str] = set()
        for id_ in ranking:
            if id_ in seen:
                continue
            seen.add(id_)
            scores[id_] += 1.0 / (RRF_K + len(seen))
    return sorted(scores.items(), key=lambda item: -item[1])[:limit]
