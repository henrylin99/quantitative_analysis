"""robust_score：K 段稳健分（0.6×中位 + 0.4×最差）。"""

import pytest

from app.services.robust_score import annotate_robust, robust_score, split_segments


def test_split_segments_keeps_order_and_covers_all():
    segs = split_segments(list(range(10)), n_segments=4)
    flat = [v for seg in segs for v in seg]
    assert flat == list(range(10))
    assert len(segs) == 4


def test_split_segments_drops_none_and_nan():
    segs = split_segments([1.0, None, 2.0, float("nan"), 3.0, 4.0], n_segments=2)
    flat = [v for seg in segs for v in seg]
    assert flat == [1.0, 2.0, 3.0, 4.0]


def test_robust_score_penalizes_worst_segment():
    # 全均值相同，但后者末段崩掉 → 稳健分必须更低
    steady = [0.01] * 12
    crash = [0.01] * 9 + [-0.20] * 3
    assert robust_score(crash) < robust_score(steady)


def test_robust_score_formula():
    # 4 段均值 [0.1, 0.2, 0.3, 0.4] → 中位 0.25、最差 0.1
    expect = round(0.6 * 0.25 + 0.4 * 0.1, 6)
    assert robust_score([0.1] * 3 + [0.2] * 3 + [0.3] * 3 + [0.4] * 3) == expect


def test_robust_score_insufficient_segments_returns_none():
    assert robust_score([0.1, 0.2]) is None
    assert robust_score([]) is None


def test_annotate_robust_sorts_desc_and_none_last():
    rows = [
        {"params": {"a": 1}, "segment_excess": [0.05] * 8},
        {"params": {"a": 2}, "segment_excess": [0.05] * 6 + [-0.1] * 2},
        {"params": {"a": 3}, "segment_excess": [0.01]},  # 段不足 → None
    ]
    out = annotate_robust(rows)
    assert out[0]["params"]["a"] == 1
    assert out[-1]["params"]["a"] == 3
    assert out[-1]["robust_score"] is None
    assert out[0]["robust_score"] > out[1]["robust_score"]
