def test_portfolio_optimize_rejects_unsupported_industry_constraints(app):
    client = app.test_client()

    response = client.post(
        "/api/ml-factor/portfolio/optimize",
        json={
            "expected_returns": {"000001.SZ": 0.1, "000002.SZ": 0.08},
            "method": "equal_weight",
            "constraints": {
                "industry_constraints": {"银行": {"max_weight": 0.3}}
            },
        },
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "industry_constraints" in data["error"]
