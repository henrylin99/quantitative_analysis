from pathlib import Path


def test_homepage_portfolio_card_matches_current_scope():
    html = Path("app/templates/index.html").read_text(encoding="utf-8")

    assert "查看真实组合、维护持仓并保存优化结果" in html
    assert "智能构建和优化投资组合" not in html


def test_realtime_analysis_tab_leads_avoid_full_capability_claims():
    html = Path("app/templates/realtime_analysis/index.html").read_text(encoding="utf-8")

    assert "当前开放多周期技术指标查看与计算入口。" in html
    assert "当前开放风险计算、预警和止损止盈相关入口。" in html
    assert "当前开放已接通的推送管理入口，未开放项会明确标识。" in html
    assert "强大的技术指标计算和分析引擎" not in html
    assert "全面的投资组合风险管理系统" not in html
    assert "高性能的实时数据推送系统" not in html


def test_realtime_analysis_monitor_and_signal_tabs_mark_partial_scope():
    html = Path("app/templates/realtime_analysis/index.html").read_text(encoding="utf-8")

    assert "当前提供监控页面入口，实际展示内容以当前页面返回结果为准。" in html
    assert "当前提供信号分析入口，策略覆盖范围和结果解释以实际页面为准。" in html
    assert "全方位的实时市场监控系统" not in html
    assert "支持8种经典交易策略" not in html
    assert "智能融合多个策略信号，通过加权计算生成最终交易建议" not in html


def test_realtime_analysis_websocket_tab_avoids_performance_promises():
    html = Path("app/templates/realtime_analysis/index.html").read_text(encoding="utf-8")

    assert "推送频率、并发能力和恢复机制以后端当前实现为准。" in html
    assert "毫秒级数据推送，确保信息实时性" not in html
    assert "支持数千并发连接" not in html
    assert "自动重连和故障恢复" not in html


def test_realtime_analysis_monitor_and_indicator_sections_avoid_feature_checklist_overclaim():
    html = Path("app/templates/realtime_analysis/index.html").read_text(encoding="utf-8")

    assert "刷新频率、阈值和图表范围以当前监控页实现为准。" in html
    assert "指标范围、结果存储和扩展分析能力以实际页面为准。" in html
    assert "30秒自动刷新" not in html
    assert "智能异动评分" not in html
    assert "历史数据回测" not in html
    assert "统计分析报告" not in html
