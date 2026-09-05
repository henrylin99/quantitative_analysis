"""financial_fuyao / stock_basic_fuyao 合约测试：披露期推导、分区合并、主流程。"""

from datetime import date

import pandas as pd
import pytest

from app.services.data_jobs.registry import JobRegistry
from app.utils import financial_fuyao, stock_basic_fuyao
from app.utils.data_sources.fuyao_normalize import financial_items_to_frame

pytestmark = pytest.mark.module_data_jobs


# ---- 披露期推导 ----

def test_expected_latest_period_follows_deadlines():
    assert financial_fuyao.expected_latest_period(date(2026, 9, 5)) == "20260630"   # H1 截止 8/31 已过
    assert financial_fuyao.expected_latest_period(date(2026, 8, 30)) == "20260331"  # H1 截止未到
    assert financial_fuyao.expected_latest_period(date(2026, 5, 1)) == "20260331"   # Q1 截止 4/30 已过
    assert financial_fuyao.expected_latest_period(date(2026, 1, 5)) == "20250930"   # FY 截止次年 4/30
    assert financial_fuyao.expected_latest_period(date(2026, 4, 29)) == "20250930"  # Q1 截止前一天
    assert financial_fuyao.expected_latest_period(date(2026, 4, 30)) == "20260331"  # 截止日当天即视为已披露


def test_resolve_fetch_periods_includes_correction_window():
    periods = financial_fuyao.resolve_fetch_periods("20260331", "20260630")
    assert periods == ["20260331", "20260630"]
    # 冷启动：5 年窗口
    assert len(financial_fuyao.resolve_fetch_periods(None, "20260630")) >= 18


# ---- 分区合并 ----

def _income_frame(ts_code, end_date, ann_date, revenue):
    return financial_items_to_frame(
        [{"thscode": ts_code, "period_end_ms": _ms(end_date), "report_date_ms": _ms(ann_date),
          "operating_income": revenue}],
        "income", ts_code,
    )


def _ms(ymd):
    from datetime import datetime

    return int((datetime.strptime(ymd, "%Y%m%d") - datetime(1970, 1, 1)).total_seconds() * 1000) - 8 * 3600 * 1000


def test_merge_partition_keeps_latest_announcement():
    existing = _income_frame("600000.SH", "20260630", "20260820", 100.0)
    # 更正公告（更晚的 ann_date）应覆盖旧值
    restatement = _income_frame("600000.SH", "20260630", "20260901", 200.0)
    merged = financial_fuyao._merge_partition(existing, restatement)
    assert len(merged) == 1
    assert merged.iloc[0]["revenue"] == 200.0

    # 更旧的公告不应覆盖已有值
    stale = _income_frame("600000.SH", "20260630", "20260701", 50.0)
    merged = financial_fuyao._merge_partition(existing, stale)
    assert merged.iloc[0]["revenue"] == 100.0

    # 新标的追加
    other = _income_frame("000001.SZ", "20260630", "20260825", 10.0)
    merged = financial_fuyao._merge_partition(existing, other)
    assert len(merged) == 2


def test_merge_partition_with_empty_existing():
    new = _income_frame("600000.SH", "20260630", "20260820", 100.0)
    assert len(financial_fuyao._merge_partition(None, new)) == 1


# ---- 脚本主流程 ----

class _FakeFuyaoClient:
    def __init__(self, statements):
        self.statements = statements  # table -> {ts_code: items}

    def financial_statement(self, table, ts_code, limit=20, period="quarterly"):
        return self.statements.get(table, {}).get(ts_code, [])

    def snapshot_all(self, max_pages=50):
        return [], None


