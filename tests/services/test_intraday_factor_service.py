"""日内因子库测试（批次 3.3）：合成 5min 截面逐因子核对 + 落库管线。"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from app.services.intraday_factor_service import (
    INTRADAY_FACTOR_IDS,
    IntradayFactorService,
    compute_intraday_factors,
)


def _session_bars(base_close: float, n: int, start: datetime, volume: float = 100.0) -> list[dict]:
    """n 根 5min bar：open=close=base_close 恒定，amount=close×volume。"""
    rows = []
    for i in range(n):
        dt = start + pd.Timedelta(minutes=5 * i)
        rows.append({
            "ts_code": "600000.SH", "datetime": dt, "period_type": "5min",
            "open": base_close, "high": base_close + 0.1, "low": base_close - 0.1,
            "close": base_close, "volume": volume, "amount": base_close * volume,
        })
    return rows


def _full_day(ts_code: str = "600000.SH", morning_close: float = 10.0,
              pm_close: float = 11.0, pm_volume: float = 200.0) -> pd.DataFrame:
    """48 根标准交易日：上午 24 根 + 午后 24 根，两段价格不同便于断言。"""
    rows = _session_bars(morning_close, 24, datetime(2026, 10, 9, 9, 35))
    rows += _session_bars(pm_close, 24, datetime(2026, 10, 9, 13, 5), volume=pm_volume)
    df = pd.DataFrame(rows)
    df["ts_code"] = ts_code
    df["pre_close"] = df["close"].shift(1)
    df.loc[df.index[0], "pre_close"] = 9.5  # 昨收
    df["pct_chg"] = [0.1 if i % 2 == 0 else -0.1 for i in range(len(df))]
    return df


@pytest.mark.module_data_jobs
class TestComputeIntradayFactors:
    def test_full_day_all_ten_factors(self):
        df = compute_intraday_factors(_full_day())
        pivot = df.pivot(index="ts_code", columns="factor_id", values="factor_value")
        assert set(pivot.columns) == set(INTRADAY_FACTOR_IDS)

        row = pivot.iloc[0]
        # open_mom_30: 10:00 收盘(10.0) / 首根 open(10.0) - 1
        assert row["open_mom_30"] == pytest.approx(0.0)
        # tail_ret_30: 15:00 收盘(11.0) / 14:35 open(11.0) - 1
        assert row["tail_ret_30"] == pytest.approx(0.0)
        # intraday_mom: 收盘(11.0) / 首根 open(10.0) - 1
        assert row["intraday_mom"] == pytest.approx(0.1)
        # morning_reversal: -(上午收盘 10/10 - 1)
        assert row["morning_reversal"] == pytest.approx(0.0)
        # vwap_dev: 全天 vwap = (10×2400 + 11×4800)/(2400+4800)
        vwap = (10.0 * 2400 + 11.0 * 4800) / 7200
        assert row["vwap_dev"] == pytest.approx(11.0 / vwap - 1)
        # 午后量能占比 = 4800/7200
        assert row["vol_concentration_pm"] == pytest.approx(2 / 3)
        # close_pos: high=max(10.1, 11.1), low=min(9.9, 10.9)
        assert row["close_pos_intraday"] == pytest.approx((11.0 - 9.9) / (11.1 - 9.9))
        # gap: 首根 open 10 / 昨收 9.5 - 1
        assert row["gap_strength"] == pytest.approx(10.0 / 9.5 - 1)
        # amount_cv: 上午 1000×24 根、午后 2200×24 根
        amounts = pd.Series([1000.0] * 24 + [2200.0] * 24)
        assert row["amount_cv"] == pytest.approx(amounts.std(ddof=1) / amounts.mean())

    def test_price_rise_scenario(self):
        # 全天单边上行：open=10 收盘=11，各动量因子均可精确断言
        df = _full_day(morning_close=10.0, pm_close=11.0)
        df["close"] = 11.0
        df["open"] = 10.0
        df["pre_close"] = df["close"].shift(1)
        df.loc[df.index[0], "pre_close"] = 9.0
        out = compute_intraday_factors(df).pivot(index="ts_code", columns="factor_id", values="factor_value").iloc[0]
        assert out["intraday_mom"] == pytest.approx(0.1)
        assert out["open_mom_30"] == pytest.approx(0.1)
        assert out["tail_ret_30"] == pytest.approx(0.1)
        assert out["morning_reversal"] == pytest.approx(-0.1)
        assert out["gap_strength"] == pytest.approx(10.0 / 9.0 - 1)

    def test_insufficient_bars_skipped(self):
        short = _full_day().iloc[:11]  # 少于 12 根
        out = compute_intraday_factors(short)
        assert out.empty

    def test_one_line_board_missing_close_pos(self):
        # 一字板：全天恒定价、high==low → close_pos_intraday 缺失，其余因子正常
        df = _full_day(morning_close=10.0, pm_close=10.0)
        df["open"] = df["high"] = df["low"] = df["close"] = 10.0
        out = compute_intraday_factors(df)
        pivot = out.pivot(index="ts_code", columns="factor_id", values="factor_value")
        assert "close_pos_intraday" not in pivot.columns
        assert "intraday_mom" in pivot.columns

    def test_multi_stock_independence(self):
        df_a = _full_day(ts_code="600000.SH")
        df_b = _full_day(ts_code="000001.SZ", pm_close=12.0)
        out = compute_intraday_factors(pd.concat([df_a, df_b]))
        pivot = out.pivot(index="ts_code", columns="factor_id", values="factor_value")
        assert pivot.loc["600000.SH", "intraday_mom"] == pytest.approx(0.1)
        assert pivot.loc["000001.SZ", "intraday_mom"] == pytest.approx(0.2)

    def test_min5_vol_std(self):
        df = _full_day()
        # 上午 5min 收益 +0.1%/-0.1% 交替，std 可手算
        rets = [0.1 if i % 2 == 0 else -0.1 for i in range(len(df))]
        df["pct_chg"] = rets
        out = compute_intraday_factors(df)
        pivot = out.pivot(index="ts_code", columns="factor_id", values="factor_value")
        expected = pd.Series(rets).std(ddof=1)  # pct_chg 存储口径为百分位单位
        assert pivot.iloc[0]["min5_vol_std"] == pytest.approx(expected)


def _write_minute_partition(data_dir: Path, ymd: str, df: pd.DataFrame) -> None:
    year, month, day = ymd.split("-")
    day_dir = data_dir / "stock_minute" / "5min" / f"year={year}" / f"month={month}" / f"day={day}"
    day_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(day_dir / "data.parquet", index=False)


@pytest.mark.module_data_jobs
class TestComputeAndSave:
    def test_compute_and_save_lands_in_factor_values(self, tmp_path):
        from app.services.factor_engine import FactorEngine
        from app.services.parquet_state_store import ParquetStateStore

        ymd = "2026-10-09"
        day_df = _full_day()
        day_df["ts_code"] = day_df["ts_code"].cat.remove_unused_categories() if hasattr(day_df["ts_code"], "cat") else day_df["ts_code"]
        _write_minute_partition(tmp_path, ymd, day_df)

        engine = FactorEngine(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
        service = IntradayFactorService(data_dir=str(tmp_path), engine=engine)
        result = service.compute_and_save(ymd)

        assert result["success"] is True
        assert result["stocks"] == 1
        assert result["factors"] == len(INTRADAY_FACTOR_IDS)

        values = engine.factor_repo.get_values(
            factor_ids=list(INTRADAY_FACTOR_IDS), trade_date=ymd.replace("-", "")
        )
        assert not values.empty
        assert set(values["factor_id"]) == set(INTRADAY_FACTOR_IDS)
        # 标准化列已按既有管线补齐
        assert values["percentile_rank"].notna().all()
        assert values["z_score"].notna().all()

    def test_no_minute_data_returns_failure(self, tmp_path):
        from app.services.factor_engine import FactorEngine
        from app.services.parquet_state_store import ParquetStateStore

        engine = FactorEngine(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
        service = IntradayFactorService(data_dir=str(tmp_path), engine=engine)
        result = service.compute_and_save("2026-10-09")
        assert result["success"] is False
