from unittest.mock import patch



def test_analysis_endpoints_return_page_aligned_payloads(app):
    client = app.test_client()

    with (
        patch(
            "app.api.ml_factor_api._build_model_performance_summary",
            return_value={
                "total_models": 2,
                "best_r2": 0.82,
                "performance_data": [{"date": "2024-06-01", "train_r2": 0.7, "test_r2": 0.68, "mae": 0.12}],
                "comparison_data": [{"model_type": "random_forest", "r2_score": 0.82, "mae_score": 0.12}],
            },
        ),
        patch(
            "app.api.ml_factor_api._build_factor_effectiveness_summary",
            return_value={
                "active_factors": 3,
                "importance_data": [{"factor_name": "alpha", "importance": 0.91, "correlation": 0.25}],
                "factor_stats": [{"factor_name": "alpha", "importance": 0.91, "correlation": 0.25}],
            },
        ),
        patch(
            "app.api.ml_factor_api._build_portfolio_performance_summary",
            return_value={
                "portfolio_count": 1,
                "annual_return": 12.34,
                "max_drawdown": -4.56,
                "sharpe_ratio": 1.23,
                "win_rate": 58.0,
                "performance_data": [{"date": "2024-06-01", "portfolio_return": 1.0, "benchmark_return": 0.5}],
                "sector_distribution": {"科技": 60.0},
                "portfolio_metrics": [],
            },
        ),
        patch(
            "app.api.ml_factor_api._build_risk_analysis_summary",
            return_value={"risk_data": [{"name": "科技", "value": 60.0}]},
        ),
        patch(
            "app.api.ml_factor_api._build_analysis_report",
            return_value={
                "generated_at": "2024-06-04T00:00:00",
                "model_performance": {"total_models": 2},
                "factor_effectiveness": {"active_factors": 3},
                "portfolio_performance": {"portfolio_count": 1},
                "risk_analysis": {"risk_data": [{"name": "科技", "value": 60.0}]},
            },
        ),
    ):
        response = client.get("/api/ml-factor/analysis/model-performance")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["total_models"] == 2
        assert data["best_r2"] == 0.82

        response = client.get("/api/ml-factor/analysis/factor-effectiveness")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["active_factors"] == 3
        assert data["factor_stats"][0]["factor_name"] == "alpha"

        response = client.get("/api/ml-factor/analysis/portfolio-performance")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["portfolio_count"] == 1
        assert data["annual_return"] == 12.34

        response = client.get("/api/ml-factor/analysis/risk-analysis")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["risk_data"][0]["name"] == "科技"

        response = client.post("/api/ml-factor/analysis/generate-report")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["report"]["model_performance"]["total_models"] == 2

        response = client.get("/api/ml-factor/analysis/export-report")
        assert response.status_code == 200
        assert "attachment; filename=ml_factor_analysis_report_" in response.headers["Content-Disposition"]
        assert b'"generated_at": "2024-06-04T00:00:00"' in response.data


