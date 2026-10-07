"""筹码信号扫描服务：基于筹码分布（cyq_perf）与资金流的截面信号。

三类信号（全部为事前截面规则，无前视）：

- squeeze 筹码挤压蓄势：获利盘过半、90% 筹码区间高度集中、量能收缩——
  上方虽有获利压力但筹码沉淀，常见于吸筹/蓄势阶段。
- resonance 资金×筹码多头共振：主力资金连续净流入，且获利盘从低位抬升
  但未到拥挤区——量价筹码同向。
- divergence 量价资金背离预警：股价上行但主力净流出、获利盘高位——
  兑现压力大的顶部预警。

数据口径：cyq 成本与 get_daily 收盘价同为未复权口径，可直接比较。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from app.services.data_reader import ParquetDataReader
from app.services.signal_defs import (
    DEFAULT_THRESHOLDS,
    SignalThresholds,
    divergence_mask,
    resonance_mask,
    signal_definitions,
    squeeze_mask,
)
from app.services.stock_name_registry import get_stock_name_registry

_MAX_ROWS_PER_SIGNAL = 50
_CACHE_TTL_SECONDS = 300.0


class ChipSignalService:
    def __init__(self, data_reader: Optional[ParquetDataReader] = None):
        self.data_reader = data_reader or ParquetDataReader()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_key: Optional[tuple] = None
        self._cache_at: float = 0.0

    # ------------------------------------------------------------------
    def scan(self, force_refresh: bool = False,
             thresholds: SignalThresholds = DEFAULT_THRESHOLDS) -> Dict[str, Any]:
        """全市场扫描最近一个筹码交易日截面，返回三类信号。"""
        import time

        cache_key = thresholds.signature()
        if not force_refresh and self._cache is not None \
                and self._cache_key == cache_key \
                and time.monotonic() - self._cache_at < _CACHE_TTL_SECONDS:
            return self._cache

        end_date = datetime.now().strftime("%Y-%m-%d")
        window_start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

        try:
            cyq = self.data_reader.get_cyq_perf(ts_codes=None, start_date=window_start,
                                                end_date=end_date)
        except Exception as e:
            logger.error(f"筹码信号扫描读取 cyq 失败: {e}")
            return {"error": f"读取筹码数据失败: {e}"}
        if cyq.empty:
            return {"error": "筹码数据为空"}

        cyq["trade_date"] = pd.to_datetime(cyq["trade_date"])
        scan_date = cyq["trade_date"].max()
        # 截面基准：最近 30 个自然日内有筹码数据的天数足够算 5 日变化
        cyq = cyq[cyq["trade_date"] >= scan_date - timedelta(days=25)]

        try:
            daily = self.data_reader.get_daily(ts_codes=None, start_date=window_start,
                                               end_date=end_date)
            flow = self.data_reader.get_moneyflow(ts_codes=None, start_date=window_start,
                                                  end_date=end_date)
        except Exception as e:
            logger.error(f"筹码信号扫描读取行情/资金流失败: {e}")
            return {"error": f"读取行情数据失败: {e}"}

        result = self._build_signals(cyq, daily, flow, scan_date, thresholds)
        if "error" not in result:
            self._cache = result
            self._cache_key = cache_key
            self._cache_at = time.monotonic()
        return result

    # ------------------------------------------------------------------
    def _build_signals(self, cyq: pd.DataFrame, daily: pd.DataFrame,
                       flow: pd.DataFrame, scan_date,
                       t: SignalThresholds) -> Dict[str, Any]:
        # 逐票最新筹码截面 + 5 日前获利盘
        cyq = cyq.sort_values(["ts_code", "trade_date"])
        latest = cyq[cyq["trade_date"] == scan_date].set_index("ts_code")
        if latest.empty:
            return {"error": "最近交易日无筹码截面"}

        def _winner_days_ago(days: int) -> pd.Series:
            rows = {}
            for code, grp in cyq.groupby("ts_code", sort=False):
                past = grp[grp["trade_date"] <= scan_date - timedelta(days=days - 1)]
                if not past.empty:
                    rows[code] = float(past.iloc[-1]["winner_rate"])
            return pd.Series(rows)

        winner_5d_ago = _winner_days_ago(5)

        latest = latest.assign(
            conc=(latest["cost_95pct"] - latest["cost_5pct"]) / latest["cost_50pct"],
        )
        latest = latest.replace([np.inf, -np.inf], np.nan)
        conc_thresh = float(latest["conc"].quantile(t.squeeze_conc_quantile))

        # 行情：5 日涨跌幅 + 量能收缩（逐票滚动均值后取每股末行，索引统一为 ts_code）
        daily = daily.copy()
        daily["trade_date"] = pd.to_datetime(daily["trade_date"])
        daily = daily[daily["trade_date"] <= scan_date].sort_values(["ts_code", "trade_date"])
        daily["vol_ma5"] = daily.groupby("ts_code")["vol"].transform(
            lambda s: s.rolling(5).mean())
        daily["vol_ma20"] = daily.groupby("ts_code")["vol"].transform(
            lambda s: s.rolling(20).mean())
        tail6 = daily.groupby("ts_code").tail(6)
        agg = tail6.groupby("ts_code").agg(
            close_last=("close", "last"),
            close_5ago=("close", "first"),
            vol_ma5=("vol_ma5", "last"),
            vol_ma20=("vol_ma20", "last"),
        )
        last_close = agg["close_last"]
        pct5 = agg["close_last"] / agg["close_5ago"] - 1
        vol_ratio = agg["vol_ma5"] / agg["vol_ma20"]

        # 资金：近 5 日主力净额合计 + 最新一日
        flow = flow.copy()
        flow["trade_date"] = pd.to_datetime(flow["trade_date"])
        flow = flow[flow["trade_date"] <= scan_date]
        flow["main_net"] = (flow["buy_lg_amount"] + flow["buy_elg_amount"]
                            - flow["sell_lg_amount"] - flow["sell_elg_amount"])
        net5 = flow[flow["trade_date"] >= scan_date - timedelta(days=6)] \
            .groupby("ts_code")["main_net"].sum()
        net_last = flow.groupby("ts_code")["main_net"].last()

        panel = pd.DataFrame({
            "close": last_close,
            "pct_5d": pct5,
            "vol_ratio": vol_ratio,
            "winner_rate": latest["winner_rate"],
            "conc": latest["conc"],
            "weight_avg": latest["weight_avg"],
            "cost_dev": last_close / latest["weight_avg"] - 1,
            "winner_chg_5d": latest["winner_rate"] - winner_5d_ago,
            "main_net_5d": net5,
            "main_net_last": net_last,
        }).dropna(subset=["close", "winner_rate", "conc"])

        if panel.empty:
            return {"error": "有效截面为空"}

        squeeze_m = squeeze_mask(panel["winner_rate"], panel["conc"], conc_thresh,
                                 panel["vol_ratio"], panel["pct_5d"], t)
        resonance_m = resonance_mask(panel["main_net_5d"], panel["main_net_last"],
                                     panel["winner_chg_5d"], panel["winner_rate"],
                                     panel["pct_5d"], t)
        divergence_m = divergence_mask(panel["pct_5d"], panel["main_net_5d"],
                                       panel["winner_rate"], t)

        stats = {
            "scan_date": scan_date.strftime("%Y-%m-%d"),
            "universe": int(len(panel)),
            "conc_threshold": round(conc_thresh, 4),
            "counts": {
                "squeeze": int(squeeze_m.sum()),
                "resonance": int(resonance_m.sum()),
                "divergence": int(divergence_m.sum()),
            },
        }

        def _rows(mask: pd.Series) -> List[Dict[str, Any]]:
            sub = panel[mask].copy()
            if sub.empty:
                return []
            return [
                {
                    "ts_code": code,
                    "close": round(float(r["close"]), 2),
                    "pct_5d": round(float(r["pct_5d"]) * 100, 2) if pd.notna(r["pct_5d"]) else None,
                    "winner_rate": round(float(r["winner_rate"]), 2),
                    "winner_chg_5d": round(float(r["winner_chg_5d"]), 2) if pd.notna(r["winner_chg_5d"]) else None,
                    "conc": round(float(r["conc"]), 4),
                    "cost_dev": round(float(r["cost_dev"]) * 100, 2) if pd.notna(r["cost_dev"]) else None,
                    "main_net_5d": round(float(r["main_net_5d"]), 0) if pd.notna(r["main_net_5d"]) else None,
                    "vol_ratio": round(float(r["vol_ratio"]), 3) if pd.notna(r["vol_ratio"]) else None,
                }
                for code, r in sub.iterrows()
            ]

        result = {
            "stats": stats,
            "definitions": signal_definitions(t, conc_thresh),
            "squeeze": _rows(squeeze_m)[:_MAX_ROWS_PER_SIGNAL],
            "resonance": _rows(resonance_m)[:_MAX_ROWS_PER_SIGNAL],
            "divergence": _rows(divergence_m)[:_MAX_ROWS_PER_SIGNAL],
        }
        for key in ("squeeze", "resonance", "divergence"):
            try:
                get_stock_name_registry().merge_names(result[key])
            except Exception:
                pass
        return result
