"""分钟级（日内）回测服务：5min 信号 → 逐笔模拟 → 逐日复利净值。

批次 3.4。与日线口径（signal_backtest T+1 开→开）互补，回答「信号在
分钟时点上的可实现收益」：

交易语义（A 股约束内建）：
- 信号在 bar t 收盘时点生成，t+1 根 bar 开盘价入场（无前视）；
- **T+1 约束**（respect_t1=True 默认）：当日买入当日不可卖，出场最早
  顺延到次一交易日首根 bar；关闭后为研究口径（允许日内往返）；
- **涨跌停不可成交**：入场 bar 开盘价达到板块涨停幅度的 99.5% → 放弃
  该笔；出场 bar 达到跌停幅度 → 顺延到下一根可成交 bar（数据尾部截断）；
- 止损/止盈（可选）：逐 bar 扫描 low/high 触线即出，同 bar 双触保守判
  止损；T+1 开启时从次日起才扫描。

信号（bar t 时点值，全滚动无前视）：
- ret_30m   近 6 根（30 分钟）动量
- vwap_dev  收盘价相对当日累计 VWAP 乖离
- price_pos 收盘在当日已实现高低区间的位置

选股：每个信号时点（signal_time，缺省全天每根 bar）按信号值取前/后
top_n；净值按入场日等权合成、逐日复利（与 signal_backtest 同纪律）。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from app.services.minute_code_style import normalize_minute_code

_SIGNAL_KINDS = ("ret_30m", "vwap_dev", "price_pos")
#: 全市场分钟面板行数上限（内存保护）
_MAX_PANEL_ROWS = 20_000_000


def limit_ratio_for(ts_code: str) -> float:
    """按代码板块推断涨跌停幅度（与 market_dashboard 同口径）。"""
    code = str(ts_code).split(".")[0]
    if str(ts_code).endswith(".BJ"):
        return 0.30
    if code.startswith(("300", "688", "689")):
        return 0.20
    return 0.10


class IntradayBacktestService:
    def __init__(self, data_dir: str | None = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir

    # ------------------------------------------------------------------
    def run(
        self,
        start_date: str,
        end_date: str,
        signal: str = "ret_30m",
        direction: str = "high",
        top_n: int = 5,
        signal_time: Optional[str] = None,
        horizon_bars: int = 12,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        respect_t1: bool = True,
        initial_capital: float = 1_000_000.0,
        max_trades_returned: int = 200,
    ) -> Dict[str, Any]:
        """回测 [start_date, end_date]（YYYYMMDD）。返回 summary/nav/trades。"""
        if signal not in _SIGNAL_KINDS:
            return {"error": f"不支持的信号: {signal}（可选 {_SIGNAL_KINDS}）"}
        if direction not in ("high", "low"):
            return {"error": f"不支持的方向: {direction}"}
        top_n = max(1, int(top_n))
        horizon_bars = max(1, int(horizon_bars))

        panel = self._load_panel(start_date, end_date)
        if isinstance(panel, dict):
            return panel
        if panel.empty:
            return {"error": "区间内无 5min 数据"}

        panel = self._with_signals(panel, signal)
        selections = self._select_signals(panel, direction, top_n, signal_time)
        if not selections:
            return {"error": "无有效信号候选（检查区间/信号时点）"}

        trades = self._simulate(panel, selections, horizon_bars, stop_loss_pct,
                                take_profit_pct, respect_t1)
        if not trades:
            return {"error": "信号未产生任何可成交交易（涨跌停/T+1 过滤后为空）"}

        trades_df = pd.DataFrame(trades)
        nav, summary = self._summarize(trades_df, initial_capital)
        summary.update({
            "signal": signal,
            "direction": direction,
            "top_n": top_n,
            "signal_time": signal_time,
            "horizon_bars": horizon_bars,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "respect_t1": respect_t1,
            "start_date": start_date,
            "end_date": end_date,
        })
        return {
            "summary": summary,
            "nav": nav,
            "trades": trades_df.head(max_trades_returned).to_dict(orient="records"),
            "trades_total": int(len(trades_df)),
        }

    # ------------------------------------------------------------------
    def _load_panel(self, start_date: str, end_date: str) -> pd.DataFrame | Dict[str, Any]:
        from app.services.minute_parquet_reader import MinuteParquetReader

        start = pd.Timestamp(datetime.strptime(str(start_date), "%Y%m%d"))
        end = pd.Timestamp(datetime.strptime(str(end_date), "%Y%m%d"))
        reader = MinuteParquetReader(data_dir=self.data_dir)
        df = reader.get_data(
            period_type="5min",
            start_time=start.strftime("%Y-%m-%d"),
            end_time=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d 23:59"),
        )
        if df.empty:
            return df
        if len(df) > _MAX_PANEL_ROWS:
            return {"error": f"分钟面板过大（{len(df)} 行 > {_MAX_PANEL_ROWS}），请缩小区间"}
        df = df.copy()
        df["ts_code"] = df["ts_code"].astype(str).map(normalize_minute_code)
        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "close"]).sort_values(["ts_code", "datetime"]).reset_index(drop=True)
        df["date"] = df["datetime"].dt.date
        return df

    @staticmethod
    def _with_signals(panel: pd.DataFrame, signal: str) -> pd.DataFrame:
        df = panel.copy()
        if signal == "ret_30m":
            df["signal_value"] = df.groupby("ts_code")["close"].pct_change(6)
        elif signal == "vwap_dev":
            grp = df.groupby(["ts_code", "date"])
            cum_amount = grp["amount"].cumsum() if "amount" in df.columns else None
            cum_vol = grp["volume"].cumsum() if "volume" in df.columns else None
            if cum_amount is None or cum_vol is None:
                df["signal_value"] = np.nan
            else:
                cum_vol = cum_vol.replace(0, np.nan)
                df["signal_value"] = df["close"] / (cum_amount / cum_vol) - 1
        else:  # price_pos
            grp = df.groupby(["ts_code", "date"])
            day_high = grp["high"].cummax()
            day_low = grp["low"].cummin()
            span = (day_high - day_low).replace(0, np.nan)
            df["signal_value"] = (df["close"] - day_low) / span
        return df

    @staticmethod
    def _select_signals(panel: pd.DataFrame, direction: str, top_n: int,
                        signal_time: Optional[str]) -> List[Dict[str, Any]]:
        df = panel[panel["signal_value"].notna()]
        if signal_time:
            times = df["datetime"].dt.strftime("%H:%M")
            df = df[times == signal_time]
        if df.empty:
            return []

        selections: List[Dict[str, Any]] = []
        # 每根 bar 一个截面：同 (date, time) 内排序取前/后 top_n
        for (date, time), group in df.groupby([df["date"], df["datetime"].dt.strftime("%H:%M")],
                                              sort=True):
            ranked = group.sort_values("signal_value", ascending=(direction == "low"))
            for _, row in ranked.head(top_n).iterrows():
                selections.append({
                    "ts_code": row["ts_code"],
                    "signal_time": row["datetime"],
                    "signal_value": float(row["signal_value"]),
                })
        return selections

    # ------------------------------------------------------------------
    def _simulate(self, panel: pd.DataFrame, selections: List[Dict[str, Any]],
                  horizon_bars: int, stop_loss_pct: Optional[float],
                  take_profit_pct: Optional[float], respect_t1: bool) -> List[Dict[str, Any]]:
        """逐笔模拟。panel 已按 (ts_code, datetime) 排序。"""
        bar_index: Dict[str, pd.DataFrame] = {
            code: g.reset_index(drop=True) for code, g in panel.groupby("ts_code", sort=False)
        }
        trades: List[Dict[str, Any]] = []
        for sel in selections:
            frame = bar_index.get(sel["ts_code"])
            if frame is None:
                continue
            entry_pos = frame.index[frame["datetime"] > sel["signal_time"]]
            if len(entry_pos) == 0:
                continue
            pos = int(entry_pos[0])  # 下一根 bar
            entry_row = frame.iloc[pos]
            prev_close = frame.iloc[pos - 1]["close"] if pos > 0 else entry_row.get("pre_close")
            if pd.isna(prev_close) or prev_close <= 0:
                continue
            ratio = limit_ratio_for(sel["ts_code"])
            # 涨停不可买入（开盘价触板即放弃）
            if entry_row["open"] / prev_close - 1 >= ratio * 0.995:
                continue

            entry_price = float(entry_row["open"])
            entry_date = entry_row["date"]
            exit_info = self._find_exit(
                frame, pos, horizon_bars, entry_price, entry_date,
                stop_loss_pct, take_profit_pct, respect_t1, ratio,
            )
            if exit_info is None:
                continue
            exit_pos, exit_price, exit_reason = exit_info
            exit_row = frame.iloc[exit_pos]
            trades.append({
                "ts_code": sel["ts_code"],
                "signal_time": sel["signal_time"],
                "signal_value": sel["signal_value"],
                "entry_time": entry_row["datetime"],
                "entry_date": entry_date.isoformat(),
                "entry_price": entry_price,
                "exit_time": exit_row["datetime"],
                "exit_price": float(exit_price),
                "ret": float(exit_price) / entry_price - 1,
                "exit_reason": exit_reason,
                "holding_bars": int(exit_pos - pos),
            })
        return trades

    @staticmethod
    def _find_exit(frame: pd.DataFrame, entry_pos: int, horizon_bars: int,
                   entry_price: float, entry_date,
                   stop_loss_pct: Optional[float], take_profit_pct: Optional[float],
                   respect_t1: bool, ratio: float) -> Optional[tuple]:
        """定位出场 bar：返回 (pos, price, reason) 或 None（数据尾部）。"""
        n = len(frame)
        stop_price = entry_price * (1 - stop_loss_pct / 100.0) if stop_loss_pct else None
        target_price = entry_price * (1 + take_profit_pct / 100.0) if take_profit_pct else None

        earliest = entry_pos + 1
        if respect_t1:
            # T+1：当日买入最早次日首根可卖
            while earliest < n and frame.iloc[earliest]["date"] == entry_date:
                earliest += 1
        if earliest >= n:
            return None

        horizon_pos = min(entry_pos + horizon_bars, n - 1)
        pos = earliest
        while pos <= horizon_pos:
            row = frame.iloc[pos]
            # 跌停不可卖出：顺延（收盘/前收 -1 触板近似）；entry bar 前一根本身存在
            prev_close = frame.iloc[pos - 1]["close"]
            if prev_close > 0 and row["close"] / prev_close - 1 <= -ratio * 0.995:
                pos += 1
                continue
            if stop_price is not None and row["low"] <= stop_price:
                return pos, stop_price, "stop_loss"
            if target_price is not None and row["high"] >= target_price:
                return pos, target_price, "take_profit"
            pos += 1
            if pos > horizon_pos:
                break
        exit_pos = min(pos, n - 1)
        return exit_pos, frame.iloc[exit_pos]["close"], "horizon"

    # ------------------------------------------------------------------
    @staticmethod
    def _summarize(trades: pd.DataFrame, initial_capital: float) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """按入场日等权合成、逐日复利。返回 (nav 序列, 汇总指标)。"""
        daily = trades.groupby("entry_date")["ret"].mean()
        nav_values = (1.0 + daily).cumprod()
        nav = [{"date": d, "nav": round(float(v), 6)} for d, v in nav_values.items()]

        running_max = nav_values.cummax()
        drawdown = nav_values / running_max - 1.0
        total_days = len(daily)
        total_ret = float(nav_values.iloc[-1] - 1) if total_days else 0.0
        summary = {
            "trades": int(len(trades)),
            "win_rate": round(float((trades["ret"] > 0).mean()) * 100, 2),
            "avg_ret_pct": round(float(trades["ret"].mean()) * 100, 4),
            "total_ret_pct": round(total_ret * 100, 4),
            "max_drawdown_pct": round(float(drawdown.min()) * 100, 4) if total_days else 0.0,
            "days": total_days,
            "final_nav": round(float(nav_values.iloc[-1]), 6) if total_days else 1.0,
            "exit_reasons": {k: int(v) for k, v in trades["exit_reason"].value_counts().items()},
        }
        return nav, summary
