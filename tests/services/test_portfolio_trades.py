"""组合交易流水测试：记账、持仓更新、重放重建、市值曲线。"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.parquet_state_store import PortfolioRepository, ParquetStateStore


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    r = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))
    # equity_curve 的行情读取打桩：两票合成价格
    daily = pd.DataFrame([
        {"ts_code": "600519.SH", "trade_date": "2026-09-30", "close": 1500.0},
        {"ts_code": "600519.SH", "trade_date": "2026-10-06", "close": 1600.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-09-30", "close": 10.0},
        {"ts_code": "000001.SZ", "trade_date": "2026-10-06", "close": 12.0},
    ])

    import app.services.data_reader as dr_mod
    monkeypatch.setattr(dr_mod.ParquetDataReader, "get_daily",
                        lambda self, ts_codes=None, start_date=None, end_date=None: daily.copy())
    return r


class TestTrades:
    def test_buy_then_sell_updates_position(self, repo):
        repo.add_trade("p1", "600519.SH", "buy", 100, 1500.0, fee=100)
        pos = repo.get_position_by_stock("p1", "600519.SH")
        assert pos["position_size"] == 100
        # 成本含费用：(1500*100+100)/100 = 1501
        assert pos["avg_cost"] == pytest.approx(1501.0)

        repo.add_trade("p1", "600519.SH", "sell", 40, 1600.0, fee=50)
        pos = repo.get_position_by_stock("p1", "600519.SH")
        assert pos["position_size"] == 60
        assert pos["avg_cost"] == pytest.approx(1501.0)  # 卖出不改成本基
        assert pos["current_price"] == 1600.0

    def test_trades_listed_desc(self, repo):
        repo.add_trade("p1", "A.SH", "buy", 100, 10, traded_at="2026-10-05")
        repo.add_trade("p1", "A.SH", "buy", 100, 11, traded_at="2026-10-06")
        trades = repo.list_trades("p1")
        assert [t["traded_at"] for t in trades] == ["2026-10-06", "2026-10-05"]

    def test_validation(self, repo):
        with pytest.raises(ValueError):
            repo.add_trade("p1", "A.SH", "hold", 100, 10)
        with pytest.raises(ValueError):
            repo.add_trade("p1", "A.SH", "buy", -5, 10)
        with pytest.raises(ValueError):
            repo.add_trade("p1", "A.SH", "buy", 100, 0)

    def test_remove_trade_rebuilds(self, repo):
        t1 = repo.add_trade("p1", "600519.SH", "buy", 100, 1500)
        repo.add_trade("p1", "600519.SH", "buy", 100, 1600)
        assert repo.get_position_by_stock("p1", "600519.SH")["position_size"] == 200

        assert repo.remove_trade("p1", t1["id"]) is True
        assert repo.remove_trade("p1", t1["id"]) is False
        pos = repo.get_position_by_stock("p1", "600519.SH")
        assert pos["position_size"] == 100
        assert pos["avg_cost"] == pytest.approx(1600.0)

    def test_rebuild_creates_missing_position_row(self, repo):
        repo.add_trade("p1", "000001.SZ", "buy", 500, 10)
        # 手动删掉持仓行，模拟账本有而持仓表无
        with repo.store.locked(PortfolioRepository.TABLE_POSITIONS):
            pdf = repo.store.read_frame(PortfolioRepository.TABLE_POSITIONS)
            repo.store.write_frame(PortfolioRepository.TABLE_POSITIONS,
                                   pdf[pdf["ts_code"] != "000001.SZ"])
        touched = repo.rebuild_positions_from_trades("p1")
        assert touched >= 1
        pos = repo.get_position_by_stock("p1", "000001.SZ")
        assert pos["position_size"] == 500


class TestEquityCurve:
    def test_curve_values(self, repo):
        repo.add_trade("p1", "600519.SH", "buy", 1, 1500, traded_at="2026-09-30")
        repo.add_trade("p1", "000001.SZ", "buy", 100, 10, traded_at="2026-09-30")
        curve = repo.equity_curve("p1")
        assert "error" not in curve
        by_date = dict(zip(curve["dates"], curve["values"]))
        assert by_date["2026-09-30"] == pytest.approx(1500 + 100 * 10)
        assert by_date["2026-10-06"] == pytest.approx(1600 + 100 * 12)
        assert curve["cost_basis"] == pytest.approx(1500 + 1000)

    def test_no_trades(self, repo):
        assert "error" in repo.equity_curve("p1")

    def test_partial_exit_reflects_in_curve(self, repo):
        repo.add_trade("p1", "600519.SH", "buy", 2, 1500, traded_at="2026-09-30")
        repo.add_trade("p1", "600519.SH", "sell", 1, 1600, traded_at="2026-10-06")
        curve = repo.equity_curve("p1")
        by_date = dict(zip(curve["dates"], curve["values"]))
        assert by_date["2026-09-30"] == pytest.approx(3000)
        assert by_date["2026-10-06"] == pytest.approx(1600)  # 只剩 1 股 × 当日收盘
