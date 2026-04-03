from pathlib import Path


def test_report_management_template_hides_todo_sections():
    html = Path("app/templates/realtime_analysis/report_management.html").read_text(encoding="utf-8")

    assert "模板管理" not in html
    assert "订阅管理" not in html
    assert "统计分析" not in html
    assert "createTemplateModal" not in html
    assert "createSubscriptionModal" not in html
    assert "function loadSubscriptions()" not in html
    assert "function loadStatisticsOverview()" not in html
    assert "function loadStatistics()" not in html
    assert "function createTemplate()" not in html
    assert "function createSubscription()" not in html
