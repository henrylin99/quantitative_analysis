"""每日收盘后定时扫描 + 预警记录。

每天收盘后（默认 18:30，可用 DAILY_ALERT_TIME 覆盖）在后台线程跑一轮：
- 筹码三类信号扫描（ChipSignalService）
- 指数 regime（MarketRegimeService）
- 行业轮动评分 top/bottom（IndustryRotationService）
- 财务异动概要（FinancialQualityService.anomaly_scan，仅统计）

与上一次记录对比生成预警（regime 翻转 / 新增信号 / 轮动榜首变化），
连同当日快照追加写入 data/alerts/daily_alerts.json（保留最近 90 条，
原子写）。同一扫描日期不重复写（可用 force 覆盖）。

API：GET /api/trial/daily-alerts（?refresh=1 立即扫描一次）。
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

_ALERTS_DIR_NAME = "alerts"
_ALERTS_FILE_NAME = "daily_alerts.json"
_MAX_RECORDS = 90
_DEFAULT_SCAN_TIME = "18:30"
_SIGNAL_KEYS = ("squeeze", "resonance", "divergence")

_lock = threading.Lock()


class DailyAlertService:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir

    # ------------------------------------------------------------------
    # 存储
    # ------------------------------------------------------------------
    @property
    def _file_path(self) -> str:
        return os.path.join(self.data_dir, _ALERTS_DIR_NAME, _ALERTS_FILE_NAME)

    def list_records(self, limit: int = 30) -> List[Dict[str, Any]]:
        records = self._read_all()
        return records[-limit:]

    def _read_all(self) -> List[Dict[str, Any]]:
        try:
            with open(self._file_path, encoding="utf-8") as f:
                payload = json.load(f)
            return payload.get("records", [])
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"读取预警记录失败: {e}")
            return []

    def _append(self, record: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        records = [r for r in self._read_all() if r.get("scan_date") != record["scan_date"]]
        records.append(record)
        records = records[-_MAX_RECORDS:]
        tmp = self._file_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"records": records}, f, ensure_ascii=False)
        os.replace(tmp, self._file_path)

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------
    def run_scan(self, force: bool = False) -> Dict[str, Any]:
        """跑一轮扫描并落盘；同日已有记录且未 force 时直接返回已有记录。"""
        with _lock:
            records = self._read_all()
            if records and not force and records[-1].get("scan_date") == datetime.now().strftime("%Y-%m-%d"):
                return records[-1]

            snapshot = self._collect()
            record = {
                "scan_date": datetime.now().strftime("%Y-%m-%d"),
                "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                **snapshot,
            }
            prev = None
            for r in reversed(records):
                if r.get("scan_date") != record["scan_date"]:
                    prev = r
                    break
            record["alerts"] = self._derive_alerts(record, prev)
            self._append(record)
            return record

    def _collect(self) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {"regime": None, "signals": None,
                                    "rotation": None, "anomaly": None}
        from app.services.chip_signal_service import ChipSignalService
        from app.services.market_regime_service import MarketRegimeService

        try:
            sig = ChipSignalService().scan()
            snapshot["signals"] = None if "error" in sig else {
                "stats": sig.get("stats"),
                "codes": {k: [row["ts_code"] for row in sig.get(k, [])]
                          for k in _SIGNAL_KEYS},
            }
        except Exception as e:
            logger.warning(f"每日扫描-筹码信号失败: {e}")

        try:
            regime = MarketRegimeService().regime()
            indexes = regime.get("indexes", []) if isinstance(regime, dict) else []
            snapshot["regime"] = [
                {"code": r["code"], "name": r["name"], "regime": r["regime"]}
                for r in indexes
            ] or None
        except Exception as e:
            logger.warning(f"每日扫描-regime 失败: {e}")

        try:
            from app.services.industry_rotation_service import IndustryRotationService

            rot = IndustryRotationService().run(months=12)
            if "error" not in rot:
                rows = rot.get("rows", [])
                snapshot["rotation"] = {
                    "top": [{"industry": r["industry"], "total_score": r["total_score"]}
                            for r in rows[:3]],
                    "bottom": [{"industry": r["industry"], "total_score": r["total_score"]}
                               for r in rows[-3:]],
                }
        except Exception as e:
            logger.warning(f"每日扫描-行业轮动失败: {e}")

        try:
            from app.services.financial_quality_service import FinancialQualityService

            anomaly = FinancialQualityService().anomaly_scan()
            if "error" not in anomaly:
                snapshot["anomaly"] = {
                    "report_year": anomaly.get("report_year"),
                    "total_flagged": anomaly.get("total_flagged"),
                }
        except Exception as e:
            logger.warning(f"每日扫描-财务异动失败: {e}")

        return snapshot

    # ------------------------------------------------------------------
    @staticmethod
    def _derive_alerts(record: Dict[str, Any], prev: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        if prev is None:
            alerts.append({"type": "init", "level": "info",
                           "message": "首次扫描，建立基线（不生成对比预警）"})
            return alerts

        # regime 翻转
        prev_regime = {r["code"]: r["regime"] for r in (prev.get("regime") or [])}
        for r in record.get("regime") or []:
            old = prev_regime.get(r["code"])
            if old and old != r["regime"]:
                alerts.append({
                    "type": "regime_flip", "level": "warn",
                    "message": f"{r['name']}：{old} → {r['regime']}",
                })

        # 新增信号
        prev_codes = (prev.get("signals") or {}).get("codes", {})
        cur_codes = (record.get("signals") or {}).get("codes", {})
        labels = {"squeeze": "挤压蓄势", "resonance": "多头共振", "divergence": "背离预警"}
        for key in _SIGNAL_KEYS:
            new = sorted(set(cur_codes.get(key, [])) - set(prev_codes.get(key, [])))
            if new:
                alerts.append({
                    "type": f"new_{key}", "level": "info",
                    "message": f"{labels[key]}新增 {len(new)} 只：{'、'.join(new[:8])}"
                               + ("…" if len(new) > 8 else ""),
                })

        # 轮动榜首变化
        prev_top = ((prev.get("rotation") or {}).get("top") or [{}])[0].get("industry")
        cur_top = ((record.get("rotation") or {}).get("top") or [{}])[0].get("industry")
        if prev_top and cur_top and prev_top != cur_top:
            alerts.append({"type": "rotation_top", "level": "info",
                           "message": f"行业轮动榜首变化：{prev_top} → {cur_top}"})

        # 财务异动覆盖变化（年报换届时）
        prev_an = prev.get("anomaly") or {}
        cur_an = record.get("anomaly") or {}
        if cur_an and prev_an and cur_an.get("report_year") != prev_an.get("report_year"):
            alerts.append({
                "type": "anomaly_year", "level": "warn",
                "message": f"财务异动报告期切换：{prev_an.get('report_year')} → {cur_an.get('report_year')}"
                           f"（命中 {cur_an.get('total_flagged')} 只）",
            })

        if not alerts:
            alerts.append({"type": "none", "level": "info", "message": "无变化"})
        return alerts


class DailyAlertScheduler:
    """进程内后台线程：每天 DAILY_ALERT_TIME（默认 18:30）跑一次扫描。"""

    _instance: Optional["DailyAlertScheduler"] = None
    _instance_lock = threading.Lock()

    def __init__(self):
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @classmethod
    def instance(cls) -> "DailyAlertScheduler":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="daily-alert-scheduler",
                                        daemon=True)
        self._thread.start()
        logger.info("每日预警调度线程已启动")

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                wait = self._seconds_until_next_run()
            except Exception:
                wait = 600.0
            if self._stop.wait(wait):
                return
            try:
                record = DailyAlertService().run_scan()
                logger.info(f"每日预警扫描完成 {record['scan_date']}："
                            f"{len(record.get('alerts', []))} 条预警")
            except Exception:
                logger.error("每日预警扫描失败", exc_info=True)

    @staticmethod
    def _seconds_until_next_run() -> float:
        raw = os.getenv("DAILY_ALERT_TIME", _DEFAULT_SCAN_TIME)
        hour, minute = (int(x) for x in raw.split(":")[:2])
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return max(60.0, (target - now).total_seconds())