def test_quantile_portfolio_endpoint_returns_payload(app):
    client = app.test_client()

    fake = type(
        "FakeAnalyzer",
        (),
        {"quantile_portfolio_backtest": staticmethod(
            lambda **kwargs: {
                "factor_id": kwargs["factor_id"],
                "n_periods": 3,
                "nav_long_short": [1.0, 1.01, 1.02],
            }
        )},
    )

    with patch(
        "app.api.ml_factor_api.get_factor_analyzer", return_value=fake,
    ):
        response = client.post(
            "/api/ml-factor/factor/analysis/quantile-portfolio",
            json={"factor_id": "momentum_20d", "holding_days": 20,
                  "n_quantiles": 5, "cost_bps": 10},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["factor_id"] == "momentum_20d"
        assert data["n_periods"] == 3


def test_quantile_portfolio_endpoint_requires_factor(app):
    client = app.test_client()
    response = client.post(
        "/api/ml-factor/factor/analysis/quantile-portfolio", json={},
    )
    assert response.status_code == 400
    assert "factor_id" in response.get_json()["error"]


def test_ic_decay_endpoint_returns_payload(app):
    client = app.test_client()
    fake = type("FakeAnalyzer", (), {"ic_decay_analysis": staticmethod(
        lambda **kwargs: {"factor_id": kwargs["factor_id"],
                          "ic_by_horizon": {"5": {"ic_mean": 0.05}}})})
    with patch("app.api.ml_factor_api.get_factor_analyzer", return_value=fake):
        response = client.post(
            "/api/ml-factor/factor/analysis/ic-decay",
            json={"factor_id": "momentum_20d", "forward_periods": [1, 5]},
        )
        assert response.status_code == 200
        assert response.get_json()["ic_by_horizon"]["5"]["ic_mean"] == 0.05


def test_ic_decay_endpoint_requires_factor(app):
    client = app.test_client()
    response = client.post("/api/ml-factor/factor/analysis/ic-decay", json={})
    assert response.status_code == 400


def test_screening_endpoints_contract(app):
    client = app.test_client()
    fake = type("FakeScreening", (), {
        "screen_factors": staticmethod(lambda **kwargs: {
            "n_factors": 2, "factors": {"f1": {"ic_mean": 0.1}}}),
        "list_screenings": staticmethod(lambda **kwargs: [
            {"factor_id": "f1", "status": "evaluated"}]),
        "set_status": staticmethod(lambda **kwargs: {
            "factor_id": kwargs["factor_id"], "status": kwargs["status"]}),
        "accepted_factors": staticmethod(lambda: ["f1"]),
        "select_low_collinearity": staticmethod(lambda **kwargs: {
            "kept": kwargs["factor_ids"], "dropped": []}),
    })
    with patch("app.api.ml_factor_api._get_screening_service",
               return_value=fake):
        r = client.post("/api/ml-factor/factor/screening/run",
                        json={"save": False})
        assert r.status_code == 200
        assert r.get_json()["n_factors"] == 2

        r = client.get("/api/ml-factor/factor/screening/list?status=evaluated")
        assert r.get_json()["count"] == 1

        r = client.post("/api/ml-factor/factor/screening/status",
                        json={"factor_id": "f1", "status": "accepted"})
        assert r.get_json()["status"] == "accepted"

        r = client.post("/api/ml-factor/factor/screening/status",
                        json={"factor_id": "f1"})
        assert r.status_code == 400

        r = client.get("/api/ml-factor/factor/screening/accepted")
        assert r.get_json()["factor_ids"] == ["f1"]

        r = client.post("/api/ml-factor/factor/screening/decorrelate",
                        json={"factor_ids": ["f1", "f2"]})
        assert r.get_json()["kept"] == ["f1", "f2"]

        r = client.post("/api/ml-factor/factor/screening/decorrelate",
                        json={"factor_ids": ["f1"]})
        assert r.status_code == 400


def test_quality_report_endpoint(app):
    client = app.test_client()
    fake = type("FakeMonitor", (), {"quality_report": staticmethod(
        lambda **kwargs: {"n_alerts": 1, "alerts": [
            {"type": "coverage_drop", "factor_id": "alpha_138"}]})})
    with patch("app.services.factor_screening.FactorQualityMonitor",
               return_value=fake):
        r = client.get("/api/ml-factor/factor/quality-report")
        assert r.status_code == 200
        assert r.get_json()["n_alerts"] == 1


def test_prediction_track_endpoint(app):
    client = app.test_client()
    fake = type("FakeTracker", (), {"track": staticmethod(lambda **kwargs: {
        "models": {"mA": {"summary": {"spread_mean": 0.01}}}})})
    with patch("app.services.prediction_tracking.PredictionTrackingService",
               return_value=fake):
        r = client.post("/api/ml-factor/predictions/track", json={})
        assert r.status_code == 200
        assert r.get_json()["models"]["mA"]["summary"]["spread_mean"] == 0.01


def test_portfolio_attribution_endpoint(app):
    client = app.test_client()
    fake = type("FakeAttr", (), {"attribute": staticmethod(lambda **kwargs: {
        "portfolio_id": kwargs["portfolio_id"],
        "attribution": {"perfect": {"beta": 0.5}}})})
    with patch("app.services.portfolio_attribution."
               "PortfolioAttributionService", return_value=fake):
        r = client.post("/api/ml-factor/portfolio/p1/attribution", json={})
        assert r.status_code == 200
        assert r.get_json()["attribution"]["perfect"]["beta"] == 0.5


def test_model_snapshot_endpoints(app):
    client = app.test_client()
    fake = type("FakeSnapRepo", (), {
        "list_snapshots": staticmethod(lambda model_id=None: [
            {"snapshot_id": 1, "model_id": model_id,
             "metrics": {"test_r2": 0.2}}]),
        "compare_models": staticmethod(lambda model_ids: {
            "models": [{"model_id": "m2", "metrics": {"test_r2": 0.2}}]}),
    })
    with patch("app.services.model_experiments.TrainingSnapshotRepository",
               return_value=fake):
        r = client.get("/api/ml-factor/models/m2/snapshots")
        assert r.status_code == 200
        assert r.get_json()["count"] == 1

        r = client.post("/api/ml-factor/models/compare",
                        json={"model_ids": ["m2"]})
        assert r.get_json()["models"][0]["metrics"]["test_r2"] == 0.2

        r = client.post("/api/ml-factor/models/compare", json={})
        assert r.status_code == 400
