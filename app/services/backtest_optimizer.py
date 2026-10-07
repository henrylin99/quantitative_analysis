"""单股技术策略参数寻优 + Walk-Forward 样本外验证。

复用 SingleStockBacktestEngine（同一成交/成本口径），在其上做两件事：

- grid_search：全样本网格搜索。所有参数组合在同一段数据上回测并按
  metric（默认 sharpe）排名。注意全样本寻优天然偏乐观——它回答
  "参数敏感度如何"，不回答"参数是否过拟合"；可信结论看 walk_forward。
- walk_forward：滚动 IS/OOS。IS 窗内网格选参 → 紧随 OOS 窗用最优参数
  验证 → 窗口按步长前推、各 OOS 段收益链式承接。输出 OOS 汇总 +
  参数稳定性（各参数被选中的频率）——OOS 显著差于 IS 即过拟合信号。

参数网格只覆盖引擎真正消费参数的策略：ma_cross（ma_short/ma_long）、
kdj（oversold/overbought）、rsi（oversold/overbought）。macd/bollinger
的轨道值来自预存技术因子列，引擎不读参数，寻优无意义。
"""

from __future__ import annotations

from datetime import timedelta
from itertools import product
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.services.single_stock_backtest import SingleStockBacktestEngine
from app.services.stock_service import StockService

_DEFAULT_GRIDS: Dict[str, Dict[str, List[Any]]] = {
    "ma_cross": {"ma_short": [5, 10, 20], "ma_long": [20, 30, 60]},
    "kdj": {"oversold": [15, 20, 30], "overbought": [70, 80, 85]},
    "rsi": {"oversold": [20, 25, 30], "overbought": [70, 75, 80]},
}

_OPTIMIZEABLE = tuple(_DEFAULT_GRIDS)
_METRICS = ("sharpe_ratio", "total_return", "annual_return")

_WARMUP_DAYS = 120  # 指标预热（与 API 层 100 天同量级，稍宽）
_MAX_COMBOS = 64


def expand_grid(strategy_type: str, grid: Optional[Dict[str, List[Any]]] = None) -> List[Dict[str, Any]]:
    """展开参数网格为组合列表；非法组合（短均线≥长均线、超卖≥超买）剔除。"""
    base = grid or _DEFAULT_GRIDS.get(strategy_type)
    if not base:
        return []
    keys = sorted(base)
    combos = []
    for values in product(*(base[k] for k in keys)):
        combo = dict(zip(keys, values))
        if strategy_type == "ma_cross" and combo.get("ma_short", 0) >= combo.get("ma_long", 1):
            continue
        if strategy_type in ("kdj", "rsi") \
                and combo.get("oversold", 0) >= combo.get("overbought", 1):
            continue
        combos.append(combo)
        if len(combos) >= _MAX_COMBOS:
            break
    return combos


