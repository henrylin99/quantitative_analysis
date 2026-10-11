"""全市场分钟线同步服务测试：断点续传、失败冷却、运行互斥、写入链路。"""

from datetime import datetime, timedelta
from pathlib import Path

import json

import pandas as pd
import pytest

from app.services.minute_market_sync_service import MinuteMarketSyncService


class _ScriptedClient:
    """假客户端：fail_codes 内的代码抛异常，其余返回两根 bar。"""

    def __init__(self, fail_codes=()):
        self.fail_codes = set(fail_codes)
        self.latest_calls: list[str] = []
        self.range_calls: list[tuple] = []

    def fetch_latest(self, ts_code, period_type="5min", limit=600):
        self.latest_calls.append(ts_code)
        return self._bars(ts_code, period_type)

    def fetch_range(self, ts_code, period_type, start_date):
        self.range_calls.append((ts_code, period_type, start_date))
        return self._bars(ts_code, period_type)

    def _bars(self, ts_code, period_type):
        if ts_code in self.fail_codes:
            raise RuntimeError("boom")
        return pd.DataFrame(
            [
                {"datetime": datetime(2026, 10, 9, 9, 35), "open": 10.0, "close": 10.1,
                 "high": 10.2, "low": 9.9, "volume": 1000.0, "amount": 10100.0,
                 "pre_close": 10.0, "change": 0.1, "pct_chg": 1.0,
                 "ts_code": ts_code, "period_type": period_type},
                {"datetime": datetime(2026, 10, 9, 9, 40), "open": 10.1, "close": 10.2,
                 "high": 10.3, "low": 10.0, "volume": 1200.0, "amount": 12240.0,
                 "pre_close": 10.1, "change": 0.1, "pct_chg": 0.99,
                 "ts_code": ts_code, "period_type": period_type},
            ]
        )


@pytest.fixture()
def service(tmp_path):
    svc = MinuteMarketSyncService(data_dir=str(tmp_path))
    svc._client_factory = lambda: _ScriptedClient()
    return svc


def _stock_codes(offset: int, n: int) -> list[str]:
    """规范 6 位数字假代码：000000.SZ 起。"""
    return [f"{offset + i:06d}.SZ" for i in range(n)]


@pytest.mark.module_data_jobs
class TestSyncMarket:
    def test_happy_path_writes_minute_parquet(self, service, tmp_path):
        result = service.sync_market(stock_list=_stock_codes(0, 3))
        assert result["success"] is True
        assert result["failed_stocks"] == 0
        assert result["rows_written"] == 6
        stored = pd.read_parquet(
            Path(tmp_path) / "stock_minute" / "5min" / "year=2026" / "month=10" / "day=09" / "data.parquet"
        )
        assert len(stored) == 6
        assert set(stored["ts_code"]) == set(_stock_codes(0, 3))
        # pre_close/change/pct_chg 已按存储 schema 补齐
        assert stored["pre_close"].notna().all()

    def test_partial_failure_not_marked_done(self, service):
        codes = _stock_codes(0, 3)
        service._client_factory = lambda: _ScriptedClient(fail_codes=[codes[1]])
        result = service.sync_market(stock_list=codes)
        assert result["success"] is True
        assert result["failed_stocks"] == 1
        state = service.load_state()
        assert codes[1] in state["failed"]
        assert codes[1] not in state["done_codes"]

    def test_cooldown_aborts_and_resumes(self, service):
        # 前 2 只成功，其后 5 只失败：第 3 只失败触发冷却（阈值 3）
        ok_codes = _stock_codes(0, 2)
        fail_codes = _stock_codes(100, 5)
        codes = ok_codes + fail_codes
        service._client_factory = lambda: _ScriptedClient(fail_codes=fail_codes)
        result = service.sync_market(stock_list=codes, cooldown_failures=3)
        assert result["success"] is False
        assert "冷却" in result["message"]
        state = service.load_state()
        assert state["finished_at"] is None
        assert state["cooldown"] is True
        assert len(state["done_codes"]) == 2

        # 续传：失败源恢复（重置缓存 client + 干净 client），只处理剩余 5 只
        service._client = None
        service._client_factory = lambda: _ScriptedClient()
        resumed = service.sync_market(stock_list=codes)
        assert resumed["success"] is True
        state = service.load_state()
        assert len(state["done_codes"]) == 7
        assert state["finished_at"] is not None

    def test_running_state_blocks_new_run(self, service):
        service.sync_market(stock_list=_stock_codes(0, 2))
        # 伪造"正在运行"的心跳
        state = service.load_state()
        state["finished_at"] = None
        service.save_state(state)
        result = service.sync_market(stock_list=_stock_codes(50, 2))
        assert result["success"] is False
        assert "在运行" in result["message"]

    def test_stale_running_state_does_not_block(self, service):
        service.sync_market(stock_list=_stock_codes(0, 1))
        # 直接改状态文件模拟"心跳已停 60 分钟"（save_state 会刷新 updated_at，绕开它）
        state = service.load_state()
        state["finished_at"] = None
        state["updated_at"] = (datetime.now() - timedelta(minutes=60)).isoformat(timespec="seconds")
        service.state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        result = service.sync_market(stock_list=_stock_codes(10, 1))
        assert result["success"] is True

    def test_progress_view(self, service):
        service.sync_market(stock_list=_stock_codes(0, 2))
        progress = service.get_progress()
        assert progress["total"] == 2
        assert progress["done"] == 2
        assert progress["failed"] == 0
        assert progress["running"] is False

    def test_empty_universe_rejected(self, service):
        result = service.sync_market(stock_list=[])
        assert result["success"] is False

    def test_backfill_mode_passes_start_date_to_fetcher(self, service):
        client = _ScriptedClient()
        service._client_factory = lambda: client
        result = service.sync_market(
            stock_list=["000001.SZ"], mode="backfill", start_date="20260410"
        )
        assert result["success"] is True
        assert client.range_calls == [("000001.SZ", "5min", "20260410")]
