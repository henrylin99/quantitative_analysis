from pathlib import Path
from unittest.mock import patch


def test_navigation_exposes_data_management_as_separate_menu():
    html = Path("app/templates/base.html").read_text(encoding="utf-8")

    assert "href=\"/data-management\"" in html
    assert ">数据管理<" in html


def test_realtime_data_route_redirects_to_data_management():
    route_file = Path("app/routes/realtime_analysis_routes.py").read_text(encoding="utf-8")

    assert "def data()" in route_file
    assert "redirect(url_for('main.data_management'))" in route_file


def test_data_management_route_embeds_initialization_status_payload(app):
    client = app.test_client()
    fake_report = {
        "entrypoint": "run.py",
        "database": {
            "connected": True,
            "ok": False,
            "missing_tables": ["stock_basic"],
            "empty_tables": [],
            "next_actions": ["测试下一步动作"],
        },
        "data_jobs": {"execution_mode": "inline"},
    }

    with patch("app.main.views.inspect_data_management_status", return_value=fake_report):
        response = client.get("/data-management")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "测试下一步动作" in html
    assert "\"missing_tables\": [\"stock_basic\"]" in html
