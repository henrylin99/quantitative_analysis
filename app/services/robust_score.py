"""K 段稳健分（反过拟合排名口径，借鉴开源 robust_optimizer 实现）。

全样本/样本内单一数字天然偏乐观——一段大行情可以掩盖其余段全部失效。
稳健分把评估序列切成 K 段，按

    robust = 0.6 × 中位段得分 + 0.4 × 最差段得分

合成：既要求"多数段有效"（中位），又惩罚"存在失效段"（最差）。
段数不足 min_segments 时不给分（None），避免两段样本假装稳健。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

W_MEDIAN = 0.6
W_WORST = 0.4
MIN_SEGMENTS = 3


def split_segments(values: Sequence[float], n_segments: int = 4) -> List[List[float]]:
    """把有序得分序列切成 n_segments 个连续段（不均分时前面的段多分）。

    顺序保留：段对应时间上的先后（行情 regime 段），打乱会丢掉时间结构。
    """
    def _bad(v: Any) -> bool:
        if v is None:
            return True
        try:
            return not np.isfinite(float(v))
        except (TypeError, ValueError):
            return False  # 非数值（如锚点日期）原样保留，切分不针对数值过滤

    values = [v for v in values if not _bad(v)]
    n = len(values)
    if n == 0 or n_segments <= 0:
        return []
    n_segments = min(n_segments, n)
    base, extra = divmod(n, n_segments)
    segments: List[List[float]] = []
    start = 0
    for i in range(n_segments):
        size = base + (1 if i < extra else 0)
        if size == 0:
            continue
        segments.append(values[start:start + size])
        start += size
    return segments


def robust_score(scores: Sequence[Optional[float]],
                 n_segments: int = 4,
                 w_median: float = W_MEDIAN,
                 w_worst: float = W_WORST,
                 min_segments: int = MIN_SEGMENTS,
                 agg: str = "mean") -> Optional[float]:
    """按时间顺序切 K 段 → 每段聚合得分 → 0.6×中位 + 0.4×最差。

    agg=mean：段内逐点平均（窗口收益类，每点量级可比）；
    agg=sum ：段内求和（对数超额/日超额类，段内点数一致时等价于 mean×n）。
    有效段数 < min_segments 时返回 None。
    """
    segments = split_segments(list(scores), n_segments)  # type: ignore[arg-type]
    if len(segments) < min_segments:
        return None
    seg_vals = []
    for seg in segments:
        seg_vals.append(float(np.mean(seg)) if agg == "mean" else float(np.sum(seg)))
    median_v = float(np.median(seg_vals))
    worst_v = float(np.min(seg_vals))
    score = w_median * median_v + w_worst * worst_v
    return round(float(score), 6)


def annotate_robust(rows: List[Dict[str, Any]],
                    segment_values_key: str = "segment_excess",
                    n_segments: int = 4) -> List[Dict[str, Any]]:
    """给已带分段得分列表的网格行打稳健分并按其降序返回副本。

    输入行形如 {"params": {...}, "segment_excess": [e1, e2, ...], ...}；
    输出每行追加 "robust_score"（可为 None），None 垫底。
    """
    annotated = []
    for row in rows:
        segs = row.get(segment_values_key) or []
        annotated.append({**row, "robust_score": robust_score(segs, n_segments=n_segments)})
    annotated.sort(key=lambda r: (r["robust_score"] is None,
                                  -(r["robust_score"] if r["robust_score"] is not None else 0.0)))
    return annotated
