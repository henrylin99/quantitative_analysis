from unittest.mock import patch

import pytest


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