def test_financial_main_writes_partitions(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATA_JOB_FULL_REFRESH", raising=False)
    items = [{"thscode": "600000.SH", "period_end_ms": _ms("20260630"),
              "report_date_ms": _ms("20260820"), "operating_income": 100.0}]
    client = _FakeFuyaoClient({
        "income": {"600000.SH": items},
        "balance_sheet": {"600000.SH": [dict(items[0], assets_total=50.0)]},
        "cash_flow": {"600000.SH": [dict(items[0], act_cash_flow_net=5.0)]},
    })
    monkeypatch.setattr(financial_fuyao, "FuyaoClient", lambda: client)
    monkeypatch.setattr(financial_fuyao, "all_stock_codes", lambda client=None: ["600000.SH"])

    exit_code = financial_fuyao.main()

    assert exit_code == 0
    for table in ("income_statement", "balance_sheet", "cash_flow"):
        path = tmp_path / table / "year=2026" / "month=06" / "day=30" / "data.parquet"
        assert path.exists(), table
        df = pd.read_parquet(path)
        assert df.iloc[0]["ts_code"] == "600000.SH"
        assert df.iloc[0]["end_date"] == "20260630"


def test_financial_main_skips_when_local_covers_expected(monkeypatch, tmp_path, capsys):
    (tmp_path / "income_statement" / "year=2026" / "month=06" / "day=30").mkdir(parents=True)
    (tmp_path / "balance_sheet" / "year=2026" / "month=06" / "day=30").mkdir(parents=True)
    (tmp_path / "cash_flow" / "year=2026" / "month=06" / "day=30").mkdir(parents=True)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = _FakeFuyaoClient({})
    monkeypatch.setattr(financial_fuyao, "FuyaoClient", lambda: client)
    monkeypatch.setattr(financial_fuyao, "all_stock_codes", lambda client=None: ["600000.SH"])

    exit_code = financial_fuyao.main()

    assert exit_code == 0
    out = capsys.readouterr().out
    assert out.count("跳过") == 3


def test_financial_main_fails_when_no_symbols(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATA_JOB_FULL_REFRESH", raising=False)
    client = _FakeFuyaoClient({})
    monkeypatch.setattr(financial_fuyao, "FuyaoClient", lambda: client)
    monkeypatch.setattr(financial_fuyao, "all_stock_codes", lambda client=None: [])

    assert financial_fuyao.main() == 1


# ---- stock_basic_fuyao ----

def test_stock_basic_main_merges_and_saves(monkeypatch, tmp_path):
    import os

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    existing = pd.DataFrame([
        {"ts_code": "000001.SZ", "symbol": "000001", "name": "旧名称", "industry": "银行", "list_status": "L"},
    ])
    existing.to_parquet(tmp_path / "stock_basic.parquet")

    rows = [{"thscode": "000001.SZ", "name": "平安银行"},
            {"thscode": "301999.SZ", "name": "新股"}]
    client = _FakeFuyaoClient({})
    client.snapshot_all = lambda max_pages=50: (rows, 123)
    monkeypatch.setattr(stock_basic_fuyao, "FuyaoClient", lambda: client)

    exit_code = stock_basic_fuyao.main()

    assert exit_code == 0
    df = pd.read_parquet(tmp_path / "stock_basic.parquet")
    assert len(df) == 2
    by_code = df.set_index("ts_code")
    assert by_code.loc["000001.SZ", "name"] == "平安银行"
    assert by_code.loc["000001.SZ", "industry"] == "银行"
    assert by_code.loc["301999.SZ", "list_status"] == "L"
    assert os.environ.get("DATA_DIR") == str(tmp_path)


def test_registry_metadata_financial_fuyao():
    registry = JobRegistry()
    assert registry.get_job("financial_fuyao").source_name == "fuyao"
    assert registry.get_job("stock_basic_fuyao").source_name == "fuyao"


def test_read_existing_partition_falls_back_to_default_data_root(monkeypatch, tmp_path):
    """回归：data_dir=None 时必须与 save_to_parquet 同源回退（DATA_DIR→项目 data/），
    否则分块 flush 各自整分区覆盖，静默丢掉之前块的数据（PR #16 review #1）。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    end_date = "20260331"
    table = "income_statement"

    from app.utils.parquet_writer import save_to_parquet

    existing = pd.DataFrame(
        {"ts_code": ["600000.SH"], "end_date": [end_date], "ann_date": ["20260420"]}
    )
    save_to_parquet(existing, trade_date=end_date, table=table)

    # save_to_parquet 写入的分区，_read_existing_partition 必须能读到
    found = financial_fuyao._read_existing_partition(table, end_date, data_dir=None)
    assert found is not None
    assert list(found["ts_code"]) == ["600000.SH"]

    # 显式 data_dir 仍然生效（指向别处时读不到该分区）
    assert financial_fuyao._read_existing_partition(table, end_date, data_dir=str(tmp_path / "elsewhere")) is None
