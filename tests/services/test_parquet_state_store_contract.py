import pytest

from app.services.parquet_state_store import (
    BacktestRepository,
    FactorRepository,
    ModelRepository,
    ParquetStateStore,
    PortfolioRepository,
)


def test_parquet_state_store_creates_isolated_files(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "state"))

    assert store.path_for("factor_values").name == "factor_values.parquet"
    assert store.path_for("backtest_runs").parent == tmp_path / "state"


def test_factor_repository_round_trips_definitions_and_values(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    repo = FactorRepository(store)

    repo.upsert_definition(
        {
            "factor_id": "momentum_5d",
            "factor_name": "5日动量",
            "factor_formula": "close.pct_change(5)",
            "factor_type": "technical",
            "description": "demo",
            "params": {"window": 5},
        }
    )

    values = repo.save_values(
        __import__("pandas").DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "momentum_5d", "factor_value": 1.2},
                {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "factor_id": "momentum_5d", "factor_value": 2.2},
            ]
        )
    )

    assert values == 2
    assert [item["factor_id"] for item in repo.list_definitions()] == ["momentum_5d"]

    frame = repo.get_values(factor_ids=["momentum_5d"], trade_date="2024-06-04")
    assert frame["ts_code"].tolist() == ["000001.SZ", "000002.SZ"]

    repo.save_values(
        __import__("pandas").DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "momentum_5d", "factor_value": 9.9},
            ]
        )
    )
    frame = repo.get_values(factor_ids=["momentum_5d"], trade_date="2024-06-04")
    # save_values 落库统一 float32，回读值与 float64 字面量只能近似相等
    assert frame.loc[frame["ts_code"] == "000001.SZ", "factor_value"].iloc[0] == pytest.approx(9.9)


def test_model_repository_round_trips_definitions_and_predictions(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    repo = ModelRepository(store)

    repo.upsert_definition(
        {
            "model_id": "model_a",
            "model_name": "模型A",
            "model_type": "random_forest",
            "factor_list": ["momentum_5d", "volatility_20d"],
            "target_type": "return_5d",
            "model_params": {"n_estimators": 10},
            "training_config": {"test_size": 0.2},
        }
    )

    repo.save_predictions(
        __import__("pandas").DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "model_id": "model_a", "predicted_return": 0.1, "rank_score": 1},
                {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "model_id": "model_a", "predicted_return": 0.2, "rank_score": 2},
            ]
        )
    )

    definitions = repo.list_definitions()
    assert definitions[0]["factor_list"] == ["momentum_5d", "volatility_20d"]

    predictions = repo.get_predictions(model_id="model_a", trade_date="2024-06-04")
    assert predictions["ts_code"].tolist() == ["000001.SZ", "000002.SZ"]

    repo.delete_definition("model_a")
    assert repo.get_definition("model_a")["is_active"] is False
    assert repo.get_predictions(model_id="model_a").empty


