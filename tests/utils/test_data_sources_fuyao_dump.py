"""dump 缓存与三档取数策略合约测试（fake client，不访问网络）。"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from app.utils.data_sources.fuyao_client import FuyaoError
from app.utils.data_sources.fuyao_dump import DumpStore, FuyaoDailyFetcher
from app.utils.data_sources.fuyao_normalize import DAILY_COLUMNS


def _beijing_midnight_ms(ymd: str) -> int:
    dt = datetime.strptime(ymd, "%Y%m%d")
    return int((dt - datetime(1970, 1, 1)).total_seconds() * 1000) - 8 * 3600 * 1000


def _dump_row(ts_code, ymd, close, volume=100_000, turnover=1_000_000):
    return {
        "thscode": ts_code, "currency": "CNY", "interval": "1d", "adjusted": "none",
        "date_ms": _beijing_midnight_ms(ymd),
        "open_price": close, "high_price": close, "low_price": close, "close_price": close,
        "volume": volume, "turnover": turnover,
    }


def _dump_frame(ts_codes, ymds):
    rows = [
        _dump_row(code, ymd, close=10.0 + i * 0.1)
        for i, ymd in enumerate(ymds)
        for code in ts_codes
    ]
    return pd.DataFrame(rows)


class FakeDumpClient:
    """dump_download_url/download_dump 的进程内替身。"""

    def __init__(self, dumps):
        self.dumps = dumps  # kind -> DataFrame
        self.downloads = []

    def dump_download_url(self, kind):
        return {"presigned_url": f"https://oss.example.com/releases/20260904/{kind.replace('-', '_')}.parquet"}

    def download_dump(self, kind, dest_path):
        self.downloads.append(kind)
        self.dumps[kind].to_parquet(dest_path)


def _fetcher(tmp_path, recent_dump=None, full_dump=None):
    dumps = {}
    if recent_dump is not None:
        dumps["daily-k-10d"] = recent_dump
    if full_dump is not None:
        dumps["daily-k"] = full_dump
    client = FakeDumpClient(dumps)
    store = DumpStore(client, cache_dir=tmp_path)
    return FuyaoDailyFetcher(client=client, store=store), client


# ---- DumpStore ----

def test_dump_store_downloads_once_and_caches_by_release(tmp_path):
    dumps = {"daily-k-10d": _dump_frame(["000001.SZ"], ["20260904"])}
    fake = FakeDumpClient(dumps)
    store = DumpStore(fake, cache_dir=tmp_path)

    path1 = store.ensure_path("daily-k-10d", "daily_k_10d")
    path2 = store.ensure_path("daily-k-10d", "daily_k_10d")
    assert path1 == path2
    assert fake.downloads == ["daily-k-10d"]  # 第二次命中缓存


def test_dump_store_reuses_old_full_dump_when_covering_start(tmp_path):
    """已有 10 年 dump 覆盖请求起点时复用旧 release，不重下 172MB。"""
    full = _dump_frame(["000001.SZ"], ["20260601", "20260904"])
    fake = FakeDumpClient({})
    store = DumpStore(fake, cache_dir=tmp_path)
    # 预置旧 release 缓存（模拟早前下载）
    old_path = tmp_path / "daily_k__20260601.parquet"
    full.to_parquet(old_path)

    path = store.ensure_path("daily-k", "daily_k", reuse_old_if_covers="20260701")
    assert path == old_path
    assert fake.downloads == []


# ---- FuyaoDailyFetcher 三档策略 ----

def test_fetch_dates_uses_recent_dump_for_near_window(tmp_path):
    ymds = [f"202609{d:02d}" for d in range(1, 5)]
    recent = _dump_frame(["000001.SZ", "600000.SH"], ymds)
    fetcher, fake = _fetcher(tmp_path, recent_dump=recent)

    result = fetcher.fetch_dates(["20260903", "20260904"])
    assert set(result) == {"20260903", "20260904"}
    assert set(fake.downloads) == {"daily-k-10d"}  # 未触发 10 年 dump
    for frame in result.values():
        assert list(frame.columns) == DAILY_COLUMNS
    # pre_close 由前一日推导
    day4 = result["20260904"]
    assert (day4["pre_close"] == 10.2).all()


def test_fetch_dates_falls_back_to_full_dump_for_old_window(tmp_path):
    recent = _dump_frame(["000001.SZ"], ["20260901", "20260904"])
    full = _dump_frame(["000001.SZ"], ["20250601", "20250602", "20250603"])
    fetcher, fake = _fetcher(tmp_path, recent_dump=recent, full_dump=full)

    result = fetcher.fetch_dates(["20250602", "20250603"])
    assert set(result) == {"20250602", "20250603"}
    assert "daily-k" in fake.downloads
    assert "daily-k-10d" in fake.downloads  # 补尾不触发（日期都在大 dump 内）→ 实际是覆盖判断
    # pre_close 在深窗口内正确推导
    day3 = result["20250603"]
    assert day3["pre_close"].notna().all()


def test_fetch_dates_rejects_window_beyond_ten_years(tmp_path):
    full = _dump_frame(["000001.SZ"], ["20250601"])
    fetcher, _ = _fetcher(tmp_path, recent_dump=_dump_frame(["000001.SZ"], ["20260904"]), full_dump=full)
    with pytest.raises(FuyaoError) as exc:
        fetcher.fetch_dates(["20100101", "20260904"])
    assert exc.value.code == "window_too_long"


def test_fetch_dates_rejects_too_many_uncovered_dates(tmp_path):
    """dump 覆盖不了且缺口超过兜底上限时明确失败，而不是烧数小时单标的接口。"""
    recent = _dump_frame(["000001.SZ"], ["20260901", "20260904"])
    # 大 dump 只覆盖 6 月初，缺口 [20250610..20250831] 远超 5 天
    full = _dump_frame(["000001.SZ"], ["20250601", "20250602"])
    fetcher, _ = _fetcher(tmp_path, recent_dump=recent, full_dump=full)
    with pytest.raises(FuyaoError) as exc:
        fetcher.fetch_dates(["20250610", "20250611", "20250612", "20250613", "20250614", "20250615"])
    assert exc.value.code == "dates_not_covered"
