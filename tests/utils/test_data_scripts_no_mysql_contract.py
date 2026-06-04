from pathlib import Path

import pytest

pytestmark = pytest.mark.module_data_jobs


SCRIPT_PATHS = [
    "app/utils/stock_basic.py",
    "app/utils/stock_company.py",
    "app/utils/trade_calendar.py",
    "app/utils/income_statement.py",
    "app/utils/balance_sheet.py",
    "app/utils/cash_flow.py",
    "app/utils/moneyflow.py",
    "app/utils/moneyflow_ths.py",
    "app/utils/cyq_perf.py",
    "app/utils/stk_factor.py",
    "app/utils/ma_calculator.py",
    "app/utils/baostock_daily.py",
    "app/utils/daily_history_by_code.py",
    "app/utils/min5.py",
    "app/utils/min15.py",
    "app/utils/min30.py",
    "app/utils/min60.py",
    "app/utils/daily_basic.py",
    "app/utils/daily_history_by_date.py",
]


def test_remaining_data_scripts_do_not_use_mysql_connectors():
    repo_root = Path(__file__).resolve().parents[2]
    offenders = []

    for rel_path in SCRIPT_PATHS:
        text = (repo_root / rel_path).read_text(encoding="utf-8")
        if "connect_to_mysql(" in text:
            offenders.append(rel_path)

    assert offenders == []
