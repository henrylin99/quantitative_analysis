from app.services.realtime_report_generator import RealtimeReportGenerator


def test_report_generator_requires_explicit_portfolio_id_for_portfolio_analysis():
    generator = RealtimeReportGenerator()

    data = generator._collect_report_data("portfolio_analysis", {})

    assert data["error"] == "portfolio_id is required for portfolio_analysis"


def test_report_generator_requires_explicit_portfolio_id_for_risk_assessment():
    generator = RealtimeReportGenerator()

    data = generator._collect_report_data("risk_assessment", {})

    assert data["error"] == "portfolio_id is required for risk_assessment"
