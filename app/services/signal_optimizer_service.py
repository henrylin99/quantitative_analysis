"""信号参数寻优（5.3）：筹码信号阈值 + 行业轮动权重，网格 + walk-forward OOS。

两类寻优共用同一纪律：
- 全样本网格 = 参数敏感度参考（天然偏乐观）；
- walk-forward = IS 窗网格选参 → 紧随 OOS 窗验证，OOS 不重叠、链式承接；
- apply=True 把最优参数写回单一源（signal_defs 的 JSON 覆盖 / 轮动权重 JSON），
  写回后扫描与回测服务读到的是同一份参数——"一处定义、两处消费"。

评估口径与 ChipSignalBacktestService / IndustryRotationService 一致（T+1 开盘、
非重叠锚点、超额 vs universe/全行业等权），无前视。
"""

from __future__ import annotations

from dataclasses import replace
from itertools import product
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from app.services.data_reader import ParquetDataReader
from app.services.robust_score import annotate_robust, robust_score, split_segments
from app.services.signal_defs import (
    SignalThresholds,
    current_thresholds,
    save_threshold_override,
)

_MAX_COMBOS = 48

# 筹码阈值默认网格（字段名即 SignalThresholds 字段）
DEFAULT_CHIP_GRID: Dict[str, List[float]] = {
    "squeeze_winner_min": [50.0, 60.0, 70.0],
    "squeeze_volume_ratio_max": [0.80, 0.85, 0.90],
    "resonance_winner_lo": [20.0, 30.0, 40.0],
    "divergence_winner_min": [60.0, 70.0, 80.0],
}

# 轮动评分权重默认网格：score = w_mom·z(动量20) + w_flow·(z(资金5)+z(资金20))
#                            + w_val·(−z(PE截面分位))
DEFAULT_ROTATION_GRID: Dict[str, List[float]] = {
    "w_mom": [0.5, 1.0, 1.5],
    "w_flow": [0.0, 0.5, 1.0],
    "w_val": [0.0, 0.5, 1.0],
}

_DEFAULT_ROTATION_WEIGHTS = {"w_mom": 1.0, "w_flow": 1.0, "w_val": 1.0}


