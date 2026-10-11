"""盘中（日内）因子库：从 5min 分钟线计算 ~10 个日内因子，走既有因子管线。

批次 3.3。因子定义（全部以单只股票单交易日的 5min bar 序列为输入，
bar 语义与存储一致：首根 09:35 覆盖 09:30-09:35，末根 15:00）：

- vwap_dev            收盘价相对当日 VWAP 乖离：close / vwap - 1
- open_mom_30         开盘 30min 动量：10:00 收盘 / 首根 open - 1
- tail_ret_30         尾盘 30min 收益：15:00 收盘 / 14:35 open - 1
- intraday_mom        日内动量：收盘 / 首根 open - 1
- morning_reversal    早盘反转：-(上午收盘 / 首根 open - 1)
- vol_concentration_pm 午后量能占比：13:00 后成交量 / 全天成交量
- amount_cv           量能波动：5min amount 变异系数 std/mean
- close_pos_intraday  收盘日内位置：(close-low)/(high-low)
- gap_strength        跳空强度：(首根 open - 首根 pre_close) / pre_close
- min5_vol_std        已实现分钟波动：5min pct_chg 标准差

验收约定与内置日频因子一致：样本不足（bars < 12 或关键窗口缺失）→ 该股
当日无值；除零（high==low、全天零成交等）→ 缺失不造假 0。

落库走 FactorEngine 既有路径（_calculate_factor_stats 截面标准化 +
save_factor_values），落地后 IC 分析/分位回测/因子体检直接可消费。
"""

from __future__ import annotations

import os
from typing import Dict, List

import numpy as np
import pandas as pd
from loguru import logger

#: 有效 bar 数下限：低于此视为停牌/数据不完整，跳过该股当日
_MIN_BARS = 12
#: 开盘 30min 窗口右端（含）
_MORNING30_END = "10:00"
#: 尾盘 30min 窗口左端（含）
_TAIL30_START = "14:35"
#: 午后起点
_PM_START = "13:00"

INTRADAY_FACTOR_IDS = (
    "vwap_dev",
    "open_mom_30",
    "tail_ret_30",
    "intraday_mom",
    "morning_reversal",
    "vol_concentration_pm",
    "amount_cv",
    "close_pos_intraday",
    "gap_strength",
    "min5_vol_std",
)


def _bar_time(df: pd.DataFrame) -> pd.Series:
    return df["datetime"].dt.strftime("%H:%M")