class BacktestOptimizerService:
    def __init__(self):
        pass

    # ------------------------------------------------------------------
    def _load_data(self, ts_code: str, start_date: str, end_date: str) -> Tuple[List[dict], List[dict]]:
        extended_start = (str_to_date(start_date) - timedelta(days=_WARMUP_DAYS)).strftime("%Y-%m-%d")
        # limit 放宽：回测区间长时 500 条会截断（get_daily_history 取最新 limit 条）
        history = StockService.get_daily_history(ts_code, start_date=extended_start,
                                                 end_date=end_date, limit=5000)
        factors = StockService.get_stock_factors(ts_code, start_date=extended_start,
                                                 end_date=end_date, limit=5000)
        return history, factors

    @staticmethod
    def _run_once(strategy_type: str, params: Dict[str, Any], history, factors,
                  start_date: str, end_date: str, initial_capital: float) -> Dict[str, Any]:
        engine = SingleStockBacktestEngine({
            "ts_code": "OPT",
            "strategy_type": strategy_type,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "params": params,
        })
        try:
            result = engine.run_backtest(history, factors)
        except Exception as e:  # 数据不足等 → 该组合记为无效
            logger.debug(f"寻优组合回测失败 params={params}: {e}")
            return {"params": params, "valid": False, "error": str(e),
                    "total_return": None, "sharpe_ratio": None, "max_drawdown": None,
                    "win_rate": None, "total_trades": 0, "benchmark_return": None}
        perf = result["performance"]
        return {"params": params, "valid": True,
                "total_return": perf["total_return"],
                "annual_return": perf.get("annual_return"),
                "sharpe_ratio": perf["sharpe_ratio"],
                "max_drawdown": perf["max_drawdown"],
                "win_rate": perf["win_rate"],
                "total_trades": perf["total_trades"],
                "benchmark_return": perf["benchmark_return"]}

    # ------------------------------------------------------------------
    def grid_search(self, ts_code: str, strategy_type: str, start_date: str,
                    end_date: str, grid: Optional[Dict[str, List[Any]]] = None,
                    metric: str = "sharpe_ratio",
                    initial_capital: float = 1_000_000.0) -> Dict[str, Any]:
        if strategy_type not in _OPTIMIZEABLE:
            return {"error": f"策略 {strategy_type} 的参数由预存技术因子决定，暂不支持寻优"
                             f"（支持：{'、'.join(_OPTIMIZEABLE)}）"}
        if metric not in _METRICS:
            metric = "sharpe_ratio"
        combos = expand_grid(strategy_type, grid)
        if not combos:
            return {"error": "参数网格为空"}

        history, factors = self._load_data(ts_code, start_date, end_date)
        if not history:
            return {"error": "无行情数据"}

        rows = [self._run_once(strategy_type, combo, history, factors,
                               start_date, end_date, initial_capital)
                for combo in combos]
        valid = [r for r in rows if r["valid"]]
        valid.sort(key=lambda r: (r.get(metric) if r.get(metric) is not None else -1e9),
                   reverse=True)
        # results 按指标降序，无效组合垫底
        results = valid + [r for r in rows if not r["valid"]]
        return {
            "mode": "grid",
            "ts_code": ts_code,
            "strategy_type": strategy_type,
            "metric": metric,
            "n_combos": len(rows),
            "results": results,
            "best": valid[0] if valid else None,
            "note": "全样本网格搜索结果偏乐观（同一段数据既选参又评估），"
                    "参数敏感度参考 walk_forward 的样本外结果",
        }

    # ------------------------------------------------------------------
    def walk_forward(self, ts_code: str, strategy_type: str, start_date: str,
                     end_date: str, grid: Optional[Dict[str, List[Any]]] = None,
                     metric: str = "sharpe_ratio", is_days: int = 120,
                     oos_days: int = 60, step: Optional[int] = None,
                     initial_capital: float = 1_000_000.0) -> Dict[str, Any]:
        if strategy_type not in _OPTIMIZEABLE:
            return {"error": f"策略 {strategy_type} 暂不支持寻优"
                             f"（支持：{'、'.join(_OPTIMIZEABLE)}）"}
        if metric not in _METRICS:
            metric = "sharpe_ratio"
        combos = expand_grid(strategy_type, grid)
        if not combos:
            return {"error": "参数网格为空"}
        is_days = max(30, int(is_days))
        oos_days = max(10, int(oos_days))
        step = max(oos_days, int(step or oos_days))  # 步长 ≥ OOS 长度 → OOS 不重叠

        history, factors = self._load_data(ts_code, start_date, end_date)
        if not history:
            return {"error": "无行情数据"}

        # 交易日序列（取回测区间的行情日期）
        all_dates = sorted({r["trade_date"] for r in history
                            if start_date <= str(r["trade_date"]) <= end_date})
        if len(all_dates) < is_days + oos_days:
            return {"error": f"区间交易日不足（{len(all_dates)} < IS{is_days}+OOS{oos_days}）"}

        windows: List[Dict[str, Any]] = []
        param_counts: Dict[str, Dict[Any, int]] = {}
        i = 0
        while i + is_days + oos_days <= len(all_dates):
            is_start, is_end = all_dates[i], all_dates[i + is_days - 1]
            oos_start, oos_end = all_dates[i + is_days], all_dates[i + is_days + oos_days - 1]

            is_rows = [self._run_once(strategy_type, combo, history, factors,
                                      is_start, is_end, initial_capital)
                       for combo in combos]
            is_valid = [r for r in is_rows if r["valid"] and r.get(metric) is not None]
            if not is_valid:
                i += step
                continue
            is_valid.sort(key=lambda r: r[metric], reverse=True)
            best = is_valid[0]

            oos = self._run_once(strategy_type, best["params"], history, factors,
                                 oos_start, oos_end, initial_capital)
            windows.append({
                "is_start": is_start, "is_end": is_end,
                "oos_start": oos_start, "oos_end": oos_end,
                "best_params": best["params"],
                "is_metric": best[metric],
                "is_total_return": best["total_return"],
                "oos_total_return": oos.get("total_return"),
                "oos_sharpe": oos.get("sharpe_ratio"),
                "oos_trades": oos.get("total_trades"),
                "oos_benchmark_return": oos.get("benchmark_return"),
                "oos_valid": oos.get("valid", False),
            })
            for k, v in best["params"].items():
                param_counts.setdefault(k, {})
                param_counts[k][v] = param_counts[k].get(v, 0) + 1
            i += step

        if not windows:
            return {"error": "无有效窗口（IS 段全部无信号或数据不足）"}

        oos_rets = [w["oos_total_return"] for w in windows
                    if w["oos_valid"] and w["oos_total_return"] is not None]
        is_metrics = [w["is_metric"] for w in windows]
        chained = 1.0
        for r in oos_rets:
            chained *= 1 + r
        n_profit = sum(1 for r in oos_rets if r > 0)

        return {
            "mode": "walk_forward",
            "ts_code": ts_code,
            "strategy_type": strategy_type,
            "metric": metric,
            "is_days": is_days,
            "oos_days": oos_days,
            "step": step,
            "n_combos": len(combos),
            "windows": windows,
            "param_stability": {
                k: [{"value": v, "count": c} for v, c in
                    sorted(counts.items(), key=lambda kv: -kv[1])]
                for k, counts in param_counts.items()
            },
            "summary": {
                "n_windows": len(windows),
                "n_oos_valid": len(oos_rets),
                "oos_hit_rate": round(n_profit / len(oos_rets), 3) if oos_rets else None,
                "oos_chained_return": round(chained - 1, 4) if oos_rets else None,
                "oos_mean_return": (round(sum(oos_rets) / len(oos_rets), 4)
                                    if oos_rets else None),
                "is_mean_metric": (round(sum(is_metrics) / len(is_metrics), 4)
                                   if is_metrics else None),
            },
            "note": "IS 段选参、紧随 OOS 段验证（步长≥OOS 长度，无重叠）；"
                    "各 OOS 段收益按全仓口径链式承接",
        }


def str_to_date(s: str):
    from datetime import datetime as _dt
    return _dt.strptime(str(s)[:10], "%Y-%m-%d")
