from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

import pandas as pd

from app.services.parquet_state_store import ParquetStateStore


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _to_python(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _normalize_json_payload(value: Any) -> Any:
    value = _to_python(value)
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _json_text(value: Any) -> str:
    normalized = _normalize_json_payload(value)
    if normalized is None:
        normalized = {}
    if isinstance(normalized, str):
        return normalized
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)


@dataclass
class DataJobRunRecord:
    id: int
    job_type: str
    status: str
    progress: float
    progress_message: Optional[str]
    params_json: Dict[str, Any]
    source_name: Optional[str]
    source_mode: Optional[str]
    snapshot_tag: Optional[str]
    result_json: Optional[Dict[str, Any]]
    error_message: Optional[str]
    log_text: Optional[str]
    queued_at: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "params_json": self.params_json or {},
            "source_name": self.source_name,
            "source_mode": self.source_mode,
            "snapshot_tag": self.snapshot_tag,
            "result_json": self.result_json,
            "error_message": self.error_message,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class DataJobCursorRecord:
    def __init__(self, job_type: str, cursor_key: str, cursor_value: str, updated_at: Optional[str] = None):
        self.job_type = job_type
        self.cursor_key = cursor_key
        self.cursor_value = cursor_value
        self.updated_at = updated_at or _now_iso()


