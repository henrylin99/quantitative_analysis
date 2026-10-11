"""Paper trading 模拟盘：纯虚拟记账，无任何券商接口。

设计（研究口径，非投资建议）：
- 虚拟账户：现金 + 持仓（加权平均成本）+ 交易流水 + 待执行单 + 逐日盯市净值，
  全部落 ``data/paper_trading/account.json``（原子写）。
- 信号源：筹码三类信号（复用 ChipSignalService），多头组合 = resonance 优先、
  squeeze 补足的 top-N 等权。
- 生命周期：18:30 信号 → 生成待执行单（以信号日收盘价记 target_value）→
  次日开盘虚拟成交（T+1）；停牌（无行情）当日跳过保留挂单，开盘涨停不买入、
  开盘跌停不卖出；连续 3 个交易日未成交则过期撤销。
- 成本：佣金+滑点双边、印花税卖出单边（与 backtest_engine 同口径）。
- 对齐报告：与"信号篮子 close-close 等权收益"（回测同口径基准）逐日对比，
  跟踪误差归因到 成交价差 / 交易成本 / 未成交。

调度：DailyAlertScheduler 18:30 链（run_scan 之后）；PAPER_TRADING_ENABLED=0 关闭。
API：/api/paper-trading/*（见 app/api/paper_trading_api.py）。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

from config import Config

_DIR_NAME = "paper_trading"
_FILE_NAME = "account.json"

DEFAULT_INITIAL_CASH = 1_000_000.0
DEFAULT_TOP_N = 10
_MAX_ORDER_ATTEMPTS = 3

_lock = threading.Lock()


def _limit_pct(ts_code: str, name: str = "") -> float:
    """涨跌停幅度（与 backtest_engine._limit_pct 同规则）。"""
    prefix = ts_code.split(".")[0]
    if prefix.startswith(("300", "301", "688", "689")):
        return 0.20
    if prefix.startswith(("8", "4", "92")):
        return 0.30
    if "ST" in name.upper():
        return 0.05
    return 0.10


class PaperTradingService:
    def __init__(self, data_dir: Optional[str] = None,
                 data_reader=None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(
                    os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir
        self._reader = data_reader

    # ------------------------------------------------------------------
    # 存储
    # ------------------------------------------------------------------
    @property
    def _file_path(self) -> str:
        return os.path.join(self.data_dir, _DIR_NAME, _FILE_NAME)

    @property
    def reader(self):
        if self._reader is None:
            from app.services.data_reader import ParquetDataReader
            self._reader = ParquetDataReader()
        return self._reader

    def _load(self) -> Dict[str, Any]:
        try:
            with open(self._file_path, encoding="utf-8") as f:
                state = json.load(f)
            if isinstance(state, dict) and "cash" in state:
                return state
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"读取模拟盘状态失败（将重建）: {e}")
        return self._new_state()

    @staticmethod
    def _new_state(initial_cash: float = DEFAULT_INITIAL_CASH,
                   top_n: int = DEFAULT_TOP_N) -> Dict[str, Any]:
        return {
            "account_id": "paper-main",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "initial_cash": float(initial_cash),
            "top_n": int(top_n),
            "commission_rate": 0.0003,
            "slippage_rate": 0.001,
            "cash": float(initial_cash),
            "positions": {},        # ts_code -> {qty, avg_cost, since}
            "pending_orders": [],   # 待执行单（含重试）
            "trades": [],           # 成交流水
            "nav_history": [],      # 逐日盯市
            "stats": {"filled": 0, "skipped": 0, "expired": 0},
        }

    def _save(self, state: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        tmp = self._file_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, self._file_path)

    # ------------------------------------------------------------------
    # 信号 → 待执行单
    # ------------------------------------------------------------------
    def _select_targets(self, scan: Dict[str, Any]) -> List[Dict[str, Any]]:
        n = self._top_n()
        picked: List[Dict[str, Any]] = []
        seen = set()
        for key in ("resonance", "squeeze"):
            for row in scan.get(key, []):
                code = row.get("ts_code")
                if code and code not in seen:
                    picked.append(row)
                    seen.add(code)
                if len(picked) >= n:
                    return picked
        return picked

    def _top_n(self, state: Optional[Dict[str, Any]] = None) -> int:
        return int((state or self._load()).get("top_n", DEFAULT_TOP_N))

    def generate_orders(self, scan: Optional[Dict[str, Any]] = None,
                        force: bool = False) -> Dict[str, Any]:
        """按当日筹码信号生成待执行单（同信号日不重复生成）。"""
        with _lock:
            state = self._load()
            if scan is None:
                from app.services.chip_signal_service import ChipSignalService
                scan = ChipSignalService(data_reader=self.reader).scan()
            if not isinstance(scan, dict) or "error" in scan or not scan.get("stats"):
                return {"ok": False, "message": f"信号不可用: {scan.get('error') if isinstance(scan, dict) else '无效返回'}"}

            signal_date = scan["stats"].get("scan_date")
            if not signal_date:
                return {"ok": False, "message": "信号缺少 scan_date"}
            if not force and any(o.get("signal_date") == signal_date
                                 for o in state["pending_orders"]):
                return {"ok": True, "message": "该信号日挂单已存在", "signal_date": signal_date}

            targets = self._select_targets(scan)
            target_codes = {r["ts_code"] for r in targets}
            closes = {r["ts_code"]: float(r["close"]) for r in targets}
            equity = self._equity(state, closes)
            per_value = equity / max(len(targets), 1) if targets else 0.0

            created: List[Dict[str, Any]] = []
            # 先卖后买：不在目标内的持仓全部挂卖
            for code in list(state["positions"]):
                if code not in target_codes:
                    created.append(self._make_order(
                        signal_date, code, "sell",
                        signal_close=self._last_known_close(state, code),
                        target_value=0.0,
                        reason="调出信号组合"))
            for row in targets:
                code = row["ts_code"]
                held = state["positions"].get(code)
                if held:
                    continue  # 已持有，等权再平衡不折腾（降低换手）
                created.append(self._make_order(
                    signal_date, code, "buy",
                    signal_close=closes[code],
                    target_value=per_value,
                    reason=f"chip_signal({'resonance' if code in {r['ts_code'] for r in scan.get('resonance', [])} else 'squeeze'})"))

            state["pending_orders"].extend(created)
            state["last_signal_date"] = signal_date
            state["last_target_codes"] = sorted(target_codes)
            self._save(state)
            return {
                "ok": True, "signal_date": signal_date,
                "targets": sorted(target_codes),
                "orders_created": len(created),
                "orders": [{k: o[k] for k in ("order_id", "ts_code", "side", "signal_close", "target_value")}
                           for o in created],
            }

    @staticmethod
    def _make_order(signal_date: str, ts_code: str, side: str,
                    signal_close: Optional[float], target_value: float,
                    reason: str) -> Dict[str, Any]:
        return {
            "order_id": f"{signal_date}-{side}-{ts_code}",
            "signal_date": signal_date,
            "ts_code": ts_code,
            "side": side,
            "signal_close": signal_close,
            "target_value": round(float(target_value), 2),
            "reason": reason,
            "status": "pending",
            "attempts": 0,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _last_known_close(self, state: Dict[str, Any], ts_code: str) -> Optional[float]:
        for t in reversed(state["trades"]):
            if t.get("ts_code") == ts_code:
                return t.get("price")
        pos = state["positions"].get(ts_code)
        return pos.get("avg_cost") if pos else None

    def _equity(self, state: Dict[str, Any],
                closes: Dict[str, float]) -> float:
        mv = sum(
            p["qty"] * closes.get(code, p["avg_cost"])
            for code, p in state["positions"].items()
        )
        return state["cash"] + mv

    # ------------------------------------------------------------------
    # 次日开盘虚拟成交
    # ------------------------------------------------------------------
    def settle(self, exec_date: Optional[str] = None) -> Dict[str, Any]:
        """对 pending 且 signal_date < exec_date 的挂单按开盘价虚拟成交。"""
        with _lock:
            state = self._load()
            if exec_date is None:
                dates = self.reader.get_trade_dates()
                if not dates:
                    return {"ok": False, "message": "无交易日历"}
                exec_date = dates[-1]
            exec_date = str(exec_date).replace("-", "")

            pending = [o for o in state["pending_orders"]
                       if o["status"] == "pending"
                       and str(o["signal_date"]).replace("-", "") < exec_date]
            if not pending:
                return {"ok": True, "exec_date": exec_date, "filled": 0, "message": "无待执行单"}

            codes = sorted({o["ts_code"] for o in pending})
            try:
                df = self.reader.get_daily(ts_codes=codes,
                                           start_date=exec_date, end_date=exec_date)
            except Exception as e:
                return {"ok": False, "message": f"读取执行日行情失败: {e}"}
            if df.empty:
                return {"ok": True, "exec_date": exec_date, "filled": 0,
                        "message": "执行日无行情（可能未更新），挂单保留"}

            # 名称（ST 判定）
            names: Dict[str, str] = {}
            try:
                basic = self.reader.get_stock_basic()
                sub = basic[basic["ts_code"].isin(set(codes))]
                names = {r["ts_code"]: str(r.get("name") or "") for _, r in sub.iterrows()}
            except Exception:
                pass

            bars: Dict[str, Dict[str, float]] = {}
            for _, row in df.iterrows():
                code = row["ts_code"]
                open_p = row.get("open")
                pre = row.get("pre_close")
                close = row.get("close")
                if open_p is None or pd.isna(open_p) or float(open_p) <= 0:
                    continue
                open_p = float(open_p)
                pre_p = float(pre) if pre is not None and not pd.isna(pre) and float(pre) > 0 else None
                chg_open = (open_p / pre_p - 1.0) if pre_p else None
                limit = _limit_pct(code, names.get(code, ""))
                bars[code] = {
                    "open": open_p,
                    "close": float(close) if close is not None and not pd.isna(close) else open_p,
                    "chg_open": chg_open,
                    "limit_up_open": chg_open is not None and chg_open >= limit - 0.002,
                    "limit_down_open": chg_open is not None and chg_open <= -(limit - 0.002),
                }

            # 先卖后买
            filled = skipped = expired = 0
            order_by_id = {o["order_id"]: o for o in state["pending_orders"]}
            for order in sorted(pending, key=lambda o: 0 if o["side"] == "sell" else 1):
                oid = order["order_id"]
                code = order["ts_code"]
                bar = bars.get(code)
                order["attempts"] = int(order.get("attempts", 0)) + 1
                if bar is None:
                    order["status"] = "skipped"
                    order["skip_reason"] = "停牌/无行情"
                    skipped += 1
                    state["stats"]["skipped"] += 1
                elif order["side"] == "buy" and bar["limit_up_open"]:
                    order["status"] = "skipped"
                    order["skip_reason"] = "开盘涨停不可买"
                    skipped += 1
                    state["stats"]["skipped"] += 1
                elif order["side"] == "sell" and bar["limit_down_open"]:
                    order["status"] = "skipped"
                    order["skip_reason"] = "开盘跌停不可卖"
                    skipped += 1
                    state["stats"]["skipped"] += 1
                else:
                    ok = self._fill(state, order, bar, exec_date)
                    if ok:
                        filled += 1
                        state["stats"]["filled"] += 1
                    else:
                        skipped += 1
                        state["stats"]["skipped"] += 1
                # 跳过/未成的单：attempts 超限则过期；否则恢复 pending 等次日
                if order["status"] == "skipped":
                    if order["attempts"] >= _MAX_ORDER_ATTEMPTS:
                        order["status"] = "expired"
                        expired += 1
                        state["stats"]["expired"] += 1
                    else:
                        order["status"] = "pending"
                        order.pop("skip_reason", None)
                        skipped -= 1
                        state["stats"]["skipped"] -= 1
            _ = order_by_id  # 保留索引便于调试

            state["pending_orders"] = [
                o for o in state["pending_orders"] if o["status"] == "pending"] + [
                o for o in state["pending_orders"] if o["status"] != "pending"]
            self._save(state)
            return {"ok": True, "exec_date": exec_date, "filled": filled,
                    "skipped": skipped, "expired": expired}

    def _fill(self, state: Dict[str, Any], order: Dict[str, Any],
              bar: Dict[str, float], exec_date: str) -> bool:
        code = order["ts_code"]
        price = bar["open"]
        pos = state["positions"].get(code)
        if order["side"] == "sell":
            if not pos or pos["qty"] <= 0:
                order["status"] = "cancelled"
                order["note"] = "无持仓可卖"
                return True  # 无需成交，直接关闭
            qty = pos["qty"]
            value = qty * price
            costs = self._costs(state, value, sell_value=value)
            proceeds = value - costs["total_cost"]
            state["cash"] += proceeds
            del state["positions"][code]
            order["status"] = "filled"
            self._record_trade(state, exec_date, order, qty, price, costs)
            return True

        # buy
        budget = min(order["target_value"], state["cash"])
        lot = int(budget / (price * 100)) * 100
        if lot < 100:
            order["status"] = "skipped"
            order["skip_reason"] = "资金不足一手"
            return False
        value = lot * price
        costs = self._costs(state, value)
        while lot >= 100 and value + costs["total_cost"] > state["cash"]:
            lot -= 100
            value = lot * price
            costs = self._costs(state, value)
        if lot < 100:
            order["status"] = "skipped"
            order["skip_reason"] = "资金不足一手"
            return False
        state["cash"] -= value + costs["total_cost"]
        if pos:
            new_qty = pos["qty"] + lot
            pos["avg_cost"] = (pos["avg_cost"] * pos["qty"] + value + costs["total_cost"]) / new_qty
            pos["qty"] = new_qty
        else:
            state["positions"][code] = {
                "qty": lot, "avg_cost": (value + costs["total_cost"]) / lot,
                "since": exec_date,
            }
        order["status"] = "filled"
        self._record_trade(state, exec_date, order, lot, price, costs)
        return True

    @staticmethod
    def _costs(state: Dict[str, Any], value: float,
               sell_value: float = 0.0) -> Dict[str, float]:
        commission = value * state["commission_rate"]
        slippage = value * state["slippage_rate"]
        stamp = sell_value * Config.DEFAULT_STAMP_DUTY_RATE
        return {"commission": round(commission, 2), "slippage": round(slippage, 2),
                "stamp_duty": round(stamp, 2),
                "total_cost": round(commission + slippage + stamp, 2)}

    def _record_trade(self, state: Dict[str, Any], exec_date: str,
                      order: Dict[str, Any], qty: int, price: float,
                      costs: Dict[str, float]) -> None:
        gap = None
        if order.get("signal_close"):
            gap = round(price / order["signal_close"] - 1.0, 5)
        state["trades"].append({
            "trade_id": len(state["trades"]) + 1,
            "date": exec_date,
            "order_id": order["order_id"],
            "ts_code": order["ts_code"],
            "side": order["side"],
            "qty": qty,
            "price": round(price, 3),
            "value": round(qty * price, 2),
            "costs": costs,
            "signal_close": order.get("signal_close"),
            "price_gap": gap,
            "reason": order.get("reason"),
        })

    # ------------------------------------------------------------------
    # 逐日盯市
    # ------------------------------------------------------------------
    def mark(self, date: Optional[str] = None) -> Dict[str, Any]:
        """按收盘价盯市，写 nav_history；同时记录信号篮子基准收益。"""
        with _lock:
            state = self._load()
            if date is None:
                dates = self.reader.get_trade_dates()
                if not dates:
                    return {"ok": False, "message": "无交易日历"}
                date = dates[-1]
            date = str(date).replace("-", "")
            if state["nav_history"] and state["nav_history"][-1]["date"] == date:
                return {"ok": True, "date": date, "message": "已盯市"}

            codes = list(state["positions"])
            closes: Dict[str, float] = {}
            basket_ret = None
            if codes:
                try:
                    df = self.reader.get_daily(ts_codes=codes,
                                               start_date=date, end_date=date)
                    for _, row in df.iterrows():
                        c = float(row["close"])
                        if c > 0:
                            closes[row["ts_code"]] = c
                except Exception as e:
                    logger.warning(f"模拟盘盯市读取行情失败: {e}")
            # 缺行情的持仓沿用 avg_cost 兜底（保守）
            market_value = sum(
                p["qty"] * closes.get(code, p["avg_cost"])
                for code, p in state["positions"].items()
            )
            nav = state["cash"] + market_value
            prev = state["nav_history"][-1] if state["nav_history"] else None
            paper_ret = (nav / prev["nav"] - 1.0) if prev and prev["nav"] > 0 else 0.0

            # 基准：信号篮子（last_target_codes）当日等权 close-close 收益
            target_codes = state.get("last_target_codes") or []
            if target_codes:
                basket_ret = self._basket_return(target_codes, date)

            state["nav_history"].append({
                "date": date,
                "cash": round(state["cash"], 2),
                "market_value": round(market_value, 2),
                "nav": round(nav, 2),
                "positions": len(state["positions"]),
                "paper_ret": round(paper_ret, 6),
                "basket_ret": round(basket_ret, 6) if basket_ret is not None else None,
            })
            state["nav_history"] = state["nav_history"][-500:]
            self._save(state)
            return {"ok": True, "date": date, "nav": round(nav, 2)}

    def _basket_return(self, codes: List[str], date: str) -> Optional[float]:
        """信号篮子当日等权收益（回测同口径的 close-close 基准）。"""
        try:
            df = self.reader.get_daily(ts_codes=list(codes),
                                       start_date=date, end_date=date)
            if df.empty or "pct_chg" not in df.columns:
                return None
            rets = pd.to_numeric(df["pct_chg"], errors="coerce").dropna() / 100.0
            rets = rets[rets.abs() < 0.35]
            if rets.empty:
                return None
            return float(rets.mean())
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 日常入口（18:30 链）
    # ------------------------------------------------------------------
    def run_daily(self) -> Dict[str, Any]:
        """结算（今日开盘）→ 盯市（今日收盘）→ 生成明日挂单（今日信号）。"""
        result: Dict[str, Any] = {"settle": None, "mark": None, "orders": None}
        try:
            result["settle"] = self.settle()
        except Exception as e:
            logger.error(f"模拟盘结算失败: {e}")
            result["settle"] = {"ok": False, "message": str(e)}
        try:
            result["mark"] = self.mark()
        except Exception as e:
            logger.error(f"模拟盘盯市失败: {e}")
            result["mark"] = {"ok": False, "message": str(e)}
        try:
            result["orders"] = self.generate_orders()
        except Exception as e:
            logger.error(f"模拟盘生成挂单失败: {e}")
            result["orders"] = {"ok": False, "message": str(e)}
        return result

    # ------------------------------------------------------------------
    # 查询与对齐报告
    # ------------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        state = self._load()
        codes = list(state["positions"])
        closes: Dict[str, float] = {}
        if codes:
            try:
                dates = self.reader.get_trade_dates()
                if dates:
                    df = self.reader.get_daily(ts_codes=codes,
                                               start_date=dates[-1], end_date=dates[-1])
                    for _, row in df.iterrows():
                        c = float(row["close"])
                        if c > 0:
                            closes[row["ts_code"]] = c
            except Exception:
                pass
        positions = []
        for code, p in state["positions"].items():
            last = closes.get(code, p["avg_cost"])
            mv = p["qty"] * last
            cost = p["qty"] * p["avg_cost"]
            positions.append({
                "ts_code": code, "qty": p["qty"],
                "avg_cost": round(p["avg_cost"], 3),
                "last_close": round(last, 3),
                "market_value": round(mv, 2),
                "pnl": round(mv - cost, 2),
                "pnl_pct": round(mv / cost - 1.0, 4) if cost > 0 else None,
                "since": p.get("since"),
            })
        positions.sort(key=lambda r: -r["market_value"])
        nav = state["nav_history"][-1]["nav"] if state["nav_history"] \
            else state["cash"]
        return {
            "account_id": state["account_id"],
            "created_at": state["created_at"],
            "initial_cash": state["initial_cash"],
            "top_n": state["top_n"],
            "cash": round(state["cash"], 2),
            "nav": round(nav, 2),
            "total_pnl": round(nav - state["initial_cash"], 2),
            "total_pnl_pct": round(nav / state["initial_cash"] - 1.0, 4),
            "positions": positions,
            "pending_orders": [o for o in state["pending_orders"] if o["status"] == "pending"],
            "closed_orders": [o for o in state["pending_orders"] if o["status"] != "pending"][-50:],
            "stats": state["stats"],
            "last_signal_date": state.get("last_signal_date"),
        }

    def history(self, limit: int = 200) -> Dict[str, Any]:
        state = self._load()
        return {
            "nav_history": state["nav_history"][-limit:],
            "trades": state["trades"][-limit:],
        }

    def alignment_report(self) -> Dict[str, Any]:
        """与回测口径（信号篮子 close-close 等权）的对齐报告与跟踪误差归因。"""
        state = self._load()
        nav_hist = state["nav_history"]
        trades = state["trades"]
        pairs = [(r["paper_ret"], r["basket_ret"]) for r in nav_hist
                 if r.get("basket_ret") is not None]
        if len(pairs) >= 2:
            diffs = [p - b for p, b in pairs]
            tracking_error = float(pd.Series(diffs).std())
            corr = float(pd.Series([p for p, _ in pairs])
                         .corr(pd.Series([b for _, b in pairs]))) if len(pairs) > 2 else None
        else:
            tracking_error = corr = None

        buy_gaps = [t["price_gap"] for t in trades if t["side"] == "buy" and t.get("price_gap") is not None]
        sell_gaps = [t["price_gap"] for t in trades if t["side"] == "sell" and t.get("price_gap") is not None]
        total_costs = sum(t["costs"]["total_cost"] for t in trades)
        initial = state["initial_cash"] or 1.0
        return {
            "n_days": len(nav_hist),
            "paper_cum_ret": round(nav_hist[-1]["nav"] / initial - 1.0, 4) if nav_hist else None,
            "basket_cum_ret": round(float(pd.Series(
                [1.0] + [1 + b for _, b in pairs]).prod()) - 1.0, 4) if pairs else None,
            "tracking_error_daily": round(tracking_error, 6) if tracking_error is not None else None,
            "nav_corr": round(corr, 4) if corr is not None else None,
            "attribution": {
                "avg_buy_fill_gap": round(float(pd.Series(buy_gaps).mean()), 5) if buy_gaps else None,
                "avg_sell_fill_gap": round(float(pd.Series(sell_gaps).mean()), 5) if sell_gaps else None,
                "cost_drag_pct": round(total_costs / initial, 5),
                "n_trades": len(trades),
                "n_filled": state["stats"]["filled"],
                "n_expired": state["stats"]["expired"],
            },
            "note": ("对齐基准 = 每日信号篮子 close-close 等权收益（回测同口径）；"
                     "偏差来源：开盘成交 vs 信号收盘的价差、交易成本、停牌/涨跌停未成交（expired）。"),
        }

    def reset(self, initial_cash: float = DEFAULT_INITIAL_CASH,
              top_n: int = DEFAULT_TOP_N) -> Dict[str, Any]:
        with _lock:
            state = self._new_state(initial_cash, top_n)
            self._save(state)
            return {"ok": True, "initial_cash": initial_cash, "top_n": top_n}
