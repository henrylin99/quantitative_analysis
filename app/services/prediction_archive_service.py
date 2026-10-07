"""预测跟踪历史沉淀：每日把 PredictionTrackingService 的结果压缩归档。

每日预警扫描完成后（DailyAlertScheduler 触发）追加一条当日摘要到
data/model_tracking/history.json（保留最近 180 条，同日去重，原子写）：
逐模型各 horizon 的 IC 均值/ICIR、top-N 超额、模型间一致性均值。
由此形成模型质量的时间曲线——单一预测窗口的 IC 看不出衰减趋势，
跨日归档才看得出。

API：GET /ml-factor/predictions/history。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

_DIR_NAME = "model_tracking"
_FILE_NAME = "history.json"
_MAX_RECORDS = 180

_lock = threading.Lock()


class PredictionArchiveService:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir

    @property
    def _file_path(self) -> str:
        return os.path.join(self.data_dir, _DIR_NAME, _FILE_NAME)

    # ------------------------------------------------------------------
    def list_history(self, limit: int = 60) -> List[Dict[str, Any]]:
        try:
            with open(self._file_path, encoding="utf-8") as f:
                return json.load(f).get("records", [])[-limit:]
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"读取预测跟踪历史失败: {e}")
            return []

    def archive_today(self, force: bool = False) -> Dict[str, Any]:
        """跑一轮跟踪并把摘要追加归档；同日已有记录且未 force 时直接返回。"""
        with _lock:
            records = self._read_all()
            today = datetime.now().strftime("%Y-%m-%d")
            if records and not force and records[-1].get("track_date") == today:
                return records[-1]

            from app.services.prediction_tracking import PredictionTrackingService

            report = PredictionTrackingService().track()
            record = {
                "track_date": today,
                "tracked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                **self._compact(report),
            }
            if "error" in record:
                logger.warning(f"预测跟踪归档跳过：{record['error']}")
                return record
            records.append(record)
            records = records[-_MAX_RECORDS:]
            self._write_all(records)
            return record

    # ------------------------------------------------------------------
    @staticmethod
    def _compact(report: Dict[str, Any]) -> Dict[str, Any]:
        if "error" in report:
            return {"error": report["error"]}
        models: Dict[str, Any] = {}
        ic_means: List[float] = []
        for mid, m in (report.get("models") or {}).items():
            if not isinstance(m, dict) or "error" in m:
                models[mid] = {"error": (m or {}).get("error", "无数据")}
                continue
            by_h = {}
            for h, stats_ in (m.get("ic_by_horizon") or {}).items():
                by_h[f"ic_mean_{h}d" if not str(h).endswith("d") else f"ic_mean_{h}"] = stats_.get("ic_mean")
            summary = m.get("summary") or {}
            entry = {
                "base_horizon": summary.get("base_horizon"),
                "n_dates": summary.get("n_dates"),
                "spread_mean": summary.get("spread_mean"),
                "top_excess_mean": summary.get("top_excess_mean"),
            }
            entry.update(by_h)
            models[mid] = entry
            base = summary.get("base_horizon")
            key = f"ic_mean_{base}d" if base else None
            if key and isinstance(entry.get(key), (int, float)):
                ic_means.append(float(entry[key]))
        consistency = report.get("model_consistency") or {}
        series = consistency.get("series") or []
        return {
            "n_models": len(models),
            "models": models,
            "consistency_mean": (
                float(sum(s["mean_corr"] for s in series) / len(series)) if series else None
            ),
            "ic_pool_mean": float(sum(ic_means) / len(ic_means)) if ic_means else None,
            "pred_start": report.get("start_date"),
            "pred_end": report.get("end_date"),
        }

    def _read_all(self) -> List[Dict[str, Any]]:
        try:
            with open(self._file_path, encoding="utf-8") as f:
                return json.load(f).get("records", [])
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"读取预测归档失败: {e}")
            return []

    def _write_all(self, records: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
        tmp = self._file_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"records": records}, f, ensure_ascii=False)
        os.replace(tmp, self._file_path)
