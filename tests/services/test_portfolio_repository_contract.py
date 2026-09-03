from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository


def test_portfolio_repository_soft_delete_preserves_metrics_contract(tmp_path):
    repo = PortfolioRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))

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

    assert repo.get_position_by_stock("p1", "000001.SZ")["ts_code"] == "000001.SZ"
    metrics = repo.calculate_metrics("p1")
    assert metrics["total_positions"] == 2
    assert metrics["sector_distribution"]["银行"] > 0
    assert repo.deactivate_portfolio("p1") == 2
    assert repo.list_positions("p1") == []
