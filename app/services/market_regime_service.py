"""指数市场状态（regime）服务：动量 + 均线 + 波动率的状态标注。

供组合回测/选股页做仓位调节对照：当前回测引擎是恒仓运行，
regime 状态提示市场环境（多头/震荡/空头），辅助解读回测结果与
实际执行的仓位差异。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from app.services.data_reader import ParquetDataReader

DEFAULT_INDEXES: List[List[str]] = [
    # 沪深300 本地库存为 399300.SZ（与回测基准降级候选一致）
    ["399300.SZ", "沪深300"],
    ["000905.SH", "中证500"],
    ["000852.SH", "中证1000"],
    ["399006.SZ", "创业板指"],
]


def classify_regime(ret_20d: float, ma20: float, ma60: float, close: float) -> str:
    """动量 + 均线多空排列 → 多头 / 空头 / 震荡。"""
    if any(v is None or (isinstance(v, float) and not np.isfinite(v))
           for v in (ret_20d, ma20, ma60, close)):
        return "未知"
    if ma20 > ma60 and ret_20d > 0:
        return "多头"
    if ma20 < ma60 and ret_20d < 0:
        return "空头"
    return "震荡"


class MarketRegimeService:
    def __init__(self, data_reader: Optional[ParquetDataReader] = None):
        self.data_reader = data_reader or ParquetDataReader()

    def regime(self, codes: Optional[List[List[str]]] = None,
               lookback_days: int = 160) -> Dict[str, Any]:
        """返回各指数的动量/波动/均线状态。codes 为 [code, name] 列表。"""
        pairs = codes or DEFAULT_INDEXES
        end = datetime.now()
        start = end - timedelta(days=lookback_days * 2)

        indexes: List[Dict[str, Any]] = []
        for code, name in pairs:
            try:
                df = self.data_reader.get_index_daily(
                    [code], start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            except Exception as e:
                logger.warning(f"读取指数日线失败 {code}: {e}")
                df = pd.DataFrame()
            if df.empty or "close" not in df.columns:
                continue
            df = df.sort_values("trade_date").tail(lookback_days).reset_index(drop=True)
            close = df["close"].astype(float)
            if len(close) < 25:
                continue
            ma20 = float(close.tail(20).mean())
            ma60 = float(close.tail(min(60, len(close))).mean())
            ret_20d = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) >= 21 else None
            ret_60d = float(close.iloc[-1] / close.iloc[-61] - 1) if len(close) >= 61 else None
            daily_ret = close.pct_change().dropna().tail(20)
            vol_20d = float(daily_ret.std() * np.sqrt(252)) if len(daily_ret) >= 10 else None

            indexes.append({
                "code": code,
                "name": name,
                "close": round(float(close.iloc[-1]), 2),
                "trade_date": pd.to_datetime(df["trade_date"].iloc[-1]).strftime("%Y-%m-%d"),
                "ret_20d": round(ret_20d * 100, 2) if ret_20d is not None else None,
                "ret_60d": round(ret_60d * 100, 2) if ret_60d is not None else None,
                "vol_20d_ann": round(vol_20d * 100, 2) if vol_20d is not None else None,
                "ma20": round(ma20, 2),
                "ma60": round(ma60, 2),
                "regime": classify_regime(ret_20d, ma20, ma60, float(close.iloc[-1])),
                # 近 60 日净值化收盘（供前端 sparkline）
                "series": [
                    {
                        "date": pd.to_datetime(d).strftime("%Y-%m-%d"),
                        "close": round(float(c) / float(close.iloc[0]), 4),
                    }
                    for d, c in zip(df["trade_date"].tail(60), close.tail(60))
                ],
            })

        if not indexes:
            return {"error": "指数日线数据为空"}
        return {"indexes": indexes, "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
