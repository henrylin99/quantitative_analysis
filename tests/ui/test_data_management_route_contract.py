from pathlib import Path


def test_navigation_exposes_data_management_as_separate_menu():
    html = Path("app/templates/base.html").read_text(encoding="utf-8")

    assert "href=\"/data-management\"" in html
    assert ">数据管理<" in html


def test_realtime_data_route_redirects_to_data_management():
    route_file = Path("app/routes/realtime_analysis_routes.py").read_text(encoding="utf-8")

    assert "def data()" in route_file
    assert "redirect(url_for('main.data_management'))" in route_file
