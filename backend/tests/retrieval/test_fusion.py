"""Unit tests for app.retrieval.fusion. Pure Python, no I/O."""

from app.retrieval.fusion import reciprocal_rank_fusion


def test_fuses_two_identical_rankings() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["a", "b", "c"]], limit=10)
    # Identical ranks double the score; order preserved.
    assert [id_ for id_, _ in fused] == ["a", "b", "c"]
    assert fused[0][1] > fused[1][1] > fused[2][1]


def test_item_in_both_lists_beats_item_in_one() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["c", "a"]], limit=10)
    scores = dict(fused)
    # "a" appears in both lists, so it fuses to the top.
    assert next(iter(scores)) == "a"
    assert scores["a"] > scores["b"]
    assert scores["a"] > scores["c"]


def test_rank_not_score_semantics() -> None:
    # Being rank 1 in one list outweighs rank 2 in another by exactly the
    # RRF shape, regardless of any underlying score magnitude.
    fused = reciprocal_rank_fusion([["a"], ["x", "a"]], limit=10)
    scores = dict(fused)
    assert scores["a"] == 1 / 61 + 1 / 62


def test_limit_truncates() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c", "d"]], limit=2)
    assert [id_ for id_, _ in fused] == ["a", "b"]


def test_duplicates_within_a_list_ignored() -> None:
    fused = reciprocal_rank_fusion([["a", "a", "b"]], limit=10)
    scores = dict(fused)
    assert scores["a"] == 1 / 61  # second occurrence contributes nothing


def test_empty_inputs() -> None:
    assert reciprocal_rank_fusion([], limit=5) == []
    assert reciprocal_rank_fusion([[], []], limit=5) == []


def test_ties_preserve_first_appearance() -> None:
    assert [id_ for id_, _ in reciprocal_rank_fusion([["z"], ["a"]], 2)] == ["z", "a"]


def test_duplicates_do_not_change_later_ranks() -> None:
    assert reciprocal_rank_fusion([["a", "a", "b"]], 2) == reciprocal_rank_fusion(
        [["a", "b"]], 2
    )