def test_portfolio_repository_supports_soft_delete_and_metrics(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    repo = PortfolioRepository(store)

    repo.create_position(
        {
            "portfolio_id": "p1",
            "ts_code": "000001.SZ",
            "position_size": 100,
            "avg_cost": 10,
            "current_price": 11,
            "market_value": 1100,
            "unrealized_pnl": 100,
            "weight": 55,
            "sector": "银行",
            "var_1d": 1.5,
            "var_5d": 2.5,
        }
    )
    repo.create_position(
        {
            "portfolio_id": "p1",
            "ts_code": "000002.SZ",
            "position_size": 50,
            "avg_cost": 20,
            "current_price": 22,
            "market_value": 1100,
            "unrealized_pnl": 100,
            "weight": 45,
            "sector": "科技",
            "var_1d": 1.0,
            "var_5d": 2.0,
        }
    )

    positions = repo.list_positions("p1")
    assert [position["ts_code"] for position in positions] == ["000001.SZ", "000002.SZ"]
    assert repo.get_position_by_stock("p1", "000001.SZ")["ts_code"] == "000001.SZ"

    metrics = repo.calculate_metrics("p1")
    assert metrics["total_positions"] == 2
    assert metrics["sector_distribution"]["银行"] > 0

    assert repo.deactivate_portfolio("p1") == 2
    assert repo.list_positions("p1") == []


def test_backtest_repository_allocates_ids_and_round_trips_summary(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    repo = BacktestRepository(store)

    run = repo.create_run(
        {"strategy": "mean_reversion"},
        "2024-01-01",
        "2024-01-31",
        1_000_000,
        "monthly",
    )
    assert run["id"] == 1

    fetched = repo.get_run(1)
    assert fetched["strategy_config"] == {"strategy": "mean_reversion"}

    updated = repo.update_summary(1, {"annual_return": 0.12, "sharpe": 1.3})
    assert updated["summary"] == {"annual_return": 0.12, "sharpe": 1.3}
    assert repo.list_runs()[0]["id"] == 1


def test_factor_values_replace_semantics_updates_factor_and_keeps_others(tmp_path):
    """整体替换合并：被替换因子旧值整组让位，其他因子与其他日期不动。"""
    import pandas as pd

    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    repo = FactorRepository(store)

    repo.save_values(pd.DataFrame([
        {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "f1", "factor_value": 1.0},
        {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "factor_id": "f1", "factor_value": 2.0},
        {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "f2", "factor_value": 7.0},
        {"ts_code": "000001.SZ", "trade_date": "2024-06-05", "factor_id": "f1", "factor_value": 3.0},
    ]))

    # 只带一只股票的 f1 新值：替换语义下另一只股票的 f1 旧值必须消失
    repo.save_values(
        pd.DataFrame([
            {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "f1", "factor_value": 9.9},
        ]),
        replace_factor_ids=["f1"],
    )

    frame = repo.get_values(trade_date="2024-06-04")
    f1 = frame[frame["factor_id"] == "f1"]
    assert f1["ts_code"].tolist() == ["000001.SZ"]
    assert f1["factor_value"].iloc[0] == pytest.approx(9.9)
    f2 = frame[frame["factor_id"] == "f2"]
    assert len(f2) == 1
    assert f2["factor_value"].iloc[0] == pytest.approx(7.0)

    # 未涉及的日期不受影响
    other_day = repo.get_values(trade_date="2024-06-05")
    assert len(other_day) == 1
    assert other_day["factor_value"].iloc[0] == pytest.approx(3.0)

    # 同一批入参内部重复键（防御路径）：保留最后一条
    repo.save_values(
        pd.DataFrame([
            {"ts_code": "000001.SZ", "trade_date": "2024-06-06", "factor_id": "f3", "factor_value": 1.0},
            {"ts_code": "000001.SZ", "trade_date": "2024-06-06", "factor_id": "f3", "factor_value": 2.0},
        ]),
        replace_factor_ids=["f3"],
    )
    dup_day = repo.get_values(trade_date="2024-06-06")
    assert len(dup_day) == 1
    assert dup_day["factor_value"].iloc[0] == pytest.approx(2.0)


def test_factor_coverage_filters_non_trading_day_partitions(tmp_path):
    """非交易日分区（杂散写入）不计入覆盖、也不算缺口；日历缺失时退化为全量统计。"""
    import pandas as pd

    store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    repo = FactorRepository(store)

    def write(factor_id, date):
        repo.save_values(
            pd.DataFrame([
                {"ts_code": "000001.SZ", "trade_date": date, "factor_id": factor_id, "factor_value": 1.0},
            ])
        )

    write("momentum_5d", "2024-06-04")   # 开市日，有值
    write("momentum_5d", "2024-06-06")   # 开市日，有值
    write("other_factor", "2024-06-06")  # 开市日，有值
    write("momentum_5d", "2024-06-05")   # 非交易日杂散写入

    # 交易日历放在 base_dir 同级（与生产 data/ 布局一致）
    pd.DataFrame({
        "exchange": ["SSE"] * 3,
        "cal_date": ["20240604", "20240605", "20240606"],
        "is_open": [1, 0, 1],
        "pretrade_date": ["20240603", "20240604", "20240604"],
    }).to_parquet(tmp_path / "stock_trade_calendar.parquet", index=False)

    cov = repo.get_factor_coverage(["momentum_5d", "other_factor"], "2024-06-01", "2024-06-30")
    momentum = cov["momentum_5d"]
    assert momentum["dates"] == 2
    assert momentum["missing_dates"] == []
    other = cov["other_factor"]
    assert other["dates"] == 1
    # 2024-06-04 开市但 other_factor 无值 → 缺口；2024-06-05 非交易日 → 不算缺口
    assert other["missing_dates"] == ["2024-06-04"]

    # 日历缺失：退化为全部分区参与统计（杂散分区重新计入，不算缺口但计入 dates）
    (tmp_path / "stock_trade_calendar.parquet").unlink()
    cov_fallback = repo.get_factor_coverage(["momentum_5d"], "2024-06-01", "2024-06-30")
    assert cov_fallback["momentum_5d"]["dates"] == 3
