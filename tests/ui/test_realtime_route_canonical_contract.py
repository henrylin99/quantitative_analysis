from pathlib import Path


def test_realtime_routes_define_legacy_redirects_to_canonical_paths():
    route_file = Path("app/routes/realtime_analysis_routes.py").read_text(encoding="utf-8")

    assert "def risk_management_legacy()" in route_file
    assert "redirect(url_for('realtime_analysis_routes.risk'))" in route_file
    assert "def report_management_legacy()" in route_file
    assert "redirect(url_for('realtime_analysis_routes.reports'))" in route_file
    assert "def websocket_management_legacy()" in route_file
    assert "redirect(url_for('realtime_analysis_routes.websocket'))" in route_file
