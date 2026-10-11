"""基本面 PIT 因子服务测试：公告日边界、修订、缺同比、零分母、落库。"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.fundamental_pit_service import (
    FUNDAMENTAL_PIT_FACTOR_IDS,
    FundamentalPitService,
)


def _write_statement(tmp_path, table: str, frame: pd.DataFrame):
    part = tmp_path / table / "year=2026" / "month=04" / "day=30"
    part.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(part / "data.parquet", index=False)


def _income_row(ts_code, ann, end, revenue, oper_cost, profit, report_type="1"):
    return {"ts_code": ts_code, "ann_date": ann, "f_ann_date": ann,
            "end_date": end, "report_type": report_type,
            "revenue": revenue, "oper_cost": oper_cost,
            "n_income_attr_p": profit}


def _balance_row(ts_code, ann, end, assets, liab, equity):
    return {"ts_code": ts_code, "ann_date": ann, "f_ann_date": ann,
            "end_date": end, "report_type": "1",
            "total_assets": assets, "total_liab": liab,
            "total_hldr_eqy_exc_min_int": equity}


def _cash_row(ts_code, ann, end, cfo):
    return {"ts_code": ts_code, "ann_date": ann, "f_ann_date": ann,
            "end_date": end, "report_type": "1", "n_cashflow_act": cfo}


@pytest.fixture
def service(tmp_path):
    """两只股票：
    - 600001.SH：年报 20251231（毛利 40%）公告日 20260420；同比年报 20241231（毛利 30%）公告 20250410（2025 分区外，仅 2026 目录内不放）→ 无同比，走缺失
      另设 Q1 20260331（毛利 50%）公告日 20260425。
    - 600002.SH：年报 20251231（毛利 20%）公告 20260410，修订版公告 20260425（毛利 25%）；
      同比 20241231（毛利 10%，ann 20250405 —— 同样不在 2026 表内）
    """
    income = pd.DataFrame([
        # 600001.SH：2025 年报
        _income_row("600001.SH", "20260420", "20251231", revenue=100.0, oper_cost=60.0, profit=10.0),
        # 600001.SH：2026 一季报（注意混存格式：end_date 带横杠）
        _income_row("600001.SH", "20260425", "2026-03-31", revenue=50.0, oper_cost=25.0, profit=5.0),
        # 600002.SH：2025 年报原版 + 修订版
        _income_row("600002.SH", "20260410", "20251231", revenue=200.0, oper_cost=160.0, profit=8.0),
        _income_row("600002.SH", "20260425", "20251231", revenue=200.0, oper_cost=150.0, profit=9.0),
        # report_type=1 之外的行应被过滤
        _income_row("600002.SH", "20260426", "20260331", revenue=1.0, oper_cost=0.5, profit=0.1,
                    report_type="2"),
    ])
    _write_statement(tmp_path, "income_statement", income)

    balance = pd.DataFrame([
        _balance_row("600001.SH", "20260420", "20251231", assets=1000.0, liab=400.0, equity=600.0),
        _balance_row("600001.SH", "20260425", "20260331", assets=1100.0, liab=440.0, equity=660.0),
        _balance_row("600002.SH", "20260410", "20251231", assets=800.0, liab=480.0, equity=320.0),
    ])
    _write_statement(tmp_path, "balance_sheet", balance)

    cash = pd.DataFrame([
        _cash_row("600001.SH", "20260420", "20251231", cfo=15.0),
        _cash_row("600001.SH", "20260425", "20260331", cfo=6.0),
        _cash_row("600002.SH", "20260410", "20251231", cfo=4.0),
    ])
    _write_statement(tmp_path, "cash_flow", cash)
    return FundamentalPitService(data_dir=str(tmp_path))


def _values_at(service, date, factor_id):
    frame = service.compute_for_date(date)
    if frame.empty:
        return {}
    pick = frame[frame["factor_id"] == factor_id].set_index("ts_code")["factor_value"]
    return {code: float(v) for code, v in pick.items()}


class TestPitBoundary:
    def test_uses_latest_known_report(self, service):
        # 600001 年报 4/20 公告：4/19 其报告尚不可知 → 缺失；600002（4/10 公告）已知
        before = _values_at(service, "20260419", "accrual_ratio")
        assert "600001.SH" not in before
        assert before.get("600002.SH") == pytest.approx((8.0 - 4.0) / 800.0)
        # 4/21：600001 年报已知
        values = _values_at(service, "20260421", "accrual_ratio")
        assert values.get("600001.SH") == pytest.approx((10.0 - 15.0) / 1000.0)

    def test_quarter_report_switches_at_ann_date(self, service):
        # 600001 一季报 4/25 公告：4/24 仍用年报，4/26 切换到 Q1
        before = _values_at(service, "20260424", "ocf_to_ni")
        after = _values_at(service, "20260426", "ocf_to_ni")
        assert before["600001.SH"] == pytest.approx(15.0 / 10.0)
        assert after["600001.SH"] == pytest.approx(6.0 / 5.0)

    def test_revision_visible_only_after_reannouncement(self, service):
        # 600002 年报 4/10 原版（毛利 20%），4/25 修订版（毛利 25%）
        before = _values_at(service, "20260415", "gross_margin_chg")
        after = _values_at(service, "20260426", "gross_margin_chg")
        # 修订前毛利率 (200-160)/200=0.2；修订后 (200-150)/200=0.25
        # 同比期 20241231 不在表内 → 毛利率变化缺失，但 ocf_to_ni 可验修订传导
        ocf_before = _values_at(service, "20260415", "ocf_to_ni")
        ocf_after = _values_at(service, "20260426", "ocf_to_ni")
        assert ocf_before["600002.SH"] == pytest.approx(4.0 / 8.0)
        assert ocf_after["600002.SH"] == pytest.approx(4.0 / 9.0)  # 修订后净利 9
        assert "600002.SH" not in before or before["600002.SH"] != after.get("600002.SH")

    def test_report_type_filter(self, service):
        # report_type=2（单季）行必须被过滤，否则 600002 会切到 20260331
        values = _values_at(service, "20260510", "accrual_ratio")
        # 600002 最新已知报告仍是年报（单季行被滤掉）
        assert values.get("600002.SH") == pytest.approx((9.0 - 4.0) / 800.0)


class TestMissingGuards:
    def test_missing_prev_year_factor_absent(self, service):
        # 同比期报告不在表内 → 变化类因子缺失，不造假 0
        values = _values_at(service, "20260421", "gross_margin_chg")
        assert values == {}
        values = _values_at(service, "20260421", "roe_chg")
        assert values == {}

    def test_zero_denominator_missing(self, tmp_path):
        income = pd.DataFrame([
            _income_row("600003.SH", "20260410", "20251231", revenue=100.0, oper_cost=50.0,
                        profit=0.0),
            _income_row("600003.SH", "20250410", "20241231", revenue=90.0, oper_cost=45.0,
                        profit=5.0),
        ])
        balance = pd.DataFrame([
            _balance_row("600003.SH", "20260410", "20251231", assets=500.0, liab=250.0,
                         equity=250.0),
            _balance_row("600003.SH", "20250410", "20241231", assets=480.0, liab=240.0,
                         equity=240.0),
        ])
        cash = pd.DataFrame([
            _cash_row("600003.SH", "20260410", "20251231", cfo=8.0),
            _cash_row("600003.SH", "20250410", "20241231", cfo=6.0),
        ])
        _write_statement(tmp_path, "income_statement", income)
        _write_statement(tmp_path, "balance_sheet", balance)
        _write_statement(tmp_path, "cash_flow", cash)

        service = FundamentalPitService(data_dir=str(tmp_path))
        ocf = _values_at(service, "20260501", "ocf_to_ni")
        assert ocf == {}  # 净利润 0 → 现金转化缺失
        accrual = _values_at(service, "20260501", "accrual_ratio")
        assert accrual["600003.SH"] == pytest.approx((0.0 - 8.0) / 500.0)

    def test_leverage_chg_computed_when_prev_exists(self, tmp_path):
        # 完整同比：杠杆变化 = 当期负债率 - 上年同期负债率
        income = pd.DataFrame([
            _income_row("600004.SH", "20260410", "20251231", revenue=100.0, oper_cost=60.0,
                        profit=10.0),
            _income_row("600004.SH", "20250410", "20241231", revenue=90.0, oper_cost=54.0,
                        profit=9.0),
        ])
        balance = pd.DataFrame([
            _balance_row("600004.SH", "20260410", "20251231", assets=1000.0, liab=500.0,
                         equity=500.0),
            _balance_row("600004.SH", "20250410", "20241231", assets=900.0, liab=360.0,
                         equity=540.0),
        ])
        cash = pd.DataFrame([
            _cash_row("600004.SH", "20260410", "20251231", cfo=12.0),
            _cash_row("600004.SH", "20250410", "20241231", cfo=9.0),
        ])
        _write_statement(tmp_path, "income_statement", income)
        _write_statement(tmp_path, "balance_sheet", balance)
        _write_statement(tmp_path, "cash_flow", cash)

        service = FundamentalPitService(data_dir=str(tmp_path))
        frame = service.compute_for_date("20260501")
        by_factor = frame.set_index(["factor_id", "ts_code"])["factor_value"]
        assert by_factor[("leverage_chg", "600004.SH")] == pytest.approx(0.5 - 0.4)
        assert by_factor[("gross_margin_chg", "600004.SH")] == pytest.approx(0.4 - 0.4)
        assert by_factor[("roe_chg", "600004.SH")] == pytest.approx(10 / 500 - 9 / 540)
        assert by_factor[("asset_turnover_chg", "600004.SH")] == pytest.approx(0.1 - 0.1)


class TestComputeAndSave:
    def test_lands_standardized(self, service, tmp_path):
        from app.services.factor_engine import FactorEngine
        from app.services.parquet_state_store import ParquetStateStore

        engine = FactorEngine(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
        result = service.compute_and_save("20260426", engine=engine)
        assert "error" not in result
        assert result["trade_date"] == "20260426"

        values = engine.factor_repo.get_values(
            factor_ids=list(FUNDAMENTAL_PIT_FACTOR_IDS), trade_date="20260426")
        assert not values.empty
        assert values["percentile_rank"].notna().all()
        assert values["z_score"].notna().all()
