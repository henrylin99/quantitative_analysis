from pathlib import Path


def test_report_management_template_exposes_management_sections():
    html = Path("app/templates/realtime_analysis/report_management.html").read_text(encoding="utf-8")

    assert "模板管理" in html
    assert "订阅管理" in html
    assert "统计分析" in html
    assert "createTemplateModal" in html
    assert "createSubscriptionModal" in html
    assert "function loadSubscriptions()" in html
    assert "function loadStatistics()" in html
    assert "function createTemplate()" in html
    assert "function createSubscription()" in html


def test_report_management_template_describes_full_available_scope():
    html = Path("app/templates/realtime_analysis/report_management.html").read_text(encoding="utf-8")

    assert "管理分析报告、模板和订阅" in html
    assert "当前页面仅开放报告列表与报告生成能力" not in html


def test_report_management_template_loads_template_and_subscription_data():
    html = Path("app/templates/realtime_analysis/report_management.html").read_text(encoding="utf-8")

    assert "loadTemplates()" in html
    assert "renderTemplates()" in html
    assert "updateTemplateSelects()" in html
    assert "totalTemplates" in html
    assert "totalSubscriptions" in html
    assert "subscriptionTemplateId" in html
