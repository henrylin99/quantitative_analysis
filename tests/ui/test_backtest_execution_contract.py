from pathlib import Path

import pytest

pytestmark = pytest.mark.module_backtest


def test_backtest_template_consumes_execution_assumption_fields():
    html = Path("app/templates/ml_factor/backtest.html").read_text(encoding="utf-8")

    assert "const executionAssumptions = data.execution_assumptions || {};" in html
    assert "const tradeConstraints = data.trade_constraints || {};" in html
    assert "const runId = data.run_id || '--';" in html
    assert "backtestRunId" in html
