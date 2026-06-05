from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd
from loguru import logger


class ParquetEventStore:
    """Lightweight Parquet-backed append/query store for realtime events."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.base_dir = Path(base_dir) / "realtime_events"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _event_dir(self, event_type: str) -> Path:
        path = self.base_dir / event_type
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _partition_path(self, event_type: str, day: datetime) -> Path:
        return (
            self._event_dir(event_type)
            / f"year={day.year:04d}"
            / f"month={day.month:02d}"
            / f"day={day.day:02d}"
            / "data.parquet"
        )

    def _ensure_frame(self, rows: Iterable[Dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
        if isinstance(rows, pd.DataFrame):
            frame = rows.copy()
        else:
            frame = pd.DataFrame(list(rows))
        if frame.empty:
            return frame
        if "datetime" in frame.columns:
            frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
        if "created_at" in frame.columns:
            frame["created_at"] = pd.to_datetime(frame["created_at"], errors="coerce")
        if "updated_at" in frame.columns:
            frame["updated_at"] = pd.to_datetime(frame["updated_at"], errors="coerce")
        if "expiry_time" in frame.columns:
            frame["expiry_time"] = pd.to_datetime(frame["expiry_time"], errors="coerce")
        if "resolved_at" in frame.columns:
            frame["resolved_at"] = pd.to_datetime(frame["resolved_at"], errors="coerce")
        return frame

    def _read_partition(self, path: Path) -> pd.DataFrame:
        if not path.is_file():
            return pd.DataFrame()
        try:
            return pd.read_parquet(path)
        except Exception as exc:
            logger.warning(f"读取实时事件 parquet 失败 {path}: {exc}")
            return pd.DataFrame()

    def _read_event_frame(self, event_type: str) -> pd.DataFrame:
        root = self._event_dir(event_type)
        paths = sorted(root.glob("year=*/month=*/day=*/data.parquet"))
        if not paths:
            return pd.DataFrame()

        frames = [self._read_partition(path) for path in paths]
        frames = [frame for frame in frames if not frame.empty]
        if not frames:
            return pd.DataFrame()

        frame = pd.concat(frames, ignore_index=True)
        for column in ["datetime", "created_at", "updated_at", "expiry_time", "resolved_at"]:
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column], errors="coerce")
        if "id" in frame.columns:
            frame["id"] = pd.to_numeric(frame["id"], errors="coerce")
        return frame

    def _write_event_frame(self, event_type: str, frame: pd.DataFrame) -> int:
        if frame is None or frame.empty:
            return 0

        frame = frame.copy()
        frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
        frame = frame.dropna(subset=["datetime"])
        if frame.empty:
            return 0

        total_rows = 0
        for date_value, day_frame in frame.groupby(frame["datetime"].dt.date):
            path = self._partition_path(event_type, datetime.combine(date_value, datetime.min.time()))
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file():
                existing = self._read_partition(path)
                combined = pd.concat([existing, day_frame], ignore_index=True)
            else:
                combined = day_frame.copy()

            if "id" in combined.columns:
                combined["id"] = pd.to_numeric(combined["id"], errors="coerce")
                if combined["id"].isna().all():
                    combined = combined.drop(columns=["id"])

            if "id" not in combined.columns:
                existing = self._read_event_frame(event_type)
                next_id = 1
                if not existing.empty and "id" in existing.columns:
                    numeric = pd.to_numeric(existing["id"], errors="coerce").dropna()
                    if not numeric.empty:
                        next_id = int(numeric.max()) + 1
                combined = combined.copy()
                combined["id"] = range(next_id, next_id + len(combined))

            dedupe_cols = [col for col in ["id", "ts_code", "datetime", "period_type", "indicator_name", "strategy_name"] if col in combined.columns]
            if dedupe_cols:
                combined = combined.drop_duplicates(subset=dedupe_cols, keep="last")

            sort_cols = [col for col in ["datetime", "ts_code", "indicator_name", "strategy_name", "id"] if col in combined.columns]
            if sort_cols:
                combined = combined.sort_values(sort_cols).reset_index(drop=True)

            combined.to_parquet(path, index=False)
            total_rows += len(day_frame)
        return total_rows

    def _filter_frame(
        self,
        event_type: str,
        ts_code: Optional[str] = None,
        period_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        frame = self._read_event_frame(event_type)
        if frame.empty:
            return frame

        if "datetime" in frame.columns:
            frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
            frame = frame.dropna(subset=["datetime"])
        if ts_code and "ts_code" in frame.columns:
            frame = frame[frame["ts_code"] == ts_code]
        if period_type and "period_type" in frame.columns:
            frame = frame[frame["period_type"] == period_type]
        if start_time is not None and "datetime" in frame.columns:
            frame = frame[frame["datetime"] >= start_time]
        if end_time is not None and "datetime" in frame.columns:
            frame = frame[frame["datetime"] <= end_time]
        if frame.empty:
            return frame
        sort_cols = [col for col in ["datetime", "ts_code", "indicator_name", "strategy_name", "id"] if col in frame.columns]
        if sort_cols:
            frame = frame.sort_values(sort_cols).reset_index(drop=True)
        return frame

    def append_indicators(self, rows: Iterable[Dict[str, Any]] | pd.DataFrame) -> int:
        frame = self._ensure_frame(rows)
        return self._write_event_frame("indicators", frame)

    def append_signals(self, rows: Iterable[Dict[str, Any]] | pd.DataFrame) -> int:
        frame = self._ensure_frame(rows)
        return self._write_event_frame("signals", frame)

    def get_latest_indicators(
        self,
        ts_code: str,
        period_type: str,
        indicator_names: Optional[Sequence[str]] = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        frame = self._filter_frame("indicators", ts_code=ts_code, period_type=period_type)
        if frame.empty:
            return frame
        if indicator_names and "indicator_name" in frame.columns:
            frame = frame[frame["indicator_name"].isin(set(indicator_names))]
        if frame.empty:
            return frame
        return frame.sort_values("datetime", ascending=False).head(limit).reset_index(drop=True)

    def get_indicator_history(
        self,
        ts_code: str,
        period_type: str,
        indicator_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        frame = self._filter_frame(
            "indicators",
            ts_code=ts_code,
            period_type=period_type,
            start_time=start_time,
            end_time=end_time,
        )
        if frame.empty or "indicator_name" not in frame.columns:
            return frame
        frame = frame[frame["indicator_name"] == indicator_name]
        if frame.empty:
            return frame
        return frame.sort_values("datetime").reset_index(drop=True)

    def get_indicators_by_time_range(
        self,
        ts_code: Optional[str],
        period_type: Optional[str],
        start_time: datetime,
        end_time: datetime,
    ) -> pd.DataFrame:
        return self._filter_frame(
            "indicators",
            ts_code=ts_code,
            period_type=period_type,
            start_time=start_time,
            end_time=end_time,
        )

    def get_indicator_stats(self) -> Dict[str, Any]:
        frame = self._read_event_frame("indicators")
        if frame.empty:
            return {
                "total_records": 0,
                "total_stocks": 0,
                "indicator_stats": {},
                "period_stats": {},
                "earliest_time": None,
                "latest_time": None,
            }

        indicator_stats = {}
        if "indicator_name" in frame.columns:
            indicator_stats = frame["indicator_name"].fillna("UNKNOWN").value_counts().to_dict()
        period_stats = {}
        if "period_type" in frame.columns:
            period_stats = frame["period_type"].fillna("UNKNOWN").value_counts().to_dict()

        earliest = pd.to_datetime(frame["datetime"], errors="coerce").min() if "datetime" in frame.columns else None
        latest = pd.to_datetime(frame["datetime"], errors="coerce").max() if "datetime" in frame.columns else None
        stock_count = int(frame["ts_code"].dropna().astype(str).nunique()) if "ts_code" in frame.columns else 0
        return {
            "total_records": int(len(frame)),
            "total_stocks": stock_count,
            "indicator_stats": {str(key): int(value) for key, value in indicator_stats.items()},
            "period_stats": {str(key): int(value) for key, value in period_stats.items()},
            "earliest_time": earliest.isoformat() if pd.notna(earliest) else None,
            "latest_time": latest.isoformat() if pd.notna(latest) else None,
        }

    def cleanup_old_indicators(self, days_to_keep: int = 30) -> int:
        cutoff = datetime.utcnow() - pd.Timedelta(days=days_to_keep)
        frame = self._read_event_frame("indicators")
        if frame.empty or "datetime" not in frame.columns:
            return 0
        keep = frame[pd.to_datetime(frame["datetime"], errors="coerce") >= cutoff]
        removed = len(frame) - len(keep)
        self._rewrite_event_frame("indicators", keep)
        return removed

    def get_active_signals(
        self,
        ts_code: Optional[str] = None,
        strategy_name: Optional[str] = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        frame = self._read_event_frame("signals")
        if frame.empty:
            return frame
        if "status" in frame.columns:
            frame = frame[frame["status"].fillna("").str.upper() == "ACTIVE"]
        if ts_code and "ts_code" in frame.columns:
            frame = frame[frame["ts_code"] == ts_code]
        if strategy_name and "strategy_name" in frame.columns:
            frame = frame[frame["strategy_name"] == strategy_name]
        if frame.empty:
            return frame
        return frame.sort_values("datetime", ascending=False).head(limit).reset_index(drop=True)

    def get_signals_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        ts_code: Optional[str] = None,
        strategy_name: Optional[str] = None,
    ) -> pd.DataFrame:
        frame = self._filter_frame("signals", ts_code=ts_code, start_time=start_time, end_time=end_time)
        if frame.empty:
            return frame
        if strategy_name and "strategy_name" in frame.columns:
            frame = frame[frame["strategy_name"] == strategy_name]
        if frame.empty:
            return frame
        return frame.sort_values("datetime").reset_index(drop=True)

    def get_recent_signals(
        self,
        since: datetime,
        limit: int = 20,
        status: Optional[str] = "ACTIVE",
    ) -> pd.DataFrame:
        frame = self._filter_frame("signals", start_time=since, end_time=datetime.utcnow())
        if frame.empty:
            return frame
        if status and "status" in frame.columns:
            frame = frame[frame["status"].fillna("").str.upper() == status.upper()]
        if frame.empty:
            return frame
        return frame.sort_values("datetime", ascending=False).head(limit).reset_index(drop=True)

    def get_signal_performance(self, strategy_name: Optional[str] = None, days: int = 30) -> Dict[str, Any]:
        end_time = datetime.utcnow()
        start_time = end_time - pd.Timedelta(days=days)
        frame = self.get_signals_by_time_range(start_time, end_time, strategy_name=strategy_name)
        if frame.empty:
            return {
                "total_signals": 0,
                "executed_signals": 0,
                "win_rate": 0.0,
                "avg_profit_loss": 0.0,
                "total_profit_loss": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0,
            }
        if "status" in frame.columns:
            frame = frame[frame["status"].fillna("").isin(["EXECUTED", "EXPIRED"])]
        if frame.empty:
            return {
                "total_signals": 0,
                "executed_signals": 0,
                "win_rate": 0.0,
                "avg_profit_loss": 0.0,
                "total_profit_loss": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0,
            }

        executed = frame[(frame["status"].fillna("") == "EXECUTED") & frame["profit_loss"].notna()] if "profit_loss" in frame.columns else pd.DataFrame()
        if executed.empty:
            return {
                "total_signals": int(len(frame)),
                "executed_signals": 0,
                "win_rate": 0.0,
                "avg_profit_loss": 0.0,
                "total_profit_loss": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0,
            }
        profit_losses = pd.to_numeric(executed["profit_loss"], errors="coerce").dropna()
        if profit_losses.empty:
            return {
                "total_signals": int(len(frame)),
                "executed_signals": int(len(executed)),
                "win_rate": 0.0,
                "avg_profit_loss": 0.0,
                "total_profit_loss": 0.0,
                "max_profit": 0.0,
                "max_loss": 0.0,
            }
        winning = executed[pd.to_numeric(executed["profit_loss"], errors="coerce") > 0]
        return {
            "total_signals": int(len(frame)),
            "executed_signals": int(len(executed)),
            "win_rate": len(winning) / len(executed) * 100 if len(executed) else 0.0,
            "avg_profit_loss": float(profit_losses.mean()),
            "total_profit_loss": float(profit_losses.sum()),
            "max_profit": float(profit_losses.max()),
            "max_loss": float(profit_losses.min()),
        }

    def get_signal_stats(self) -> Dict[str, Any]:
        frame = self._read_event_frame("signals")
        if frame.empty:
            return {
                "total_signals": 0,
                "total_stocks": 0,
                "status_stats": {},
                "strategy_stats": {},
                "type_stats": {},
                "earliest_time": None,
                "latest_time": None,
            }

        status_stats = frame["status"].fillna("UNKNOWN").value_counts().to_dict() if "status" in frame.columns else {}
        strategy_stats = frame["strategy_name"].fillna("UNKNOWN").value_counts().to_dict() if "strategy_name" in frame.columns else {}
        type_stats = frame["signal_type"].fillna("UNKNOWN").value_counts().to_dict() if "signal_type" in frame.columns else {}
        earliest = pd.to_datetime(frame["datetime"], errors="coerce").min() if "datetime" in frame.columns else None
        latest = pd.to_datetime(frame["datetime"], errors="coerce").max() if "datetime" in frame.columns else None
        stock_count = int(frame["ts_code"].dropna().astype(str).nunique()) if "ts_code" in frame.columns else 0
        return {
            "total_signals": int(len(frame)),
            "total_stocks": stock_count,
            "status_stats": {str(key): int(value) for key, value in status_stats.items()},
            "strategy_stats": {str(key): int(value) for key, value in strategy_stats.items()},
            "type_stats": {str(key): int(value) for key, value in type_stats.items()},
            "earliest_time": earliest.isoformat() if pd.notna(earliest) else None,
            "latest_time": latest.isoformat() if pd.notna(latest) else None,
        }

    def update_signal_status(
        self,
        signal_id: int,
        status: str,
        executed_price: Optional[float] = None,
        profit_loss: Optional[float] = None,
    ) -> bool:
        frame = self._read_event_frame("signals")
        if frame.empty or "id" not in frame.columns:
            return False
        mask = frame["id"] == signal_id
        if not mask.any():
            return False
        now = datetime.utcnow()
        frame.loc[mask, "status"] = status
        frame.loc[mask, "updated_at"] = now
        if executed_price is not None:
            frame.loc[mask, "executed_price"] = executed_price
            frame.loc[mask, "executed_time"] = now
        if profit_loss is not None:
            frame.loc[mask, "profit_loss"] = profit_loss
            if "trigger_price" in frame.columns:
                trigger = pd.to_numeric(frame.loc[mask, "trigger_price"], errors="coerce")
                frame.loc[mask, "profit_loss_pct"] = (profit_loss / trigger) * 100
        self._rewrite_event_frame("signals", frame)
        return True

    def expire_old_signals(self, hours: int = 24) -> int:
        frame = self._read_event_frame("signals")
        if frame.empty or "datetime" not in frame.columns:
            return 0
        cutoff = datetime.utcnow() - pd.Timedelta(hours=hours)
        mask = pd.to_datetime(frame["datetime"], errors="coerce") < cutoff
        if "status" in frame.columns:
            mask = mask & (frame["status"].fillna("") == "ACTIVE")
        expired_count = int(mask.sum())
        if expired_count:
            frame.loc[mask, "status"] = "EXPIRED"
            frame.loc[mask, "updated_at"] = datetime.utcnow()
            self._rewrite_event_frame("signals", frame)
        return expired_count

    def _rewrite_event_frame(self, event_type: str, frame: pd.DataFrame) -> None:
        root = self._event_dir(event_type)
        for path in root.glob("year=*/month=*/day=*/data.parquet"):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        if frame.empty:
            return
        frame = frame.copy()
        frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
        frame = frame.dropna(subset=["datetime"])
        if frame.empty:
            return
        self._write_event_frame(event_type, frame)
