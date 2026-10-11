"""pytdx 分钟线取数器测试：主机缓存/轮换/全池重扫、分页与 pre_close 重算。"""

import sys
import json
import types
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

import app.services.minute_tdx_fetcher as fetcher_mod
from app.services.minute_tdx_fetcher import TdxMinuteFetcher

_FAKE_HOSTS = [("h1", "10.0.0.1", 7709), ("h2", "10.0.0.2", 7709), ("h3", "10.0.0.3", 7709)]


class _FakeApi:
    """模拟 pytdx TdxHq_API：探测金丝雀（600000 5min×5 根）与取数页分离。"""

    def __init__(self, pages: dict, dead_hosts: set | None = None):
        self.pages = pages  # key: (market, code, start) -> list[dict]
        self.dead_hosts = dead_hosts or set()
        self.connect_calls: list[tuple] = []
        #: 主机探测专用响应（count==5 且 code==600000 时返回）
        self.probe_bars: list[dict] = [{"datetime": "2026-10-09 15:00"}]

    def connect(self, ip, port, time_out=5):
        self.connect_calls.append((ip, port))
        return (ip, port) not in self.dead_hosts

    def disconnect(self):
        pass

    def get_security_bars(self, category, market, code, start, count):
        if count == 5 and str(code) == "600000":
            return self.probe_bars
        return self.pages.get((market, code, start), [])


@pytest.fixture()
def patch_pytdx(monkeypatch):
    """注入假 pytdx.hq / pytdx.config.hosts 模块；install() 直接可调用，.api 取假 api。"""

    def install(pages: dict, dead_hosts: set | None = None):
        api = _FakeApi(pages, dead_hosts)
        install.api = api
        fake_hq = types.ModuleType("pytdx.hq")
        fake_hq.TdxHq_API = lambda *a, **kw: api
        monkeypatch.setitem(sys.modules, "pytdx.hq", fake_hq)
        fake_hosts = types.ModuleType("pytdx.config.hosts")
        fake_hosts.hq_hosts = _FAKE_HOSTS
        monkeypatch.setitem(sys.modules, "pytdx.config.hosts", fake_hosts)
        return api

    return install


def _bars_payload(base: datetime, n: int, step_min: int = 5) -> list[dict]:
    rows = []
    for i in range(n):
        dt = base + pd.Timedelta(minutes=step_min * i)
        close = 10.1 + 0.1 * i
        rows.append({
            "open": close - 0.1, "close": close, "high": close + 0.1, "low": close - 0.2,
            "vol": 1000.0, "amount": 10100.0, "datetime": dt.strftime("%Y-%m-%d %H:%M"),
        })
    return rows


@pytest.mark.module_data_jobs
class TestHostDiscovery:
    def test_scan_picks_working_host_and_caches(self, patch_pytdx, tmp_path, monkeypatch):
        monkeypatch.setenv("TDX_PROBE_WORKERS", "2")
        install = patch_pytdx({(1, "600000", 0): _bars_payload(datetime(2026, 10, 9, 9, 35), 5)})
        fetcher = TdxMinuteFetcher(data_dir=str(tmp_path))

        name, ip, port = fetcher.ensure_host()

        assert (ip, port) in {(h[1], h[2]) for h in _FAKE_HOSTS}
        cache = json.loads((tmp_path / "minute_sync" / "tdx_host.json").read_text())
        assert cache["current"][1] == ip
        assert len(cache["fallbacks"]) == len(_FAKE_HOSTS) - 1

    def test_cached_host_reused_without_rescan(self, patch_pytdx, tmp_path):
        patch_pytdx({(1, "600000", 0): _bars_payload(datetime(2026, 10, 9, 9, 35), 5)})
        fetcher = TdxMinuteFetcher(data_dir=str(tmp_path))
        _, ip1, port1 = fetcher.ensure_host()

        # 全池重扫不应被触发（触发即失败）
        def _boom(self):
            raise AssertionError("scan should not run when cache is valid")

        original_scan = TdxMinuteFetcher._scan_and_pick
        TdxMinuteFetcher._scan_and_pick = _boom
        try:
            fetcher2 = TdxMinuteFetcher(data_dir=str(tmp_path))
            _, ip2, port2 = fetcher2.ensure_host()
        finally:
            TdxMinuteFetcher._scan_and_pick = original_scan
        assert (ip2, port2) == (ip1, port1)

    def test_dead_cache_host_rotates_to_fallback(self, patch_pytdx, tmp_path):
        api = patch_pytdx({(1, "600000", 0): _bars_payload(datetime(2026, 10, 9, 9, 35), 5)})
        fetcher = TdxMinuteFetcher(data_dir=str(tmp_path))
        _, ip1, _ = fetcher.ensure_host()

        # 缓存主机（10.0.0.1）死亡 → 连接失败轮换到 fallback
        api.dead_hosts = {(ip1, 7709)}
        fetcher2 = TdxMinuteFetcher(data_dir=str(tmp_path))
        _, ip2, port2 = fetcher2.ensure_host()
        assert (ip2, port2) != (ip1, 7709)


@pytest.mark.module_data_jobs
class TestFetchPaged:
    def test_fetch_latest_single_page(self, patch_pytdx, tmp_path):
        patch_pytdx({(1, "600000", 0): _bars_payload(datetime(2026, 10, 9, 9, 35), 10)})
        fetcher = TdxMinuteFetcher(data_dir=str(tmp_path))

        df = fetcher.fetch_latest("600000.SH", "5min", limit=10)

        assert len(df) == 10
        assert set(df["ts_code"]) == {"600000.SH"}
        # 全序列重算 pre_close：首行 = 自身收盘（既有约定），其余 = 前一根 close
        assert df.iloc[0]["pre_close"] == pytest.approx(df.iloc[0]["close"])
        assert df.iloc[1]["pre_close"] == pytest.approx(df.iloc[0]["close"])
        # close 序列每根 +0.1：change=0.1，pct_chg≈0.99%
        assert df.iloc[-1]["change"] == pytest.approx(0.1)
        assert df.iloc[-1]["pct_chg"] == pytest.approx(0.1 / 11.0 * 100, abs=0.01)

    def test_fetch_range_paginates_until_floor(self, patch_pytdx, tmp_path):
        page_a = _bars_payload(datetime(2026, 10, 9, 9, 35), 10)          # 新页（start=0）
        page_b = _bars_payload(datetime(2026, 9, 1, 9, 35), 10)           # 旧页（start=800，早于 floor）
        patch_pytdx({
            (1, "600000", 0): page_a,
            (1, "600000", 800): page_b,
        })
        fetcher = TdxMinuteFetcher(data_dir=str(tmp_path))

        df = fetcher.fetch_range("600000.SH", "5min", "20260915")

        assert df["datetime"].min() >= pd.Timestamp("2026-09-15")
        assert len(df) == 10  # 旧页整页早于 floor 被过滤

    def test_empty_pages_return_empty_frame(self, patch_pytdx, tmp_path):
        patch_pytdx({})
        fetcher = TdxMinuteFetcher(data_dir=str(tmp_path))
        df = fetcher.fetch_latest("600000.SH", "5min")
        assert df.empty

    def test_all_hosts_dead_raises(self, patch_pytdx, tmp_path):
        patch_pytdx({}, dead_hosts={(h[1], h[2]) for h in _FAKE_HOSTS})
        fetcher = TdxMinuteFetcher(data_dir=str(tmp_path))
        with pytest.raises(ConnectionError):
            fetcher.fetch_latest("600000.SH", "5min")
