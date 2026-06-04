"""Parquet-backed state repositories for ml-factor business objects.

This module provides a lightweight filesystem-backed persistence layer for the
stateful parts of the ml-factor feature set:

- factor definitions
- factor values
- model definitions
- model predictions
- portfolio positions
- backtest runs

The implementation intentionally keeps the API simple and pandas-friendly so it
can be used as a drop-in replacement for ORM-backed storage during the
migration.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd
from loguru import logger


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _as_iso(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _to_python_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _normalize_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


class ParquetStateStore:
    """Filesystem-backed store for Parquet state tables."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
            base_dir = os.path.join(base_dir, "ml_factor_state")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str) -> Path:
        return self.base_dir / f"{name}.parquet"

    def read_frame(self, name: str) -> pd.DataFrame:
        path = self.path_for(name)
        if not path.is_file():
            return pd.DataFrame()
        try:
            df = pd.read_parquet(path)
            return df
        except Exception as exc:
            logger.warning(f"读取 Parquet 状态表失败 {path}: {exc}")
            return pd.DataFrame()

    def write_frame(self, name: str, df: pd.DataFrame) -> None:
        path = self.path_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = df.copy()
        if not frame.empty:
            frame = frame.reset_index(drop=True)
        frame.to_parquet(path, index=False)

    def next_integer_id(self, name: str, column: str = "id") -> int:
        df = self.read_frame(name)
        if df.empty or column not in df.columns:
            return 1
        numeric = pd.to_numeric(df[column], errors="coerce").dropna()
        if numeric.empty:
            return 1
        return int(numeric.max()) + 1


