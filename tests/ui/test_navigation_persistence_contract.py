import pytest


@pytest.mark.parametrize(
    "route",
    [
        "/data-management",
        "/realtime-analysis/indicators",
        "/realtime-analysis/signals",
        "/realtime-analysis/monitor",
        "/realtime-analysis/risk",
        "/realtime-analysis/reports",
        "/realtime-analysis/websocket",
    ],
)
def test_navigation_remains_visible_on_data_and_realtime_pages(app, route):
    client = app.test_client()

    response = client.get(route)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "navbar-financial" in html
    assert 'href="/data-management"' in html
    assert 'href="/realtime-analysis/indicators"' in html
