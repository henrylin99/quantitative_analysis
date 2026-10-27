"""策略守护（Guardian）：已上线策略每日自动复验，三态生命周期 健康/观察/退役。

借鉴开源社区 strategy guardian 的思路：参数写回单一源、策略上线之后
没有人再回头检验，是最常见的复利陷阱。本服务在 18:30 盘后链里对登记的
策略用近期窗口重算同一口径的超额收益，按状态机迁移：

    healthy --近期超额 ≤ watch 线--> watch
    watch   --近期超额 > watch 线--> healthy（watch_days 清零）
    watch   --近期超额 ≤ retire 线 或 连续 max_watch_days 天--> retired（粘性，不自动复活）
    retired --仅人工 resume--> watch

评估口径与 SignalOptimizerService 完全一致（单点网格的近期窗口全样本超额），
避免守护链路自己再造第三套口径。状态变化推送预警并落 history.jsonl。
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

STATUS_HEALTHY = "healthy"
STATUS_WATCH = "watch"
STATUS_RETIRED = "retired"

_KINDS = ("chip_signal", "rotation")


def _data_dir() -> str:
    return os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
    )


def _strategies_path() -> str:
    return os.path.join(_data_dir(), "strategy_guardian", "strategies.json")


def _history_path() -> str:
    return os.path.join(_data_dir(), "strategy_guardian", "history.jsonl")


class StrategyGuardianService:
    def __init__(self, optimizer=None):
        # optimizer 可注入（测试）；默认懒加载 SignalOptimizerService
        self._optimizer = optimizer

    # ------------------------------------------------------------------
    # 登记表
    # ------------------------------------------------------------------
    def _load(self) -> Dict[str, Any]:
        try:
            with open(_strategies_path(), encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict) and isinstance(payload.get("strategies"), list):
                return payload
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"策略守护登记表解析失败，视为空表: {e}")
        return {"strategies": []}

    def _save(self, payload: Dict[str, Any]) -> None:
        path = _strategies_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def list_strategies(self) -> List[Dict[str, Any]]:
        return self._load()["strategies"]

    def register(self, name: str, kind: str,
                 params: Optional[Dict[str, Any]] = None,
                 horizon: int = 10, months_eval: int = 6,
                 watch_excess: float = 0.0, retire_excess: float = -0.05,
                 max_watch_days: int = 10,
                 signal: str = "resonance", top_n: int = 5,
                 rebalance_days: int = 20) -> Dict[str, Any]:
        kind = str(kind or "").lower()
        if kind not in _KINDS:
            return {"error": f"kind 必须是 {'/'.join(_KINDS)}"}
        payload = self._load()
        sid = f"{kind}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        record = {
            "id": sid,
            "name": str(name or sid),
            "kind": kind,
            "params": dict(params or {}),
            "signal": str(signal or "resonance").lower(),
            "horizon": max(1, int(horizon)),
            "top_n": max(1, int(top_n)),
            "rebalance_days": max(5, int(rebalance_days)),
            "months_eval": max(3, min(int(months_eval), 24)),
            "watch_excess": float(watch_excess),
            "retire_excess": float(retire_excess),
            "max_watch_days": max(1, int(max_watch_days)),
            "status": STATUS_HEALTHY,
            "watch_days": 0,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "last_eval": None,
            "last_excess": None,
            "baseline_excess": None,
        }
        payload["strategies"].append(record)
        self._save(payload)
        return record

    def remove(self, strategy_id: str) -> Dict[str, Any]:
        payload = self._load()
        before = len(payload["strategies"])
        payload["strategies"] = [s for s in payload["strategies"] if s["id"] != strategy_id]
        if len(payload["strategies"]) == before:
            return {"error": f"未找到策略 {strategy_id}"}
        self._save(payload)
        return {"removed": strategy_id}

    def resume(self, strategy_id: str) -> Dict[str, Any]:
        """退役策略人工复活 → watch（先观察，不直接回 healthy）。"""
        payload = self._load()
        for s in payload["strategies"]:
            if s["id"] == strategy_id:
                if s.get("status") != STATUS_RETIRED:
                    return {"error": "仅退役策略需要 resume"}
                s["status"] = STATUS_WATCH
                s["watch_days"] = 0
                self._save(payload)
                return s
        return {"error": f"未找到策略 {strategy_id}"}

    # ------------------------------------------------------------------
    # 评估：复用寻优器单点网格，口径与寻优完全一致
    # ------------------------------------------------------------------
    def _evaluate(self, s: Dict[str, Any]) -> Optional[float]:
        """近期 months_eval 个月窗口、登记参数下的链式超额（None=无法评估）。"""
        if self._optimizer is None:
            from app.services.signal_optimizer_service import SignalOptimizerService
            self._optimizer = SignalOptimizerService()
        params = s.get("params") or {}
        grid = {k: [v] for k, v in params.items()}
        if not grid:
            return None
        if s["kind"] == "chip_signal":
            result = self._optimizer.chip_threshold_optimize(
                months=s["months_eval"], signal=s.get("signal", "resonance"),
                horizon=s.get("horizon", 10), grid=grid)
        else:
            result = self._optimizer.rotation_weight_optimize(
                months=s["months_eval"], top_n=s.get("top_n", 5),
                rebalance_days=s.get("rebalance_days", 20), grid=grid)
        if not isinstance(result, dict) or "error" in result:
            logger.warning(f"守护评估失败 {s['id']}: {result.get('error') if isinstance(result, dict) else result}")
            return None
        rows = result.get("grid_results") or []
        return rows[0].get("excess") if rows else None

    @staticmethod
    def _transition(s: Dict[str, Any], excess: float) -> str:
        """状态迁移（retired 粘性，不在此复活）。"""
        status = s.get("status", STATUS_HEALTHY)
        watch_line = float(s.get("watch_excess", 0.0))
        retire_line = float(s.get("retire_excess", -0.05))
        if status == STATUS_RETIRED:
            return STATUS_RETIRED
        if excess <= retire_line:
            return STATUS_RETIRED
        if excess <= watch_line:
            return STATUS_WATCH
        return STATUS_HEALTHY

    # ------------------------------------------------------------------
    # 每日复验
    # ------------------------------------------------------------------
    def run_daily(self, push: bool = True) -> Dict[str, Any]:
        payload = self._load()
        strategies = payload["strategies"]
        results: List[Dict[str, Any]] = []
        today = datetime.now().strftime("%Y-%m-%d")
        changed: List[Dict[str, Any]] = []
        for s in strategies:
            excess = self._evaluate(s)
            if excess is None:
                results.append({"id": s["id"], "name": s["name"], "excess": None,
                                "status": s["status"], "note": "评估失败，状态不变"})
                continue
            prev_status = s.get("status", STATUS_HEALTHY)
            new_status = self._transition(s, excess)
            if new_status == STATUS_WATCH:
                # 每个观察日计 1，连续 max_watch_days 天未回 healthy → 退役
                s["watch_days"] = int(s.get("watch_days", 0)) + 1
                if s["watch_days"] >= int(s.get("max_watch_days", 10)):
                    new_status = STATUS_RETIRED
            elif new_status == STATUS_HEALTHY:
                s["watch_days"] = 0
            # retired：直接退役，watch_days 留档
            s["status"] = new_status
            s["last_eval"] = today
            s["last_excess"] = excess
            if s.get("baseline_excess") is None:
                s["baseline_excess"] = excess  # 首次评估即基线
            row = {"id": s["id"], "name": s["name"], "excess": excess,
                   "status": new_status, "prev_status": prev_status,
                   "watch_days": s.get("watch_days", 0)}
            results.append(row)
            self._append_history({**row, "date": today})
            if new_status != prev_status:
                changed.append(row)

        self._save(payload)
        if push and changed:
            self._push_changes(changed)
        return {"date": today, "n_strategies": len(strategies),
                "results": results, "status_changes": changed}

    @staticmethod
    def _append_history(row: Dict[str, Any]) -> None:
        path = _history_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def history(self, strategy_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        try:
            with open(_history_path(), encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            return []
        if strategy_id:
            rows = [r for r in rows if r.get("id") == strategy_id]
        return rows[-max(1, int(limit)):]

    @staticmethod
    def _push_changes(changed: List[Dict[str, Any]]) -> None:
        try:
            from app.services.alert_push_service import AlertPushService
            lines = []
            for c in changed:
                arrow = f"{c['prev_status']}→{c['status']}"
                lines.append(f"[{c['name']}] {arrow}，近窗超额 {c['excess']:+.2%}")
            AlertPushService().push_text(
                "策略守护状态变化",
                "\n".join(lines),
            )
        except Exception as e:
            logger.warning(f"策略守护推送失败（状态已落盘，不影响守护）: {e}")


_guardian_lock = threading.Lock()
_last_run_date: Optional[str] = None


def run_daily_guardian(push: bool = True) -> Dict[str, Any]:
    """18:30 链入口：无登记策略时直接跳过；同进程同日幂等，周末不评估。"""
    global _last_run_date
    if os.getenv("STRATEGY_GUARDIAN_ENABLED", "1").strip().lower() in ("0", "false", "no"):
        return {"skipped": "disabled"}
    if datetime.now().weekday() >= 5:
        return {"skipped": "weekend"}
    with _guardian_lock:
        today = datetime.now().strftime("%Y-%m-%d")
        if _last_run_date == today:
            return {"skipped": "already_run_today"}
        svc = StrategyGuardianService()
        if not svc.list_strategies():
            return {"skipped": "no_registered_strategies"}
        result = svc.run_daily(push=push)
        if "error" not in result:
            _last_run_date = today
        return result
