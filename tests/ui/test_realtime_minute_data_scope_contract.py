from pathlib import Path


def test_realtime_index_exposes_baostock_minute_data_scope_only():
    html = Path("app/templates/realtime_analysis/index.html").read_text(encoding="utf-8")

    assert "当前页面以 Baostock 分钟数据接入、聚合与衍生分析入口为主。" in html
    assert 'option value="tushare"' not in html
    assert 'option value="1min"' not in html
    assert "同步所有周期数据 (5min, 15min, 30min, 60min)" in html


def test_realtime_child_pages_do_not_expose_1min_as_supported_period():
    monitor = Path("app/templates/realtime_analysis/monitor.html").read_text(encoding="utf-8")
    indicators = Path("app/templates/realtime_analysis/indicators.html").read_text(encoding="utf-8")
    signals = Path("app/templates/realtime_analysis/signals.html").read_text(encoding="utf-8")

    assert "当前页面基于已入库的 Baostock 分钟数据进行展示。" in monitor
    assert "当前页面基于已入库的 Baostock 分钟数据计算指标。" in indicators
    assert "当前页面基于已入库的 Baostock 分钟数据生成与查看信号。" in signals
    assert "onclick=\"loadQuotes('1min')\"" not in monitor
    assert 'option value="1min"' not in indicators
    assert 'option value="1min"' not in signals
