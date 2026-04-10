import pytest

from app.services.backtest_engine import BacktestEngine

pytestmark = pytest.mark.module_backtest


def test_build_response_payload_includes_ui_ready_fields(monkeypatch):
    engine = BacktestEngine()
    monkeypatch.setattr(
        engine,
        "_get_stock_metadata",
        lambda ts_codes: {
            "000001.SZ": {"name": "平安银行", "industry": "银行"}
        },
    )

    result = engine._build_response_payload(
        strategy_config={"selection_method": "factor_based"},
        start_date="2024-01-02",
        end_date="2024-01-03",
        initial_capital=1000.0,
        final_value=1100.0,
        portfolio_values=[
            {"date": "2024-01-02", "total_value": 1000.0, "cash": 0.0, "positions_value": 1000.0},
            {"date": "2024-01-03", "total_value": 1100.0, "cash": 0.0, "positions_value": 1100.0},
        ],
        daily_returns=[0.1],
        daily_positions=[{"000001.SZ": 100}],
        daily_turnover=[0.0],
        performance_metrics={
            "annualized_return": 0.12,
            "max_drawdown": 0.05,
            "sharpe_ratio": 1.1,
            "volatility": 0.2,
            "win_rate": 1.0,
            "calmar_ratio": 2.4,
        },
        benchmark_returns=[
            {"date": "2024-01-02", "close": 100.0, "daily_return": 0.0, "cumulative_return": 0.0},
            {"date": "2024-01-03", "close": 101.0, "daily_return": 0.01, "cumulative_return": 0.01},
        ],
        final_prices={"000001.SZ": 11.0},
    )

    assert result["performance_metrics"]["annual_return"] == 0.12
    assert result["benchmark_returns"][0]["value"] == 1.0
    assert result["equity_curve"][1]["benchmark"] == 1.01
    assert result["positions"][0]["name"] == "平安银行"
    assert result["industry_distribution"][0]["name"] == "银行"
    assert "risk_metrics" in result
    assert "drawdown_series" in result
    assert "monthly_returns" in result


def test_build_response_payload_keeps_empty_ui_collections_explicit(monkeypatch):
    engine = BacktestEngine()
    monkeypatch.setattr(engine, "_get_stock_metadata", lambda ts_codes: {})

    result = engine._build_response_payload(
        strategy_config={"selection_method": "factor_based"},
        start_date="2024-01-02",
        end_date="2024-01-03",
        initial_capital=1000.0,
        final_value=1000.0,
        portfolio_values=[],
        daily_returns=[],
        daily_positions=[],
        daily_turnover=[],
        performance_metrics={},
        benchmark_returns=[],
        final_prices={},
    )

    assert result["equity_curve"] == []
    assert result["drawdown_series"] == []
    assert result["monthly_returns"] == []
    assert result["returns_distribution"] == []
    assert result["positions"] == []
    assert result["industry_distribution"] == []
    assert result["risk_metrics"] == {
        "var_95": None,
        "cvar_95": None,
        "beta": None,
        "alpha": None,
        "information_ratio": None,
        "calmar_ratio": None,
    }
