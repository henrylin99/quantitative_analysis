from pathlib import Path


def test_realtime_monitor_page_uses_neutral_refresh_toggle_copy():
    html = Path("app/templates/realtime_analysis/monitor.html").read_text(encoding="utf-8")

    assert "刷新开关（当前默认 30s）" in html
    assert "自动刷新 (30s)" not in html