class FactorRepository:
    TABLE_DEFINITIONS = "factor_definitions"
    TABLE_VALUES = "factor_values"

    def __init__(self, store: ParquetStateStore):
        self.store = store

    def upsert_definition(self, record: Dict[str, Any]) -> Dict[str, Any]:
        df = self.store.read_frame(self.TABLE_DEFINITIONS)
        now = _now_iso()
        record = {
            **record,
            "is_active": bool(record.get("is_active", True)),
            "created_at": _as_iso(record.get("created_at")) or now,
            "updated_at": now,
        }
        if df.empty:
            df = pd.DataFrame([record])
        else:
            if "factor_id" not in df.columns:
                df = pd.DataFrame(columns=list(record.keys()))
            df = df[df["factor_id"] != record["factor_id"]]
            df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        self.store.write_frame(self.TABLE_DEFINITIONS, df)
        return record

    def list_definitions(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE_DEFINITIONS)
        if df.empty:
            return []
        if not include_inactive and "is_active" in df.columns:
            df = df[df["is_active"].fillna(True).astype(bool)]
        if "factor_id" in df.columns:
            df = df.sort_values(["factor_id"]).reset_index(drop=True)
        return [_record_to_dict(row) for _, row in df.iterrows()]

    def get_definition(self, factor_id: str) -> Optional[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE_DEFINITIONS)
        if df.empty or "factor_id" not in df.columns:
            return None
        match = df[df["factor_id"] == factor_id]
        if match.empty:
            return None
        return _record_to_dict(match.iloc[-1])

    def deactivate_definition(self, factor_id: str) -> bool:
        df = self.store.read_frame(self.TABLE_DEFINITIONS)
        if df.empty or "factor_id" not in df.columns:
            return False
        mask = df["factor_id"] == factor_id
        if not mask.any():
            return False
        df.loc[mask, "is_active"] = False
        df.loc[mask, "updated_at"] = _now_iso()
        self.store.write_frame(self.TABLE_DEFINITIONS, df)
        return True

    def save_values(self, frame: pd.DataFrame) -> int:
        if frame is None or frame.empty:
            return 0
        required = {"ts_code", "trade_date", "factor_id", "factor_value"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"factor values missing columns: {sorted(missing)}")

        df = self.store.read_frame(self.TABLE_VALUES)
        if df.empty:
            combined = frame.copy()
        else:
            combined = pd.concat([df, frame], ignore_index=True)
        combined = self._dedupe_values(combined)
        self.store.write_frame(self.TABLE_VALUES, combined)
        return len(frame)

    def get_values(
        self,
        factor_ids: Optional[Sequence[str]] = None,
        trade_date: Optional[str] = None,
        ts_codes: Optional[Sequence[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        df = self.store.read_frame(self.TABLE_VALUES)
        if df.empty:
            return df

        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
            df = df.dropna(subset=["trade_date"])

        start_dt = pd.to_datetime(start_date, errors="coerce") if start_date is not None else None
        end_dt = pd.to_datetime(end_date, errors="coerce") if end_date is not None else None
        trade_dt = pd.to_datetime(trade_date, errors="coerce") if trade_date is not None else None

        if factor_ids is not None:
            df = df[df["factor_id"].isin(set(factor_ids))]
        if trade_dt is not None and "trade_date" in df.columns:
            df = df[df["trade_date"].dt.normalize() == trade_dt.normalize()]
        if ts_codes is not None:
            df = df[df["ts_code"].isin(set(ts_codes))]
        if start_dt is not None and "trade_date" in df.columns:
            df = df[df["trade_date"] >= start_dt]
        if end_dt is not None and "trade_date" in df.columns:
            df = df[df["trade_date"] <= end_dt + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)]

        if df.empty:
            return df

        for column in ["trade_date", "created_at"]:
            if column in df.columns:
                converted = pd.to_datetime(df[column], errors="coerce")
                if converted.notna().any():
                    df[column] = converted
        sort_cols = [c for c in ["trade_date", "ts_code", "factor_id"] if c in df.columns]
        if sort_cols:
            df = df.sort_values(sort_cols).reset_index(drop=True)
        return df

    def _dedupe_values(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        key_cols = [c for c in ["ts_code", "trade_date", "factor_id"] if c in df.columns]
        if not key_cols:
            return df
        for column in ["trade_date", "created_at"]:
            if column in df.columns:
                df[column] = df[column].astype(str)
        df = df.sort_values(key_cols + [c for c in ["created_at"] if c in df.columns]).reset_index(drop=True)
        return df.drop_duplicates(subset=key_cols, keep="last")


class ModelRepository:
    TABLE_DEFINITIONS = "model_definitions"
    TABLE_PREDICTIONS = "ml_predictions"

    def __init__(self, store: ParquetStateStore):
        self.store = store

    def upsert_definition(self, record: Dict[str, Any]) -> Dict[str, Any]:
        df = self.store.read_frame(self.TABLE_DEFINITIONS)
        now = _now_iso()
        record = {
            **record,
            "factor_list": json.dumps(record.get("factor_list", [])),
            "model_params": json.dumps(record.get("model_params", {})),
            "training_config": json.dumps(record.get("training_config", {})),
            "is_active": bool(record.get("is_active", True)),
            "created_at": _as_iso(record.get("created_at")) or now,
            "updated_at": now,
        }
        if df.empty:
            df = pd.DataFrame([record])
        else:
            df = df[df["model_id"] != record["model_id"]]
            df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        self.store.write_frame(self.TABLE_DEFINITIONS, df)
        return record

    def list_definitions(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE_DEFINITIONS)
        if df.empty:
            return []
        if not include_inactive and "is_active" in df.columns:
            df = df[df["is_active"].fillna(True).astype(bool)]
        df = df.sort_values(["model_id"]).reset_index(drop=True)
        return [_record_to_dict(row, json_columns={"factor_list", "model_params", "training_config"}) for _, row in df.iterrows()]

    def get_definition(self, model_id: str) -> Optional[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE_DEFINITIONS)
        if df.empty or "model_id" not in df.columns:
            return None
        match = df[df["model_id"] == model_id]
        if match.empty:
            return None
        return _record_to_dict(match.iloc[-1], json_columns={"factor_list", "model_params", "training_config"})

    def delete_definition(self, model_id: str) -> bool:
        df = self.store.read_frame(self.TABLE_DEFINITIONS)
        if df.empty or "model_id" not in df.columns:
            return False
        mask = df["model_id"] == model_id
        if not mask.any():
            return False
        df.loc[mask, "is_active"] = False
        df.loc[mask, "updated_at"] = _now_iso()
        self.store.write_frame(self.TABLE_DEFINITIONS, df)
        pred_df = self.store.read_frame(self.TABLE_PREDICTIONS)
        if not pred_df.empty and "model_id" in pred_df.columns:
            pred_df = pred_df[pred_df["model_id"] != model_id]
            self.store.write_frame(self.TABLE_PREDICTIONS, pred_df)
        return True

    def save_predictions(self, frame: pd.DataFrame) -> int:
        if frame is None or frame.empty:
            return 0
        required = {"ts_code", "trade_date", "model_id"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"predictions missing columns: {sorted(missing)}")

        df = self.store.read_frame(self.TABLE_PREDICTIONS)
        if df.empty:
            combined = frame.copy()
        else:
            combined = pd.concat([df, frame], ignore_index=True)
        combined = self._dedupe_predictions(combined)
        self.store.write_frame(self.TABLE_PREDICTIONS, combined)
        return len(frame)

    def get_predictions(
        self,
        model_id: Optional[str] = None,
        trade_date: Optional[str] = None,
        ts_codes: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        df = self.store.read_frame(self.TABLE_PREDICTIONS)
        if df.empty:
            return df
        if model_id is not None:
            df = df[df["model_id"] == model_id]
        if trade_date is not None:
            df = df[df["trade_date"].astype(str) == str(trade_date)]
        if ts_codes is not None:
            df = df[df["ts_code"].isin(set(ts_codes))]
        if df.empty:
            return df
        for column in ["trade_date", "created_at"]:
            if column in df.columns:
                df[column] = df[column].astype(str)
        sort_cols = [c for c in ["trade_date", "ts_code", "model_id"] if c in df.columns]
        if sort_cols:
            df = df.sort_values(sort_cols).reset_index(drop=True)
        return df

    def _dedupe_predictions(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        key_cols = [c for c in ["ts_code", "trade_date", "model_id"] if c in df.columns]
        if not key_cols:
            return df
        for column in ["trade_date", "created_at"]:
            if column in df.columns:
                df[column] = df[column].astype(str)
        df = df.sort_values(key_cols + [c for c in ["created_at"] if c in df.columns]).reset_index(drop=True)
        return df.drop_duplicates(subset=key_cols, keep="last")


class PortfolioRepository:
    TABLE_POSITIONS = "portfolio_positions"

    def __init__(self, store: ParquetStateStore):
        self.store = store

    def create_position(self, record: Dict[str, Any]) -> Dict[str, Any]:
        df = self.store.read_frame(self.TABLE_POSITIONS)
        now = _now_iso()
        record = {
            **record,
            "id": int(record.get("id") or self.store.next_integer_id(self.TABLE_POSITIONS)),
            "is_active": bool(record.get("is_active", True)),
            "created_at": _as_iso(record.get("created_at")) or now,
            "updated_at": _as_iso(record.get("updated_at")) or now,
        }
        if df.empty:
            df = pd.DataFrame([record])
        else:
            df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        self.store.write_frame(self.TABLE_POSITIONS, df)
        return record

    def list_positions(self, portfolio_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE_POSITIONS)
        if df.empty or "portfolio_id" not in df.columns:
            return []
        df = df[df["portfolio_id"] == portfolio_id]
        if active_only and "is_active" in df.columns:
            df = df[df["is_active"].fillna(True).astype(bool)]
        if df.empty:
            return []
        sort_cols = [c for c in ["created_at", "id"] if c in df.columns]
        if sort_cols:
            df = df.sort_values(sort_cols).reset_index(drop=True)
        return [_record_to_dict(row) for _, row in df.iterrows()]

    def list_portfolio_ids(self, active_only: bool = True) -> List[str]:
        df = self.store.read_frame(self.TABLE_POSITIONS)
        if df.empty or "portfolio_id" not in df.columns:
            return []
        if active_only and "is_active" in df.columns:
            df = df[df["is_active"].fillna(True).astype(bool)]
        return sorted(df["portfolio_id"].dropna().astype(str).unique().tolist())

    def get_position_by_stock(self, portfolio_id: str, ts_code: str) -> Optional[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE_POSITIONS)
        if df.empty:
            return None
        mask = (df["portfolio_id"] == portfolio_id) & (df["ts_code"] == ts_code)
        if "is_active" in df.columns:
            mask &= df["is_active"].fillna(True).astype(bool)
        match = df[mask]
        if match.empty:
            return None
        return _record_to_dict(match.iloc[-1])

    def deactivate_portfolio(self, portfolio_id: str) -> int:
        df = self.store.read_frame(self.TABLE_POSITIONS)
        if df.empty or "portfolio_id" not in df.columns:
            return 0
        mask = df["portfolio_id"] == portfolio_id
        if "is_active" in df.columns:
            mask &= df["is_active"].fillna(True).astype(bool)
        count = int(mask.sum())
        if count == 0:
            return 0
        df.loc[mask, "is_active"] = False
        df.loc[mask, "updated_at"] = _now_iso()
        self.store.write_frame(self.TABLE_POSITIONS, df)
        return count

    def upsert_position(self, record: Dict[str, Any]) -> Dict[str, Any]:
        df = self.store.read_frame(self.TABLE_POSITIONS)
        now = _now_iso()
        record = {
            **record,
            "id": int(record.get("id") or self.store.next_integer_id(self.TABLE_POSITIONS)),
            "is_active": bool(record.get("is_active", True)),
            "created_at": _as_iso(record.get("created_at")) or now,
            "updated_at": _as_iso(record.get("updated_at")) or now,
        }
        if df.empty:
            df = pd.DataFrame([record])
        else:
            if "id" in df.columns:
                df = df[df["id"] != record["id"]]
            df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        self.store.write_frame(self.TABLE_POSITIONS, df)
        return record

    def calculate_metrics(self, portfolio_id: str) -> Dict[str, Any]:
        positions = self.list_positions(portfolio_id, active_only=True)
        if not positions:
            return {}
        total_market_value = sum(float(pos.get("market_value") or 0) for pos in positions)
        total_unrealized_pnl = sum(float(pos.get("unrealized_pnl") or 0) for pos in positions)
        enriched = []
        sector_distribution: Dict[str, float] = {}
        for pos in positions:
            weight = float(pos.get("weight") or 0)
            if total_market_value > 0:
                weight = float(pos.get("market_value") or 0) / total_market_value * 100
            sector = pos.get("sector") or "未知"
            sector_distribution[sector] = sector_distribution.get(sector, 0) + weight
            enriched.append({**pos, "weight": weight})
        portfolio_var_1d = sum(float(pos.get("var_1d") or 0) * (float(pos.get("weight") or 0) / 100) for pos in enriched)
        portfolio_var_5d = sum(float(pos.get("var_5d") or 0) * (float(pos.get("weight") or 0) / 100) for pos in enriched)
        return {
            "total_positions": len(enriched),
            "total_market_value": total_market_value,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_pnl_percentage": (total_unrealized_pnl / (total_market_value - total_unrealized_pnl) * 100) if total_market_value > total_unrealized_pnl else 0,
            "sector_distribution": sector_distribution,
            "portfolio_var_1d": portfolio_var_1d,
            "portfolio_var_5d": portfolio_var_5d,
            "max_position_weight": max((float(pos.get("weight") or 0) for pos in enriched), default=0),
            "positions": enriched,
        }


class BacktestRepository:
    TABLE_RUNS = "backtest_runs"

    def __init__(self, store: ParquetStateStore):
        self.store = store

    def create_run(
        self,
        strategy_config: Dict[str, Any],
        start_date: str,
        end_date: str,
        initial_capital: float,
        rebalance_frequency: str,
    ) -> Dict[str, Any]:
        df = self.store.read_frame(self.TABLE_RUNS)
        run_id = int(self.store.next_integer_id(self.TABLE_RUNS))
        record = {
            "id": run_id,
            "strategy_config_json": json.dumps(strategy_config or {}),
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": float(initial_capital),
            "rebalance_frequency": rebalance_frequency,
            "summary_json": None,
            "created_at": _now_iso(),
        }
        if df.empty:
            df = pd.DataFrame([record])
        else:
            df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        self.store.write_frame(self.TABLE_RUNS, df)
        return {
            "id": run_id,
            "strategy_config": strategy_config or {},
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": float(initial_capital),
            "rebalance_frequency": rebalance_frequency,
            "summary": {},
            "created_at": record["created_at"],
        }

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE_RUNS)
        if df.empty or "id" not in df.columns:
            return None
        match = df[pd.to_numeric(df["id"], errors="coerce") == int(run_id)]
        if match.empty:
            return None
        row = match.iloc[-1]
        return {
            "id": int(_to_python_scalar(row["id"])),
            "strategy_config": _normalize_json(row.get("strategy_config_json")) or {},
            "start_date": _to_python_scalar(row.get("start_date")),
            "end_date": _to_python_scalar(row.get("end_date")),
            "initial_capital": float(_to_python_scalar(row.get("initial_capital")) or 0),
            "rebalance_frequency": _to_python_scalar(row.get("rebalance_frequency")),
            "summary": _normalize_json(row.get("summary_json")) or {},
            "created_at": _as_iso(row.get("created_at")),
        }

    def update_summary(self, run_id: int, summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE_RUNS)
        if df.empty or "id" not in df.columns:
            return None
        mask = pd.to_numeric(df["id"], errors="coerce") == int(run_id)
        if not mask.any():
            return None
        df.loc[mask, "summary_json"] = json.dumps(summary or {})
        self.store.write_frame(self.TABLE_RUNS, df)
        return self.get_run(run_id)

    def list_runs(self) -> List[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE_RUNS)
        if df.empty:
            return []
        df = df.sort_values(["created_at", "id"]).reset_index(drop=True)
        return [
            {
                "id": int(_to_python_scalar(row["id"])),
                "strategy_config": _normalize_json(row.get("strategy_config_json")) or {},
                "start_date": _to_python_scalar(row.get("start_date")),
                "end_date": _to_python_scalar(row.get("end_date")),
                "initial_capital": float(_to_python_scalar(row.get("initial_capital")) or 0),
                "rebalance_frequency": _to_python_scalar(row.get("rebalance_frequency")),
                "summary": _normalize_json(row.get("summary_json")) or {},
                "created_at": _as_iso(row.get("created_at")),
            }
            for _, row in df.iterrows()
        ]


def _record_to_dict(row: Any, json_columns: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    json_columns = set(json_columns or [])
    if isinstance(row, pd.Series):
        data = row.to_dict()
    else:
        data = dict(row)

    result: Dict[str, Any] = {}
    for key, value in data.items():
        if key in json_columns:
            result[key] = _normalize_json(value)
            continue
        if key in {"created_at", "updated_at", "trade_date"}:
            result[key] = _as_iso(value)
            continue
        result[key] = _to_python_scalar(value)
    return result
