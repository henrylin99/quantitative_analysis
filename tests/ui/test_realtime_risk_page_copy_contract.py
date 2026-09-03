from pathlib import Path


def test_realtime_risk_page_marks_scope_as_current_entry():
    html = Path("app/templates/realtime_analysis/risk_management.html").read_text(encoding="utf-8")

    assert "当前提供风险计算、预警和止损止盈入口，结果以页面返回数据为准" in html
    assert "投资组合风险监控、预警管理和止损止盈控制" not in html


def test_realtime_risk_page_avoids_static_system_running_copy():
    html = Path("app/templates/realtime_analysis/risk_management.html").read_text(encoding="utf-8")

    assert "状态以后端刷新结果为准" in html
    assert "系统状态" not in html
    assert "运行中" not in html