def compute_intraday_factors(day_df: pd.DataFrame) -> pd.DataFrame:
    """单日 5min 全市场截面 → 长表 [ts_code, factor_id, factor_value]。

    day_df 需含 ts_code/datetime/open/high/low/close/volume/amount（pre_close
    可选，缺省时 gap_strength 全部缺失）。
    """
    if day_df is None or day_df.empty:
        return pd.DataFrame(columns=["ts_code", "factor_id", "factor_value"])

    df = day_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df = df.dropna(subset=["datetime", "ts_code"])
    if df.empty:
        return pd.DataFrame(columns=["ts_code", "factor_id", "factor_value"])
    df["time"] = _bar_time(df)
    for col in ("open", "high", "low", "close", "volume", "amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    rows: List[Dict[str, object]] = []
    for ts_code, group in df.groupby("ts_code", sort=False):
        g = group.sort_values("datetime")
        if len(g) < _MIN_BARS:
            continue
        first = g.iloc[0]
        last = g.iloc[-1]
        values: Dict[str, object] = {}

        # VWAP 乖离（全天零成交 → 缺失）
        total_amount, total_volume = g["amount"].sum(), g["volume"].sum()
        if pd.notna(total_amount) and pd.notna(total_volume) and total_volume > 0:
            values["vwap_dev"] = last["close"] / (total_amount / total_volume) - 1

        # 开盘 30min 动量
        head = g[g["time"] <= _MORNING30_END]
        if not head.empty and pd.notna(head.iloc[0]["open"]) and head.iloc[0]["open"] > 0:
            values["open_mom_30"] = head.iloc[-1]["close"] / head.iloc[0]["open"] - 1

        # 尾盘 30min 收益
        tail = g[g["time"] >= _TAIL30_START]
        if not tail.empty and pd.notna(tail.iloc[0]["open"]) and tail.iloc[0]["open"] > 0:
            values["tail_ret_30"] = tail.iloc[-1]["close"] / tail.iloc[0]["open"] - 1

        # 日内动量 / 早盘反转
        if pd.notna(first["open"]) and first["open"] > 0:
            values["intraday_mom"] = last["close"] / first["open"] - 1
            morning = g[g["time"] <= "11:30"]
            if not morning.empty:
                values["morning_reversal"] = -(morning.iloc[-1]["close"] / first["open"] - 1)

        # 午后量能占比
        if total_volume and total_volume > 0:
            pm_volume = g.loc[g["time"] >= _PM_START, "volume"].sum()
            values["vol_concentration_pm"] = pm_volume / total_volume

        # 量能波动（变异系数）
        amounts = g["amount"].dropna()
        if len(amounts) >= 2 and amounts.mean() > 0:
            values["amount_cv"] = amounts.std(ddof=1) / amounts.mean()

        # 收盘日内位置（high==low 一字板 → 缺失）
        day_high, day_low = g["high"].max(), g["low"].min()
        if pd.notna(day_high) and pd.notna(day_low) and day_high > day_low:
            values["close_pos_intraday"] = (last["close"] - day_low) / (day_high - day_low)

        # 跳空强度（首根 pre_close = 前日收盘）
        if "pre_close" in g.columns and pd.notna(first.get("pre_close")) and first.get("pre_close") > 0:
            values["gap_strength"] = (first["open"] - first["pre_close"]) / first["pre_close"]

        # 已实现分钟波动
        if "pct_chg" in g.columns:
            rets = pd.to_numeric(g["pct_chg"], errors="coerce").dropna()
            if len(rets) >= 2:
                values["min5_vol_std"] = rets.std(ddof=1)

        for factor_id, value in values.items():
            if value is None or (isinstance(value, float) and not np.isfinite(value)):
                continue
            rows.append({"ts_code": ts_code, "factor_id": factor_id, "factor_value": float(value)})

    return pd.DataFrame(rows, columns=["ts_code", "factor_id", "factor_value"])


class IntradayFactorService:
    """日内因子计算与落库（复用 FactorEngine 标准化与存储）。"""

    def __init__(self, data_dir: str | None = None, engine=None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir
        self._engine = engine
        self._minute_reader = None

    @property
    def engine(self):
        if self._engine is None:
            from app.services.factor_engine import FactorEngine

            self._engine = FactorEngine()
        return self._engine

    @property
    def minute_reader(self):
        if self._minute_reader is None:
            from app.services.minute_parquet_reader import MinuteParquetReader

            self._minute_reader = MinuteParquetReader(data_dir=self.data_dir)
        return self._minute_reader

    def compute_for_date(self, trade_date: str) -> pd.DataFrame:
        """计算某交易日的全部日内因子长表（未标准化）。"""
        from app.services.minute_code_style import normalize_minute_code

        day_str = datetime_of(trade_date)
        # 行级时间过滤是闭区间：end 传当日末尾，否则当日 bar 全被滤掉
        day_df = self.minute_reader.get_data(
            period_type="5min", start_time=f"{day_str} 00:00", end_time=f"{day_str} 23:59"
        )
        if day_df.empty:
            logger.info(f"日内因子：{trade_date} 无 5min 数据，跳过")
            return pd.DataFrame(columns=["ts_code", "factor_id", "factor_value"])
        # 存量分区可能是迁移前旧风格，计算前归一
        day_df = day_df.copy()
        day_df["ts_code"] = day_df["ts_code"].astype(str).map(normalize_minute_code)
        long_df = compute_intraday_factors(day_df)
        if not long_df.empty:
            long_df["trade_date"] = pd.to_datetime(day_str)
        logger.info(
            f"日内因子 {day_str}：{len(long_df)} 行（"
            f"{long_df['ts_code'].nunique() if not long_df.empty else 0} 只 × "
            f"{long_df['factor_id'].nunique() if not long_df.empty else 0} 因子）"
        )
        return long_df

    def compute_and_save(self, trade_date: str) -> Dict[str, object]:
        """计算 + 截面标准化 + 落库。返回摘要 dict。"""
        long_df = self.compute_for_date(trade_date)
        if long_df.empty:
            return {"success": False, "message": f"{trade_date} 无 5min 数据或无有效因子值", "rows": 0}

        stats = self.engine._calculate_factor_stats(long_df, trade_date)
        ok = self.engine.save_factor_values(stats, replace_factor_ids=list(INTRADAY_FACTOR_IDS))
        if not ok:
            return {"success": False, "message": f"{trade_date} 落库失败", "rows": len(stats)}
        return {
            "success": True,
            "message": f"{trade_date} 日内因子落库 {len(stats)} 行",
            "rows": int(len(stats)),
            "stocks": int(stats["ts_code"].nunique()),
            "factors": int(stats["factor_id"].nunique()),
        }


def datetime_of(trade_date: str) -> str:
    """YYYYMMDD → YYYY-MM-DD（兼容两种入参）。"""
    text = str(trade_date).replace("-", "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
