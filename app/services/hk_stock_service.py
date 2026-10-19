"""港股行情服务层（移植自 hk_stock_screener backend/loader.py）。

数据来自 scripts/hk_stock/build_snapshot.py 离线生成的 parquet 快照与历史
（雅虎财经，延迟 15 分钟，不实时刷新），本模块只做读取、排序、分页。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = PROJECT_ROOT / "data" / "hk_snapshot.parquet"
HISTORY_PATH = PROJECT_ROOT / "data" / "hk_history.parquet"
CONFIG_PATH = PROJECT_ROOT / "scripts" / "hk_stock" / "config.yaml"

REQUIRED_COLUMNS = {"trade_date", "symbol", "name"}

SORTABLE_COLUMNS = {
    "open", "high", "low", "close", "pre_close", "change", "pct_change",
    "volume", "amount", "total_share",
    "ma5", "ma10", "ma20", "ma60",
    "ret_1d", "ret_5d", "ret_20d", "vol_ratio_5",
    "amplitude", "body_ratio", "upper_shadow_ratio", "lower_shadow_ratio",
    "market_cap", "forward_pe", "trailing_pe", "price_to_book",
    "revenue_growth", "earnings_growth", "roe", "profit_margin",
    "peg_ratio", "ps_ratio", "roa", "operating_margin",
    "debt_to_equity", "current_ratio", "dividend_yield", "dividend_rate",
    "risk_ma20_dev", "risk_ma60_dev", "risk_dd_20d", "risk_vol_20d",
    "signal_score",
}

_HISTORY_RANGE_DAYS = {"3m": 63, "6m": 126, "1y": 252, "2y": 504}

_SNAPSHOT_CACHE: pd.DataFrame | None = None
_HISTORY_CACHE: pd.DataFrame | None = None

_ZH_NAME_PATTERN = re.compile(r'-\s*"?([0-9A-Za-z]+\.HK)"?\s*#\s*(.+)$')


def load_zh_names(config_path: Path | None = None) -> dict[str, str]:
    """从 config.yaml 股票池行尾注释解析 symbol -> 中文名（如 `- "0700.HK"  # 腾讯控股`）。"""
    path = config_path or CONFIG_PATH
    names: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = _ZH_NAME_PATTERN.match(line.strip())
                if m:
                    names[m.group(1).upper()] = m.group(2).strip()
    except Exception:
        pass
    return names


def load_snapshot() -> pd.DataFrame:
    global _SNAPSHOT_CACHE
    frame = pd.read_parquet(SNAPSHOT_PATH)
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"{SNAPSHOT_PATH} 缺少必需列: {', '.join(missing)}，请先运行 scripts/hk_stock/build_snapshot.py")
    zh_names = load_zh_names()
    frame["name_zh"] = frame["symbol"].map(zh_names) if zh_names else None
    _SNAPSHOT_CACHE = frame
    return _SNAPSHOT_CACHE


def get_snapshot() -> pd.DataFrame:
    if _SNAPSHOT_CACHE is None:
        return load_snapshot()
    return _SNAPSHOT_CACHE


def load_history() -> pd.DataFrame:
    global _HISTORY_CACHE
    if not HISTORY_PATH.exists():
        _HISTORY_CACHE = pd.DataFrame()
    else:
        _HISTORY_CACHE = pd.read_parquet(HISTORY_PATH)
    return _HISTORY_CACHE


def get_history() -> pd.DataFrame:
    if _HISTORY_CACHE is None:
        return load_history()
    return _HISTORY_CACHE


def query_stocks(
    *,
    q: str | None = None,
    sort_by: str | None = None,
    sort_asc: bool = False,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    frame = get_snapshot()
    filtered = frame
    keyword = (q or "").strip().lower()
    if keyword:
        mask = (
            filtered["symbol"].str.lower().str.contains(keyword, na=False)
            | filtered["name"].fillna("").str.lower().str.contains(keyword, na=False)
        )
        if "name_zh" in filtered.columns:
            mask = mask | filtered["name_zh"].fillna("").str.contains(keyword, na=False)
        filtered = filtered[mask]

    if sort_by:
        if sort_by not in get_sortable_columns(frame):
            raise ValueError(f"不支持的排序字段: {sort_by}")
        filtered = filtered.sort_values(sort_by, ascending=sort_asc, na_position="last", kind="mergesort")
    else:
        filtered = filtered.sort_values("symbol", ascending=True, kind="mergesort")

    total = int(len(filtered))
    page = filtered.iloc[offset: offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "rows": _to_records(page),
    }


def query_stock_snapshot(symbol: str) -> dict:
    frame = get_snapshot()
    row = frame[frame["symbol"] == symbol]
    if row.empty:
        raise ValueError(f"未找到港股: {symbol}")
    return _to_records(row)[0]


def query_stock_history(symbol: str, range_key: str = "6m") -> dict:
    frame = get_history()
    if frame.empty:
        raise ValueError("history.parquet 不存在，请先运行 scripts/hk_stock/build_snapshot.py")
    stock = frame[frame["symbol"] == symbol].sort_values("day")
    if stock.empty:
        raise ValueError(f"未找到港股: {symbol}")
    days = _HISTORY_RANGE_DAYS.get(range_key, 126)
    recent = stock.tail(days)
    snapshot = get_snapshot()
    name_series = snapshot.loc[snapshot["symbol"] == symbol, "name"]
    name = str(name_series.iloc[0]) if not name_series.empty else symbol
    cols = [c for c in recent.columns if c != "symbol"]
    return {
        "symbol": symbol,
        "name": name,
        "bars": json.loads(recent[cols].to_json(orient="records")),
    }


def build_meta() -> dict:
    frame = get_snapshot()
    trade_date = None
    if not frame.empty and "trade_date" in frame.columns:
        trade_date = str(frame["trade_date"].max())
    return {"total": int(len(frame)), "trade_date": trade_date}


def get_sortable_columns(frame: pd.DataFrame | None = None) -> set[str]:
    if frame is None:
        frame = get_snapshot()
    return SORTABLE_COLUMNS.intersection(frame.columns)


def _to_records(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    cleaned = frame.where(pd.notna(frame), None)
    return json.loads(cleaned.to_json(orient="records"))