class ParquetDataJobStateStore:
    TABLE_RUNS = "data_job_runs"
    TABLE_CURSORS = "data_job_cursors"

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                str(Path(__file__).resolve().parents[3] / "data"),
            )
            base_dir = os.path.join(data_dir, "data_job_state")
        self.store = ParquetStateStore(base_dir=base_dir)
        self._migrate_previous_state_if_needed()
        self._normalize_state_files()

    def create_run(
        self,
        job_type: str,
        params: Dict[str, Any],
        source_name: Optional[str] = None,
        source_mode: Optional[str] = None,
        snapshot_tag: Optional[str] = None,
        progress_message: Optional[str] = None,
    ) -> DataJobRunRecord:
        df = self.store.read_frame(self.TABLE_RUNS)
        now = _now_iso()
        run_id = int(self.store.next_integer_id(self.TABLE_RUNS))
        record = {
            "id": run_id,
            "job_type": job_type,
            "status": "pending",
            "progress": 0.0,
            "progress_message": progress_message,
            "params_json": _json_text(params or {}),
            "source_name": source_name,
            "source_mode": source_mode,
            "snapshot_tag": snapshot_tag,
            "result_json": None,
            "error_message": None,
            "log_text": None,
            "queued_at": now,
            "started_at": None,
            "finished_at": None,
            "created_at": now,
            "updated_at": now,
        }
        df = pd.concat([df, pd.DataFrame([record])], ignore_index=True) if not df.empty else pd.DataFrame([record])
        self.store.write_frame(self.TABLE_RUNS, df)
        return self._row_to_record(pd.Series(record))

    def find_active_duplicate(self, job_type: str, params: Dict[str, Any]) -> Optional[DataJobRunRecord]:
        runs = self.list_runs(limit=1000)
        active_status = {"pending", "queued", "running"}
        for run in reversed(runs):
            if run.job_type == job_type and run.status in active_status and (run.params_json or {}) == (params or {}):
                return run
        return None

    def get_run(self, run_id: int) -> Optional[DataJobRunRecord]:
        df = self.store.read_frame(self.TABLE_RUNS)
        if df.empty or "id" not in df.columns:
            return None
        match = df[pd.to_numeric(df["id"], errors="coerce") == int(run_id)]
        if match.empty:
            return None
        return self._row_to_record(match.iloc[-1])

    def list_runs(self, limit: int = 50, status: Optional[str] = None) -> List[DataJobRunRecord]:
        df = self.store.read_frame(self.TABLE_RUNS)
        if df.empty:
            return []
        if status and "status" in df.columns:
            df = df[df["status"] == status]
        if "id" in df.columns:
            df = df.sort_values("id", ascending=False)
        if limit:
            df = df.head(limit)
        return [self._row_to_record(row) for _, row in df.iterrows()]

    def update_run_status(
        self,
        run: DataJobRunRecord,
        status: str,
        progress: Optional[float] = None,
        error_message: Optional[str] = None,
        progress_message: Optional[str] = None,
    ) -> DataJobRunRecord:
        df = self.store.read_frame(self.TABLE_RUNS)
        if df.empty or "id" not in df.columns:
            return run
        mask = pd.to_numeric(df["id"], errors="coerce") == int(run.id)
        if not mask.any():
            return run
        now = _now_iso()
        df.loc[mask, "status"] = status
        if progress is not None:
            df.loc[mask, "progress"] = float(progress)
            run.progress = float(progress)
        if error_message is not None:
            df.loc[mask, "error_message"] = error_message
            run.error_message = error_message
        if progress_message is not None:
            df.loc[mask, "progress_message"] = progress_message
            run.progress_message = progress_message
        if status == "running" and not run.started_at:
            df.loc[mask, "started_at"] = now
            run.started_at = now
        if status in {"success", "failed", "cancelled"}:
            df.loc[mask, "finished_at"] = now
            run.finished_at = now
        df.loc[mask, "updated_at"] = now
        run.status = status
        run.updated_at = now
        self.store.write_frame(self.TABLE_RUNS, df)
        return self.get_run(run.id) or run

    def save_run(self, run: DataJobRunRecord) -> DataJobRunRecord:
        df = self.store.read_frame(self.TABLE_RUNS)
        if df.empty or "id" not in df.columns:
            return run
        mask = pd.to_numeric(df["id"], errors="coerce") == int(run.id)
        if not mask.any():
            return run
        payload = run.to_dict()
        payload["updated_at"] = _now_iso()
        payload["params_json"] = _json_text(payload.get("params_json"))
        if payload.get("result_json") is not None:
            payload["result_json"] = _json_text(payload.get("result_json"))
        for key, value in payload.items():
            df.loc[mask, key] = [value]
        self.store.write_frame(self.TABLE_RUNS, df)
        return self.get_run(run.id) or run

    def upsert_cursor(self, job_type: str, cursor_key: str, cursor_value: str) -> DataJobCursorRecord:
        df = self.store.read_frame(self.TABLE_CURSORS)
        now = _now_iso()
        record = {
            "job_type": job_type,
            "cursor_key": cursor_key,
            "cursor_value": cursor_value,
            "updated_at": now,
        }
        if df.empty:
            df = pd.DataFrame([record])
        else:
            mask = (df["job_type"] == job_type) & (df["cursor_key"] == cursor_key)
            df = df[~mask]
            df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        self.store.write_frame(self.TABLE_CURSORS, df)
        return DataJobCursorRecord(**record)

    def _row_to_record(self, row: pd.Series) -> DataJobRunRecord:
        params = _to_python(row.get("params_json")) or {}
        result_json = _to_python(row.get("result_json"))
        params = _normalize_json_payload(params) or {}
        result_json = _normalize_json_payload(result_json)
        if isinstance(result_json, str):
            result_json = {"raw": result_json}
        return DataJobRunRecord(
            id=int(_to_python(row.get("id")) or 0),
            job_type=str(_to_python(row.get("job_type")) or ""),
            status=str(_to_python(row.get("status")) or "pending"),
            progress=float(_to_python(row.get("progress")) or 0.0),
            progress_message=_to_python(row.get("progress_message")),
            params_json=params,
            source_name=_to_python(row.get("source_name")),
            source_mode=_to_python(row.get("source_mode")),
            snapshot_tag=_to_python(row.get("snapshot_tag")),
            result_json=result_json,
            error_message=_to_python(row.get("error_message")),
            log_text=_to_python(row.get("log_text")),
            queued_at=_to_python(row.get("queued_at")),
            started_at=_to_python(row.get("started_at")),
            finished_at=_to_python(row.get("finished_at")),
            created_at=_to_python(row.get("created_at")),
            updated_at=_to_python(row.get("updated_at")),
        )

    def _migrate_previous_state_if_needed(self) -> None:
        current_runs = self.store.path_for(self.TABLE_RUNS)
        current_cursors = self.store.path_for(self.TABLE_CURSORS)
        current_dir = self.store.base_dir
        previous_dir = current_dir.parent / "ml_factor_state"

        if previous_dir == current_dir:
            return

        migrations = [
            (previous_dir / f"{self.TABLE_RUNS}.parquet", current_runs),
            (previous_dir / f"{self.TABLE_CURSORS}.parquet", current_cursors),
        ]
        for previous_path, current_path in migrations:
            if current_path.exists() or not previous_path.exists():
                continue
            current_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(previous_path), str(current_path))

    def _normalize_state_files(self) -> None:
        self._normalize_runs_file()
        self._normalize_cursors_file()

    def _normalize_runs_file(self) -> None:
        path = self.store.path_for(self.TABLE_RUNS)
        if not path.exists():
            return
        df = self.store.read_frame(self.TABLE_RUNS)
        if df.empty:
            return

        normalized = df.copy()
        if "params_json" in normalized.columns:
            normalized["params_json"] = normalized["params_json"].apply(_json_text)
        if "result_json" in normalized.columns:
            normalized["result_json"] = normalized["result_json"].apply(
                lambda value: None if _normalize_json_payload(value) is None else _json_text(value)
            )
        if "__params_key" in normalized.columns:
            normalized = normalized.drop(columns=["__params_key"])

        if normalized.equals(df):
            return
        self.store.write_frame(self.TABLE_RUNS, normalized)

    def _normalize_cursors_file(self) -> None:
        path = self.store.path_for(self.TABLE_CURSORS)
        if not path.exists():
            return
        df = self.store.read_frame(self.TABLE_CURSORS)
        if df.empty:
            return
        if df.equals(df.copy()):
            return

    def prune_superseded_failures(self) -> int:
        df = self.store.read_frame(self.TABLE_RUNS)
        if df.empty or "id" not in df.columns or "job_type" not in df.columns:
            return 0

        work_df = df.copy()
        work_df["id"] = pd.to_numeric(work_df["id"], errors="coerce")
        if "status" not in work_df.columns:
            return 0
        if "params_json" in work_df.columns:
            work_df["__params_key"] = work_df["params_json"].apply(
                lambda value: json.dumps(_normalize_json_payload(value) or {}, ensure_ascii=True, sort_keys=True)
            )
        else:
            work_df["__params_key"] = "{}"

        drop_ids: list[int] = []
        success_groups = work_df[work_df["status"] == "success"].groupby(["job_type", "__params_key"], dropna=False)
        for (job_type, params_key), group in success_groups:
            latest_success_id = group["id"].max()
            failed_mask = (
                (work_df["job_type"] == job_type)
                & (work_df["status"] == "failed")
                & (work_df["__params_key"] == params_key)
                & (work_df["id"] < latest_success_id)
            )
            drop_ids.extend(work_df.loc[failed_mask, "id"].dropna().astype(int).tolist())

        if not drop_ids:
            return 0

        filtered = work_df[~work_df["id"].isin(set(drop_ids))].reset_index(drop=True)
        self.store.write_frame(self.TABLE_RUNS, filtered)
        return len(drop_ids)
