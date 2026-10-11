"""指数日线下载作业：主要宽基（tushare index_daily）+ 申万一级行业（akshare）。

落盘 data/index_daily/stock/ts_code=XXX/data.parquet（与既有 6 只宽基同一
布局，data_reader._read_index_daily 直读）。回测基准 000300.SH 与市场
状态页、行业轮动的申万指数交叉验证都消费这张表。

数据源分工（2026-10-11 实测）：
- 宽基：tushare index_daily（2000 积分可用，pre_close 由官方全历史计算）；
- 申万行业：tushare sw_daily 需更高积分（实测无权限），改走 akshare
  index_hist_sw（申万研究口径，单次全历史，字段缺 pre_close 本地补算）。

用户禁令仅限"分钟线不得用 baostock/akshare/tickflow/tushare"（见记忆
minute-kline-source-pytdx-only），日线指数不在其列。

默认拉 2019 年至今（与存量宽基表起点一致）；DATA_JOB_START_DATE/END_DATE
可覆盖。增量策略是"整段重拉 + 按 trade_date 去重合并"，指数单代码全年
仅 ~250 行，成本可忽略，换取无接缝的 pre_close 一致性。
"""

import os
import time
from typing import Dict, List, Optional

import pandas as pd
from loguru import logger

DEFAULT_START = "20190102"

# 主要宽基：覆盖回测基准（000300.SH）、市场状态页与指数搜索的常用口径
BROAD_INDEXES: List[str] = [
    "000001.SH",  # 上证指数
    "000016.SH",  # 上证50
    "000300.SH",  # 沪深300（回测默认基准，此前本地缺失导致降级 399300.SZ）
    "000905.SH",  # 中证500
    "000852.SH",  # 中证1000
    "000688.SH",  # 科创50
    "399001.SZ",  # 深证成指
    "399006.SZ",  # 创业板指
    "399300.SZ",  # 沪深300（深交所口径，存量表沿用）
]

# 申万一级行业（2021 版 31 个，自 index_basic 过滤 category=一级行业指数 且非退市）
_SW_L1_CODES = [
    "801010", "801030", "801040", "801050", "801080", "801110", "801120",
    "801130", "801140", "801150", "801160", "801170", "801180", "801200",
    "801210", "801230", "801710", "801720", "801730", "801740", "801750",
    "801760", "801770", "801780", "801790", "801880", "801890", "801950",
    "801960", "801970", "801980",
]

_SCHEMA = ["ts_code", "trade_date", "close", "open", "high", "low",
           "pre_close", "change", "pct_chg", "vol", "amount"]

_AKSHARE_RATE_SECONDS = 0.5  # 申万源是网页抓取，礼貌限速


