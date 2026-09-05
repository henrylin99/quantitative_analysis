"""市场看板聚合：从统一列的行情帧计算市场宽度、涨跌分布与榜单。

输入帧契约（由 market_snapshot_service._build_dashboard 统一）：
    ts_code / name / price / pct_chg / prev_close / amount_yuan

涨跌停为近似口径：按代码板块推断涨跌停幅度（北交所 30%、创/科 20%、
其余 10%），不含 ST 5% 特例，仅用于市场宽度展示。
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

DASHBOARD_TOP_N = 10

DISTRIBUTION_BUCKETS = (
    ("< -5%", None, -5.0),
    ("-5% ~ -2%", -5.0, -2.0),
    ("-2% ~ 0", -2.0, 0.0),
    ("0 ~ 2%", 0.0, 2.0),
    ("2% ~ 5%", 2.0, 5.0),
    (">= 5%", 5.0, None),
)


def limit_ratio_for(ts_code: str) -> float:
    """按代码板块推断涨跌停幅度（近似口径，见模块 docstring）。"""
    code = str(ts_code).split(".")[0]
    if str(ts_code).endswith(".BJ"):
        return 0.30
    if code.startswith(("300", "688", "689")):
        return 0.20
    return 0.10


def _board_row(row: "pd.Series") -> Dict[str, Any]:
    return {
        "ts_code": row["ts_code"],
        "name": row.get("name"),
        "price": None if pd.isna(row["price"]) else round(float(row["price"]), 3),
        "pct_chg": None if pd.isna(row["pct_chg"]) else round(float(row["pct_chg"]), 3),
        "amount_yuan": None if pd.isna(row["amount_yuan"]) else float(row["amount_yuan"]),
    }


def build_dashboard_payload(frame: pd.DataFrame) -> Dict[str, Any]:
    """聚合市场看板数据（不含 source/degraded 等调用方附加字段）。"""
    empty_boards = {"top_gainers": [], "top_losers": [], "top_amount": []}
    if frame is None or frame.empty:
        return {
            "breadth": {}, "distribution": [], "total_amount_yuan": 0.0,
            **empty_boards,
        }

    pct = pd.to_numeric(frame["pct_chg"], errors="coerce")
    valid = pct.dropna()

    up = int((valid > 0).sum())
    down = int((valid < 0).sum())
    flat = int((valid == 0).sum())

    # 涨跌停近似统计：price/prev_close 达到板块涨跌停幅度的 99.5% 视为触板
    limit_up = 0
    limit_down = 0
    ratio_frame = frame
    if {"price", "prev_close"}.issubset(ratio_frame.columns):
        prev = pd.to_numeric(ratio_frame["prev_close"], errors="coerce")
        price = pd.to_numeric(ratio_frame["price"], errors="coerce")
        ratios = ratio_frame["ts_code"].map(limit_ratio_for).astype(float)
        with_rel = prev > 0
        change_ratio = (price / prev - 1.0).where(with_rel)
        limit_up = int((change_ratio >= ratios * 0.995).sum())
        limit_down = int((change_ratio <= -ratios * 0.995).sum())

    distribution = []
    for label, low, high in DISTRIBUTION_BUCKETS:
        if low is None:
            count = int((valid < high).sum())
        elif high is None:
            count = int((valid >= low).sum())
        else:
            count = int(((valid >= low) & (valid < high)).sum())
        distribution.append({"bucket": label, "count": count})

    ranked = frame.assign(_pct=pct)
    top_gainers = [
        _board_row(row)
        for row in ranked.nlargest(DASHBOARD_TOP_N, "_pct").to_dict("records")
        if row["_pct"] == row["_pct"]
    ]
    top_losers = [
        _board_row(row)
        for row in ranked.nsmallest(DASHBOARD_TOP_N, "_pct").to_dict("records")
        if row["_pct"] == row["_pct"]
    ]
    amount = pd.to_numeric(frame["amount_yuan"], errors="coerce")
    top_amount = [
        _board_row(row)
        for row in frame.assign(_amt=amount).nlargest(DASHBOARD_TOP_N, "_amt").to_dict("records")
        if row["_amt"] == row["_amt"]
    ]

    return {
        "breadth": {
            "up": up,
            "down": down,
            "flat": flat,
            "limit_up": limit_up,
            "limit_down": limit_down,
            "total": int(valid.shape[0]),
        },
        "distribution": distribution,
        "total_amount_yuan": float(amount.dropna().sum()),
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "top_amount": top_amount,
    }
