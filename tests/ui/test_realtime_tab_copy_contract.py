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
