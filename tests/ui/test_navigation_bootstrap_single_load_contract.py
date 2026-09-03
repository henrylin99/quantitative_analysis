from pathlib import Path


def test_realtime_and_data_templates_do_not_duplicate_bootstrap_bundle():
    template_paths = [
        "app/templates/data_management/index.html",
        "app/templates/realtime_analysis/indicators.html",
        "app/templates/realtime_analysis/signals.html",
        "app/templates/realtime_analysis/monitor.html",
        "app/templates/realtime_analysis/risk_management.html",
        "app/templates/realtime_analysis/report_management.html",
        "app/templates/realtime_analysis/websocket_management.html",
    ]

    for path in template_paths:
        html = Path(path).read_text(encoding="utf-8")
        assert html.count("bootstrap.bundle.min.js") == 0, path
