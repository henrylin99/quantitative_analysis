"""事件归档服务测试：fake fuyao 客户端归档、晋级率、情绪因子落库。"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from app.services.event_archive_service import EventArchiveService


class _FakeClient:
    """fuyao 桩：固定三池/龙虎榜/天梯返回。"""

    def dragon_tiger_list(self, board_type="all", date=None):
        return {
            "trade_date": "2026-10-09",
            "stock_items": [
                {"thscode": "600127.SH", "ticker": "600127", "name": "金健米业",
                 "change": 0.1, "net_value": 6.0e7, "net_rate": 0.02,
                 "buy_value": 3.6e8, "sell_value": 3.0e8, "limit_reason": "粮油",
                 "range_days": 1, "hot_rank": 2, "hot_money_net_value": 6.3e7,
                 "concept_list": [{"name": "乳业"}, {"name": "玉米"}]},
                {"thscode": "", "name": "脏行丢弃"},
            ],
        }

    def limit_up_ladder(self):
        boards = {
            "two_board": [
                {"thscode": "000017.SZ", "ticker": "000017", "name": "深中华A",
                 "board_num": 2, "seal_nextday": True, "sign_level": 0},
                {"thscode": "000018.SZ", "board_num": 2, "seal_nextday": False,
                 "ticker": "000018", "name": "B", "sign_level": 1},
            ],
            "three_board": [
                {"thscode": "000019.SZ", "ticker": "000019", "name": "C",
                 "board_num": 3, "seal_nextday": True, "sign_level": 2},
            ],
        }
        return {"item": [{"date": "2026-10-08", "boards": boards},
                         {"date": "2026-10-09", "boards": boards}]}

    def limit_up_pool(self, date_ms=None, page=1, size=100, **kw):
        return {"pagination": {"total": 2, "pages": 1, "page": 1, "size": size},
                "item": [
                    {"thscode": "000017.SZ", "ticker": "000017", "name": "深中华A",
                     "last_price": 10.0, "price_change_ratio_pct": 10.0,
                     "continue_day_cnt": 2, "limit_up_time": "09:31:00",
                     "limit_reason": "题材", "seal_money": 1.2e8},
                    {"thscode": "000018.SZ", "ticker": "000018", "name": "B",
                     "last_price": 5.5, "price_change_ratio_pct": 10.03,
                     "continue_day_cnt": 1, "limit_up_time": "14:50:00",
                     "limit_reason": "低价", "seal_money": 3.0e7},
                ]}

    def limit_down_pool(self, date_ms=None, page=1, size=100):
        return {"pagination": {"total": 1, "pages": 1, "page": 1, "size": size},
                "item": [{"thscode": "000020.SZ", "ticker": "000020", "name": "D",
                          "last_price": 3.3, "price_change_ratio_pct": -10.0}]}

    def limit_break_pool(self, date_ms=None, page=1, size=100):
        return {"pagination": {"total": 1, "pages": 1, "page": 1, "size": size},
                "item": [{"thscode": "000021.SZ", "ticker": "000021", "name": "E",
                          "last_price": 7.7, "price_change_ratio_pct": 5.0,
                          "open_times": 2}]}


@pytest.fixture
def service(tmp_path):
    return EventArchiveService(data_dir=str(tmp_path), client=_FakeClient())


class TestArchiveDay:
    def test_dragon_tiger_and_ladder_archived(self, service):
        stats = service.archive_day()
        assert stats["errors"] == []
        assert stats["datasets"]["dragon_tiger"]["rows"] == 1  # 脏行丢弃
        assert stats["datasets"]["ladder"]["days"] == 2
        assert "limit_up" in stats["datasets"]  # 周末空池 → skipped 字段

        dragon = service.read_dataset("dragon_tiger")
        assert dragon["thscode"].tolist() == ["600127.SH"]
        assert dragon["concept"].iloc[0] == "乳业,玉米"
        assert dragon["net_rate"].iloc[0] == pytest.approx(0.02)

        ladder = service.read_dataset("ladder")
        assert set(ladder["date"]) == {"20261008", "20261009"}
        assert len(ladder) == 6
        assert set(ladder["ladder_slot"]) == {"two_board", "three_board"}

    def test_pools_and_mood(self, service):
        stats = service.archive_day()
        pool_stats = stats["datasets"]["limit_up"]
        assert pool_stats["rows"] >= 4  # 三池 + mood 单行

        mood = service.read_dataset("mood")
        row = mood.iloc[0]
        assert row["limit_up_count"] == 2
        assert row["limit_down_count"] == 1
        assert row["break_count"] == 1
        assert row["break_rate"] == pytest.approx(1 / 3)
        assert row["max_streak"] == 2

    def test_mood_summary(self, service):
        service.archive_day()
        summary = service.mood_summary()
        assert summary["limit_up_count"] == 2
        assert summary["break_rate"] == pytest.approx(1 / 3, abs=1e-3)
        assert summary["mean_limit_up"] == 2.0


class TestPromotionStats:
    def test_promotion_rate_by_height(self, service):
        service.archive_day()
        result = service.promotion_stats()
        assert "error" not in result
        by_height = {row["height"]: row for row in result["by_height"]}
        # 2板：2 个交易日 × 2 只，其中 seal_nextday=True 1 只/日
        assert by_height[2]["n_obs"] == 4
        assert by_height[2]["n_promoted"] == 2
        assert by_height[2]["promotion_rate"] == pytest.approx(0.5)
        assert by_height[3]["promotion_rate"] == 1.0
        assert result["n_days"] == 2


class TestMoodAlerts:
    def test_mood_extreme_alerts(self):
        from app.services.daily_alert_service import DailyAlertService

        record = {"mood": {"limit_up_count": 200, "mean_limit_up": 80.0,
                           "std_limit_up": 30.0, "n_days": 20,
                           "break_rate": 0.5}}
        alerts = DailyAlertService._derive_alerts(record, prev={})
        types = {a["type"] for a in alerts}
        assert "mood_overheat" in types       # 200 ≥ 80+2×30=140
        assert "mood_break_high" in types     # 0.5 ≥ 0.45

    def test_mood_normal_no_alert(self):
        from app.services.daily_alert_service import DailyAlertService

        record = {"mood": {"limit_up_count": 85, "mean_limit_up": 80.0,
                           "std_limit_up": 30.0, "n_days": 20,
                           "break_rate": 0.2}}
        alerts = DailyAlertService._derive_alerts(record, prev={})
        assert not [a for a in alerts if a["type"].startswith("mood")]

    def test_mood_insufficient_history_no_alert(self):
        from app.services.daily_alert_service import DailyAlertService

        record = {"mood": {"limit_up_count": 300, "mean_limit_up": 50.0,
                           "std_limit_up": 10.0, "n_days": 3,
                           "break_rate": None}}
        alerts = DailyAlertService._derive_alerts(record, prev={})
        assert not [a for a in alerts if a["type"].startswith("mood")]


class TestEventFactors:
    def test_compute_and_save_lands_standardized(self, service, tmp_path):
        from app.services.factor_engine import FactorEngine
        from app.services.parquet_state_store import ParquetStateStore

        service.archive_day()

        class _Reader:
            def get_stock_basic(self):
                return pd.DataFrame({
                    "ts_code": ["000017.SZ", "000018.SZ", "000020.SZ",
                                "000021.SZ", "600127.SH"],
                })

        engine = FactorEngine(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
        today = datetime.now().strftime("%Y%m%d")  # 三池归档恒写"现在"
        result = service.compute_and_save(today, engine=engine, reader=_Reader())
        assert "error" not in result and "skipped" not in result
        assert result["limit_up"] == 2 and result["break"] == 1 and result["dragon_tiger"] == 1

        values = engine.factor_repo.get_values(
            factor_ids=list(service.EVENT_FACTOR_IDS), trade_date=today)
        assert not values.empty
        assert values["percentile_rank"].notna().all()

        streak = values[values["factor_id"] == "limit_up_streak"] \
            .set_index("ts_code")["factor_value"]
        assert streak["000017.SZ"] == 2.0   # 连板高度来自涨停池
        assert streak["600127.SH"] == 0.0   # 非涨停股填 0
        flag = values[values["factor_id"] == "break_board_flag"] \
            .set_index("ts_code")["factor_value"]
        assert flag["000021.SZ"] == 1.0 and flag["000017.SZ"] == 0.0
        net = values[values["factor_id"] == "dragon_tiger_net_rate"] \
            .set_index("ts_code")["factor_value"]
        assert net["600127.SH"] == pytest.approx(0.02)

    def test_compute_skipped_without_pool_archive(self, service):
        result = service.compute_and_save("20990101")
        assert "skipped" in result
