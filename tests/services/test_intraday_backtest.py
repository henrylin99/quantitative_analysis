"""分钟级（日内）回测测试：合成 5min 面板逐笔核对 T+1/涨跌停/止损/复利。

时点约定：_bar_time(0)=09:35 … _bar_time(5)=10:00，ret_30m 需 6 根回看，
首个有效信号 bar 为 i=6（10:05）——全部用例统一 signal_time="10:05"。
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from app.services.intraday_backtest_service import IntradayBacktestService, limit_ratio_for


def _bar_time(i: int) -> str:
    """第 i 根 5min bar 的开始时刻：前 12 根 09:35 起，其后 13:05 起。"""
    total = (9 * 60 + 35 + 5 * i) if i < 12 else (13 * 60 + 5 + 5 * (i - 12))
    return f"{total // 60:02d}:{total % 60:02d}"


def _bars(ts_code: str, day: str, prices: list[float], opens: list[float] | None = None,
          prev_close: float | None = None) -> list[dict]:
    """逐根 bar：close=prices[i]，open=opens[i]（缺省=前一根 close）。"""
    rows = []
    prev = prev_close if prev_close is not None else prices[0]
    for i, close in enumerate(prices):
        o = opens[i] if opens else prev
        rows.append({
            "ts_code": ts_code, "datetime": datetime.strptime(f"{day} {_bar_time(i)}", "%Y-%m-%d %H:%M"),
            "period_type": "5min", "open": o, "high": max(o, close) + 0.01,
            "low": min(o, close) - 0.01, "close": close, "volume": 1000.0,
            "amount": close * 1000.0, "pre_close": prev, "pct_chg": 0.0,
        })
        prev = close
    return rows


def _write_partitions(tmp_path: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    keyed = df.groupby([df["datetime"].dt.year, df["datetime"].dt.month, df["datetime"].dt.day])
    for (year, month, day), g in keyed:
        day_dir = tmp_path / "stock_minute" / "5min" / f"year={year}" / f"month={month}" / f"day={day}"
        day_dir.mkdir(parents=True, exist_ok=True)
        g.to_parquet(day_dir / "data.parquet", index=False)


@pytest.fixture()
def service(tmp_path):
    return IntradayBacktestService(data_dir=str(tmp_path))


@pytest.mark.module_data_jobs
class TestRunBasics:
    def test_ret30m_signal_enters_next_bar_open(self, service, tmp_path):
        # 10:05 信号（0%）→ 10:10 bar 开盘入场，随后上行；T+1 → 次日出
        rows = _bars("600000.SH", "2026-10-08", [10.0] * 8 + [10.5, 10.8, 11.0, 11.2])
        rows += _bars("600000.SH", "2026-10-09", [11.2, 11.5, 11.8, 12.0])
        _write_partitions(tmp_path, rows)

        result = service.run("20261008", "20261009", signal="ret_30m",
                             direction="high", top_n=1, signal_time="10:05",
                             horizon_bars=4, respect_t1=True)

        assert "error" not in result, result.get("error")
        assert result["trades_total"] >= 1
        t = result["trades"][0]
        assert t["ts_code"] == "600000.SH"
        assert t["entry_date"] == "2026-10-08"
        # 入场价 = 10:10 bar 开盘（= 10:05 收盘 10.0）
        assert t["entry_price"] == pytest.approx(10.0)
        assert t["exit_time"].date().isoformat() >= "2026-10-09"
        assert t["ret"] > 0

    def test_t1_forces_next_day_exit(self, service, tmp_path):
        rows = _bars("600000.SH", "2026-10-08", [10.0] * 6 + [10.2, 10.4])
        rows += _bars("600000.SH", "2026-10-09", [10.4, 10.6, 10.8, 11.0])
        _write_partitions(tmp_path, rows)
        result = service.run("20261008", "20261009", signal="ret_30m", top_n=1,
                             signal_time="10:05", horizon_bars=1, respect_t1=True)
        assert "error" not in result
        # horizon=1 但 T+1 强制出场在次日首根
        assert all(t["exit_time"].date().isoformat() == "2026-10-09" for t in result["trades"])
        assert all(t["exit_reason"] == "horizon" for t in result["trades"])

    def test_respect_t1_off_allows_intraday_exit(self, service, tmp_path):
        rows = _bars("600000.SH", "2026-10-08", [10.0] * 6 + [10.2, 10.4, 10.4, 10.5])
        _write_partitions(tmp_path, rows)
        result = service.run("20261008", "20261008", signal="ret_30m", top_n=1,
                             signal_time="10:05", horizon_bars=1, respect_t1=False)
        assert "error" not in result
        t = result["trades"][0]
        assert t["entry_date"] == t["exit_time"].date().isoformat() == "2026-10-08"

    def test_limit_up_entry_skipped(self, service, tmp_path):
        # 10:05 信号 → 10:10 bar 开盘 11.22 = 10.2×1.10 主板涨停 → 放弃该笔
        rows = _bars("600000.SH", "2026-10-08", [10.0] * 6 + [10.2, 10.2],
                     opens=[10.0] * 7 + [11.22])
        _write_partitions(tmp_path, rows)
        result = service.run("20261008", "20261008", signal="ret_30m", top_n=1,
                             signal_time="10:05", horizon_bars=2, respect_t1=False)
        assert result.get("error") == "信号未产生任何可成交交易（涨跌停/T+1 过滤后为空）"

    def test_stop_loss_triggers_before_horizon(self, service, tmp_path):
        # D2 深跌触发 -3% 止损（T+1 下从次日首根开始扫描）
        rows = _bars("600000.SH", "2026-10-08", [10.0] * 6 + [10.2, 10.4])
        rows += _bars("600000.SH", "2026-10-09", [10.3, 10.0, 9.8, 9.7])
        _write_partitions(tmp_path, rows)
        result = service.run("20261008", "20261009", signal="ret_30m", top_n=1,
                             signal_time="10:05", horizon_bars=6,
                             stop_loss_pct=3.0, respect_t1=True)
        assert "error" not in result
        t = result["trades"][0]
        assert t["exit_reason"] == "stop_loss"
        # 止损价 = 入场价 × (1-3%)
        assert t["exit_price"] == pytest.approx(t["entry_price"] * 0.97)
        assert t["exit_time"].date().isoformat() == "2026-10-09"

    def test_direction_low_picks_weakest(self, service, tmp_path):
        rows = _bars("600000.SH", "2026-10-08", [10.0] * 6 + [10.4, 10.8, 10.8, 10.9])   # 强动量
        rows += _bars("000001.SZ", "2026-10-08", [10.0] * 6 + [9.8, 9.6, 9.6, 9.5])      # 弱动量
        _write_partitions(tmp_path, rows)
        result = service.run("20261008", "20261008", signal="ret_30m", direction="low",
                             top_n=1, signal_time="10:05", horizon_bars=2, respect_t1=False)
        assert "error" not in result
        assert result["trades"][0]["ts_code"] == "000001.SZ"

    def test_nav_compounding_across_days(self, service, tmp_path):
        # 两日信号：D1 与 D2 各一笔，D2 上涨 → 净值复利上升
        rows = _bars("600000.SH", "2026-10-08", [10.0] * 6 + [10.2, 10.4])
        rows += _bars("600000.SH", "2026-10-09", [10.4, 10.6, 10.8, 11.0])
        _write_partitions(tmp_path, rows)
        result = service.run("20261008", "20261009", signal="ret_30m", top_n=1,
                             signal_time="10:05", horizon_bars=1, respect_t1=True)
        assert "error" not in result
        assert result["summary"]["final_nav"] > 1.0
        assert len(result["nav"]) >= 1

    def test_invalid_params_rejected(self, service):
        assert "error" in service.run("20261008", "20261009", signal="nope")
        assert "error" in service.run("20261008", "20261009", direction="sideways")


@pytest.mark.module_data_jobs
class TestLimitRatio:
    def test_board_ratios(self):
        assert limit_ratio_for("600000.SH") == 0.10
        assert limit_ratio_for("300502.SZ") == 0.20
        assert limit_ratio_for("688981.SH") == 0.20
        assert limit_ratio_for("920025.BJ") == 0.30