def _normalizeYmd(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 8 and text[:8].isdigit():
        return text[:8]
    try:
        return pd.to_datetime(text).strftime("%Y%m%d")
    except Exception:
        return None


def resolve_index_codes() -> List[str]:
    """本次要下载的指数清单；DATA_JOB_INDEX_CODES 可覆盖。"""
    raw = os.getenv("DATA_JOB_INDEX_CODES", "").strip()
    if raw:
        return [c.strip() for c in raw.split(",") if c.strip()]
    return BROAD_INDEXES + [f"{c}.SI" for c in _SW_L1_CODES]


def _fetch_broad(api, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    df = api.index_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return pd.DataFrame()
    return df


def _fetch_sw(ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """akshare 申万指数日线 → 标准十一列 schema。

    index_hist_sw 单次返回全历史（万级行也只是一次调用），这里取回后
    在内存里过滤窗口；pre_close/change/pct_chg 用全历史 close 补算，
    保证任何窗口起点都不会出现接缝值。
    """
    import akshare as ak

    raw = ak.index_hist_sw(symbol=ts_code.split(".")[0], period="day")
    if raw is None or raw.empty:
        return pd.DataFrame()
    df = raw.rename(columns={
        "日期": "trade_date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "vol", "成交额": "amount",
    })
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["pre_close"] = df["close"].shift(1)
    df["change"] = df["close"] - df["pre_close"]
    df["pct_chg"] = df["close"] / df["pre_close"] * 100 - 100
    df["ts_code"] = ts_code
    mask = (df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)
    return df.loc[mask, _SCHEMA]


def _upsert_index(ts_code: str, frame: pd.DataFrame, data_dir: str = "data") -> int:
    """按 ts_code 分区整表合并写回，返回合并后总行数。"""
    base = os.path.join(data_dir, "index_daily", "stock", f"ts_code={ts_code}")
    path = os.path.join(base, "data.parquet")
    existing = pd.DataFrame()
    if os.path.isfile(path):
        try:
            existing = pd.read_parquet(path)
        except Exception as e:
            logger.warning(f"读取存量指数数据失败 {path}: {e}")

    combined = pd.concat([existing, frame], ignore_index=True) if not existing.empty else frame
    if combined.empty:
        return 0
    combined["trade_date"] = combined["trade_date"].astype(str)
    combined = (
        combined.sort_values("trade_date")
        .drop_duplicates(subset=["trade_date"], keep="last")
        .reset_index(drop=True)
    )
    os.makedirs(base, exist_ok=True)
    combined.to_parquet(path, index=False)
    return len(combined)


def _fetch_sw_members(api) -> pd.DataFrame:
    """申万一级行业成分（index_member，含 in/out_date 可 PIT）。"""
    frames = []
    for code in _SW_L1_CODES:
        df = api.index_member(index_code=f"{code}.SI")
        if df is not None and not df.empty:
            frames.append(df)
        time.sleep(0.12)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _upsert_flat_table(frame: pd.DataFrame, rel_path: str, data_dir: str,
                       key_cols: List[str]) -> int:
    """单文件整表合并去重写回（index_members 等小表）。"""
    path = os.path.join(data_dir, rel_path)
    existing = pd.DataFrame()
    if os.path.isfile(path):
        try:
            existing = pd.read_parquet(path)
        except Exception as e:
            logger.warning(f"读取存量表失败 {path}: {e}")
    combined = pd.concat([existing, frame], ignore_index=True) if not existing.empty else frame
    if combined.empty:
        return 0
    combined = combined.drop_duplicates(subset=key_cols, keep="last").reset_index(drop=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    combined.to_parquet(path, index=False)
    return len(combined)


def run(data_dir: str = "data") -> Dict[str, object]:
    """下载全部指数日线与申万成分并合并写回。返回统计 dict（数据作业/AI 消费）。"""
    from db_utils import DatabaseUtils

    start_date = _normalizeYmd(os.getenv("DATA_JOB_START_DATE")) or DEFAULT_START
    end_date = _normalizeYmd(os.getenv("DATA_JOB_END_DATE")) \
        or pd.Timestamp.now().strftime("%Y%m%d")
    codes = resolve_index_codes()

    api = DatabaseUtils.init_tushare_api()
    stats = {"total": len(codes), "ok": 0, "empty": [], "failed": [], "rows": 0}
    for ts_code in codes:
        try:
            if ts_code.endswith(".SI"):
                frame = _fetch_sw(ts_code, start_date, end_date)
                time.sleep(_AKSHARE_RATE_SECONDS)
            else:
                frame = _fetch_broad(api, ts_code, start_date, end_date)
                time.sleep(0.12)
        except Exception as e:
            logger.error(f"[index_daily] {ts_code} 拉取失败: {e}")
            stats["failed"].append(ts_code)
            continue
        if frame.empty:
            stats["empty"].append(ts_code)
            continue
        rows = _upsert_index(ts_code, frame, data_dir=data_dir)
        stats["ok"] += 1
        stats["rows"] += rows
        logger.info(f"[index_daily] {ts_code} 合并后 {rows} 行")

    # 申万一级成分（行业轮动交叉验证/成分查询消费；失败不影响指数日线状态）
    try:
        members = _fetch_sw_members(api)
        if not members.empty:
            n = _upsert_flat_table(members, "index_members.parquet", data_dir,
                                   key_cols=["index_code", "con_code", "in_date"])
            logger.info(f"[index_daily] 申万一级成分合并后 {n} 行")
            stats["sw_members"] = n
    except Exception as e:
        logger.warning(f"[index_daily] 申万成分拉取失败（不影响指数日线）: {e}")

    stats["message"] = (
        f"指数日线完成：成功 {stats['ok']}/{stats['total']}，"
        f"空数据 {len(stats['empty'])}，失败 {len(stats['failed'])}"
    )
    logger.info(f"[index_daily] {stats['message']}")
    return stats


def main():
    result = run()
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