def _expand_grid(grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    keys = sorted(grid)
    combos = [dict(zip(keys, values))
              for values in product(*(grid[k] for k in keys))]
    return combos[:_MAX_COMBOS]


class SignalOptimizerService:
    def __init__(self, data_reader: Optional[ParquetDataReader] = None):
        self.data_reader = data_reader or ParquetDataReader()

    # ==================================================================
    # 一、筹码信号阈值寻优
    # ==================================================================
    def chip_threshold_optimize(self, months: int = 12, signal: str = "resonance",
                                horizon: int = 10,
                                grid: Optional[Dict[str, List[float]]] = None,
                                is_days: int = 120, oos_days: int = 60,
                                apply: bool = False) -> Dict[str, Any]:
        """单信号阈值网格 + walk-forward OOS。

        评估指标 = H 日非重叠锚点的链式超额收益（信号组净值 / universe 等权净值 − 1）。
        """
        from app.services.signal_backtest_service import ChipSignalBacktestService
        from app.services.signal_defs import divergence_mask, resonance_mask, squeeze_mask

        signal = str(signal or "resonance").lower()
        if signal not in ("squeeze", "resonance", "divergence"):
            return {"error": f"未知信号 {signal}（支持 squeeze/resonance/divergence）"}
        horizon = max(1, int(horizon))
        months = max(3, min(int(months or 12), 24))

        panels = ChipSignalBacktestService(self.data_reader)._load_panels(months)
        if "error" in panels:
            return panels
        if signal in ("resonance", "divergence") and not panels["has_moneyflow"]:
            return {"error": "无资金流数据，resonance/divergence 无法寻优"}

        combos = _expand_grid(grid or DEFAULT_CHIP_GRID)
        if not combos:
            return {"error": "参数网格为空"}
        base = current_thresholds()

        dates: list = panels["dates"]
        # 非重叠锚点（与 nav 口径一致）；末尾锚点无 T+1+H 出场数据，剔除
        last_usable_pos = len(dates) - (2 + horizon)
        anchors = [d for k, d in enumerate(dates[::horizon])
                   if k * horizon <= last_usable_pos]

        def eval_combo(t: SignalThresholds,
                       anchor_slice: List[pd.Timestamp]) -> Optional[float]:
            """锚点子窗口上的链式超额（None = 无有效样本）。"""
            conc_thresh = panels["conc"].quantile(t.squeeze_conc_quantile, axis=1)
            if signal == "squeeze":
                mask = squeeze_mask(panels["winner"], panels["conc"], conc_thresh,
                                    panels["vol_ratio"], panels["pct5"], t)
            elif signal == "resonance":
                mask = resonance_mask(panels["net5"], panels["net_last"],
                                      panels["winner_chg"], panels["winner"],
                                      panels["pct5"], t)
            else:
                mask = divergence_mask(panels["pct5"], panels["net5"],
                                       panels["winner"], t)
            open_al = panels["open_al"]
            entry = open_al.shift(-1)
            fwd = open_al.shift(-(1 + horizon)) / entry - 1.0

            counts = mask.sum(axis=1)
            day_mean = fwd.where(mask).mean(axis=1)
            uni = fwd.mean(axis=1)

            idx = pd.Index(anchor_slice)
            sig = day_mean.reindex(idx).dropna()
            if sig.empty:
                return None
            bench = uni.reindex(sig.index).fillna(0.0)
            excess_nav = float((1 + sig).prod() / (1 + bench).prod() - 1.0)
            return excess_nav

        # 全样本网格 + K 段稳健分：把锚点按时间切成 4 段逐段评估，
        # robust = 0.6×中位段 + 0.4×最差段——一段大行情撑起来的参数会现形
        anchor_segments = split_segments(list(anchors), n_segments=4)
        grid_rows = []
        for combo in combos:
            t = replace(base, **combo)
            val = eval_combo(t, anchors)
            seg_excess = []
            for seg in anchor_segments:
                sv = eval_combo(t, seg)
                if sv is not None:
                    seg_excess.append(round(sv, 5))
            grid_rows.append({"params": combo, "excess": None if val is None else round(val, 5),
                              "segment_excess": seg_excess})
        valid = [r for r in grid_rows if r["excess"] is not None]
        valid.sort(key=lambda r: r["excess"], reverse=True)
        robust_rows = annotate_robust(grid_rows)
        best_robust = next((r for r in robust_rows if r["robust_score"] is not None), None)

        # walk-forward：锚点序列上滚动 IS/OOS
        is_n = max(2, is_days // horizon)
        oos_n = max(1, oos_days // horizon)
        windows: List[Dict[str, Any]] = []
        param_counts: Dict[str, Dict[float, int]] = {}
        i = 0
        while i + is_n + oos_n <= len(anchors):
            is_anchors = anchors[i:i + is_n]
            oos_anchors = anchors[i + is_n:i + is_n + oos_n]
            best_combo, best_val = None, None
            for combo in combos:
                val = eval_combo(replace(base, **combo), is_anchors)
                if val is not None and (best_val is None or val > best_val):
                    best_combo, best_val = combo, val
            if best_combo is not None:
                oos_val = eval_combo(replace(base, **best_combo), oos_anchors)
                windows.append({
                    "is_anchors": [str(pd.Timestamp(d).date()) for d in is_anchors[::max(1, is_n // 3)]],
                    "oos_anchors": [str(pd.Timestamp(d).date()) for d in oos_anchors],
                    "best_params": best_combo,
                    "is_excess": round(best_val, 5),
                    "oos_excess": None if oos_val is None else round(oos_val, 5),
                })
                for k, v in best_combo.items():
                    param_counts.setdefault(k, {})
                    param_counts[k][v] = param_counts[k].get(v, 0) + 1
            i += oos_n

        oos_vals = [w["oos_excess"] for w in windows if w["oos_excess"] is not None]
        chained = 1.0
        for v in oos_vals:
            chained *= 1 + v
        best_full = valid[0] if valid else None

        result: Dict[str, Any] = {
            "mode": "chip_threshold",
            "signal": signal,
            "horizon": horizon,
            "months": months,
            "n_combos": len(combos),
            "n_anchors": len(anchors),
            "grid_results": grid_rows,
            "best_full_sample": best_full,
            "best_robust": best_robust,
            "walk_forward": {
                "is_anchor_days": is_n * horizon,
                "oos_anchor_days": oos_n * horizon,
                "windows": windows,
                "param_stability": {
                    k: [{"value": v, "count": c} for v, c in
                        sorted(counts.items(), key=lambda kv: -kv[1])]
                    for k, counts in param_counts.items()
                },
                "summary": {
                    "n_windows": len(windows),
                    "oos_mean_excess": round(float(np.mean(oos_vals)), 5) if oos_vals else None,
                    "oos_chained_excess": round(chained - 1.0, 5) if oos_vals else None,
                    "oos_hit_rate": round(float(np.mean([v > 0 for v in oos_vals])), 3)
                    if oos_vals else None,
                    "oos_robust_score": robust_score(oos_vals, n_segments=4),
                },
            },
            "current_thresholds": {f.name: getattr(base, f.name)
                                   for f in SignalThresholds.__dataclass_fields__.values()},  # type: ignore[attr-defined]
            "note": ("全样本网格偏乐观（同段数据选参+评估）；可信结论看 walk_forward OOS；"
                     "排名看 robust_score（0.6×中位段+0.4×最差段），一段行情撑起来的参数会被压低。"
                     "评估 = H 日非重叠锚点链式超额（vs universe 等权）。"),
        }

        # 最常用参数（walk-forward 中被选中次数最多的组合）作为写回候选
        if param_counts:
            stable = {k: max(c, key=c.get) for k, c in param_counts.items()}
            result["write_back_candidate"] = stable
            if apply:
                new_t = replace(base, **stable)
                path = save_threshold_override(new_t)
                result["applied"] = {
                    "params": {f.name: getattr(new_t, f.name)
                               for f in SignalThresholds.__dataclass_fields__.values()},  # type: ignore[attr-defined]
                    "path": path,
                    "message": "已写回：ChipSignalService / ChipSignalBacktestService 即时读到同一阈值",
                }
        return result

    # ==================================================================
    # 二、行业轮动权重寻优
    # ==================================================================
    def rotation_weight_optimize(self, months: int = 12, top_n: int = 5,
                                 grid: Optional[Dict[str, List[float]]] = None,
                                 is_windows: int = 6, oos_windows: int = 2,
                                 rebalance_days: int = 20,
                                 apply: bool = False) -> Dict[str, Any]:
        """轮动评分权重网格 + walk-forward OOS。

        每个 rebalance_days 个交易日在当期截面算三维 z 分量，按权重合成评分，
        取 top_n 行业持有至下一调仓日；超额 = top_n 等权收益 − 全行业等权收益。
        """
        from datetime import datetime, timedelta

        months = max(6, min(int(months or 12), 24))
        top_n = max(1, int(top_n))
        rebalance_days = max(5, int(rebalance_days))
        combos = _expand_grid(grid or DEFAULT_ROTATION_GRID)
        if not combos:
            return {"error": "参数网格为空"}

        end = datetime.now()
        eval_start = end - timedelta(days=months * 31)
        warm_start = eval_start - timedelta(days=90)

        basic = self.data_reader.get_stock_basic()
        if basic.empty or "industry" not in basic.columns:
            return {"error": "无 stock_basic 行业映射"}
        ind_map = basic.dropna(subset=["industry"]).set_index("ts_code")["industry"]

        daily = self.data_reader.get_daily(ts_codes=None,
                                           start_date=warm_start.strftime("%Y-%m-%d"),
                                           end_date=end.strftime("%Y-%m-%d"))
        if daily.empty:
            return {"error": "行情数据为空"}
        daily = daily[daily["ts_code"].isin(ind_map.index)]
        close = daily.pivot_table(index="trade_date", columns="ts_code",
                                  values="close", aggfunc="last").sort_index()
        close.index = pd.to_datetime(close.index)
        ind_ret = close.pct_change().T.groupby(pd.Series(ind_map)).mean().T

        # 资金流（缺维度时 z 分量置 0）
        ind_net = None
        try:
            flow = self.data_reader.get_moneyflow(
                ts_codes=None, start_date=eval_start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"))
            if not flow.empty:
                flow = flow[flow["ts_code"].isin(ind_map.index)].copy()
                flow["main_net"] = (flow["buy_lg_amount"] + flow["buy_elg_amount"]
                                    - flow["sell_lg_amount"] - flow["sell_elg_amount"])
                net = flow.pivot_table(index="trade_date", columns="ts_code",
                                       values="main_net", aggfunc="last").sort_index()
                net.index = pd.to_datetime(net.index)
                ind_net = net.T.groupby(pd.Series(ind_map)).sum().T
        except Exception as e:
            logger.warning(f"轮动寻优读取资金流失败（资金维度置 0）: {e}")

        # 估值：行业 pe_ttm 中位数的当日截面分位（缺维度置 0）
        pe_rank = None
        try:
            db = self.data_reader.get_daily_basic(
                ts_codes=None, start_date=eval_start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"))
            if not db.empty and "pe_ttm" in db.columns:
                db = db[db["ts_code"].isin(ind_map.index)]
                pe = db.pivot_table(index="trade_date", columns="ts_code",
                                    values="pe_ttm", aggfunc="last").sort_index()
                pe.index = pd.to_datetime(pe.index)
                pe_ind = pe.T.groupby(pd.Series(ind_map)).median().T
                pe_rank = pe_ind.rank(pct=True, axis=1)
        except Exception as e:
            logger.warning(f"轮动寻优读取估值失败（估值维度置 0）: {e}")

        # 调仓日：评估窗口内每 rebalance_days 个交易日
        all_dates = [d for d in ind_ret.index if pd.Timestamp(d) >= pd.Timestamp(eval_start)]
        reb_dates = all_dates[::rebalance_days]
        # 前向收益：t → t+rebalance_days（收盘-收盘，行业累计净值比）
        cum = (1 + ind_ret.fillna(0)).cumprod()
        if len(reb_dates) < is_windows + oos_windows + 1:
            return {"error": f"调仓样本不足（{len(reb_dates)} < IS{is_windows}+OOS{oos_windows}+1），"
                             "请扩大 months 或缩短 rebalance_days"}

        mom20 = ind_ret.rolling(20).sum()
        flow5 = ind_net.rolling(5, min_periods=3).sum() if ind_net is not None else None
        flow20 = ind_net.rolling(20, min_periods=10).sum() if ind_net is not None else None

        def _z(s: pd.Series) -> pd.Series:
            std = s.std()
            if not np.isfinite(std) or std == 0:
                return s * 0.0
            return (s - s.mean()) / std

        def eval_weights(w: Dict[str, float],
                         reb_slice: List[pd.Timestamp]) -> Optional[float]:
            """调仓日子集上的链式超额。"""
            prod_sig, prod_all = 1.0, 1.0
            n_used = 0
            for t, t_next in zip(reb_slice[:-1], reb_slice[1:]):
                zm = _z(mom20.loc[t])
                zf = (_z(flow5.loc[t]) + _z(flow20.loc[t])) if flow5 is not None \
                    else zm * 0.0
                zv = -_z(pe_rank.loc[t]) if pe_rank is not None else zm * 0.0
                score = w["w_mom"] * zm + w["w_flow"] * zf + w["w_val"] * zv
                score = score.dropna()
                if len(score) < 2 * top_n:
                    continue
                top = score.nlargest(top_n).index
                # 区间收益：行业净值比
                r_top = float(cum.loc[t_next, top].mean() / cum.loc[t, top].mean() - 1) \
                    if len(top) else 0.0
                r_all = float(cum.loc[t_next].mean() / cum.loc[t].mean() - 1)
                if not (np.isfinite(r_top) and np.isfinite(r_all)):
                    continue
                prod_sig *= 1 + r_top
                prod_all *= 1 + r_all
                n_used += 1
            if n_used == 0:
                return None
            return prod_sig / prod_all - 1.0

        # 全样本 + K 段稳健分（调仓日按时间切 4 段逐段评估）
        reb_segments = split_segments(list(reb_dates), n_segments=4)
        grid_rows = []
        for combo in combos:
            val = eval_weights(combo, reb_dates)
            seg_excess = []
            for seg in reb_segments:
                sv = eval_weights(combo, seg)
                if sv is not None:
                    seg_excess.append(round(sv, 5))
            grid_rows.append({"params": combo,
                              "excess": None if val is None else round(val, 5),
                              "segment_excess": seg_excess})
        valid = [r for r in grid_rows if r["excess"] is not None]
        valid.sort(key=lambda r: r["excess"], reverse=True)
        robust_rows = annotate_robust(grid_rows)
        best_robust = next((r for r in robust_rows if r["robust_score"] is not None), None)

        # walk-forward：调仓样本序列上滚动
        windows: List[Dict[str, Any]] = []
        param_counts: Dict[str, Dict[float, int]] = {}
        i = 0
        while i + is_windows + oos_windows + 1 <= len(reb_dates):
            is_slice = reb_dates[i:i + is_windows + 1]
            oos_slice = reb_dates[i + is_windows:i + is_windows + oos_windows + 1]
            best_combo, best_val = None, None
            for combo in combos:
                val = eval_weights(combo, is_slice)
                if val is not None and (best_val is None or val > best_val):
                    best_combo, best_val = combo, val
            if best_combo is not None:
                oos_val = eval_weights(best_combo, oos_slice)
                windows.append({
                    "is_first": str(pd.Timestamp(is_slice[0]).date()),
                    "oos_first": str(pd.Timestamp(oos_slice[0]).date()),
                    "oos_last": str(pd.Timestamp(oos_slice[-1]).date()),
                    "best_params": best_combo,
                    "is_excess": round(best_val, 5),
                    "oos_excess": None if oos_val is None else round(oos_val, 5),
                })
                for k, v in best_combo.items():
                    param_counts.setdefault(k, {})
                    param_counts[k][v] = param_counts[k].get(v, 0) + 1
            i += oos_windows

        oos_vals = [w["oos_excess"] for w in windows if w["oos_excess"] is not None]
        chained = 1.0
        for v in oos_vals:
            chained *= 1 + v

        result: Dict[str, Any] = {
            "mode": "rotation_weight",
            "months": months,
            "top_n": top_n,
            "rebalance_days": rebalance_days,
            "n_rebalances": len(reb_dates),
            "n_combos": len(combos),
            "grid_results": grid_rows,
            "best_full_sample": valid[0] if valid else None,
            "best_robust": best_robust,
            "walk_forward": {
                "is_windows": is_windows,
                "oos_windows": oos_windows,
                "windows": windows,
                "param_stability": {
                    k: [{"value": v, "count": c} for v, c in
                        sorted(counts.items(), key=lambda kv: -kv[1])]
                    for k, counts in param_counts.items()
                },
                "summary": {
                    "n_windows": len(windows),
                    "oos_mean_excess": round(float(np.mean(oos_vals)), 5) if oos_vals else None,
                    "oos_chained_excess": round(chained - 1.0, 5) if oos_vals else None,
                    "oos_hit_rate": round(float(np.mean([v > 0 for v in oos_vals])), 3)
                    if oos_vals else None,
                    "oos_robust_score": robust_score(oos_vals, n_segments=4),
                },
            },
            "current_weights": self.current_rotation_weights(),
            "note": ("超额 = top_n 行业等权净值 / 全行业等权净值 − 1（每调仓段链式承接）；"
                     "全样本网格偏乐观，可信结论看 walk_forward OOS；排名看 robust_score。"),
        }
        if param_counts:
            stable = {k: max(c, key=c.get) for k, c in param_counts.items()}
            result["write_back_candidate"] = stable
            if apply:
                result["applied"] = {
                    "params": stable,
                    **self.save_rotation_weights(stable),
                }
        return result

    # ------------------------------------------------------------------
    # 轮动权重持久化（data/config/rotation_weights.json）
    # ------------------------------------------------------------------
    @staticmethod
    def _weights_path() -> str:
        import os
        data_dir = os.getenv(
            "DATA_DIR",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
        )
        return os.path.join(data_dir, "config", "rotation_weights.json")

    def current_rotation_weights(self) -> Dict[str, float]:
        import json, os
        try:
            with open(self._weights_path(), encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                return {k: float(payload.get(k, _DEFAULT_ROTATION_WEIGHTS[k]))
                        for k in _DEFAULT_ROTATION_WEIGHTS}
        except FileNotFoundError:
            pass
        except Exception:
            logger.warning("rotation_weights.json 解析失败，回退默认权重")
        return dict(_DEFAULT_ROTATION_WEIGHTS)

    def save_rotation_weights(self, weights: Dict[str, float]) -> Dict[str, Any]:
        import json, os
        clean = {k: float(weights.get(k, _DEFAULT_ROTATION_WEIGHTS[k]))
                 for k in _DEFAULT_ROTATION_WEIGHTS}
        path = self._weights_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return {"path": path,
                "message": "已写回：IndustryRotationService 评分即时按新权重合成"}
