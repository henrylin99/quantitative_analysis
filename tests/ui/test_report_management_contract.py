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


def test_report_management_template_describes_only_available_scope():
    html = Path("app/templates/realtime_analysis/report_management.html").read_text(encoding="utf-8")

    assert "管理分析报告、模板和订阅" not in html
    assert "当前页面仅开放报告列表与报告生成能力" in html


def test_report_management_template_does_not_load_hidden_template_or_subscription_data():
    html = Path("app/templates/realtime_analysis/report_management.html").read_text(encoding="utf-8")

    assert "loadTemplates()" not in html
    assert "renderTemplates()" not in html
    assert "updateTemplateSelects()" not in html
    assert "totalTemplates" not in html
    assert "totalSubscriptions" not in html
    assert "subscriptionTemplateId" not in html
