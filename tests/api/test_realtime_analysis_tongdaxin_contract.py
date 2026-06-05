from unittest.mock import patch

from flask import Flask

from app.api.realtime_analysis import realtime_analysis_bp


def _build_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(realtime_analysis_bp)
    return app


def test_sync_endpoint_passes_tongdaxin_data_source():
    app = _build_app()
    client = app.test_client()

    with patch("app.api.realtime_analysis.data_manager") as manager:
        manager.sync_minute_data.return_value = {"success": True, "message": "ok", "data_count": 1}
        response = client.post(
            "/api/realtime-analysis/data/sync",
            json={
                "ts_code": "sh.600000",
                "period_type": "5min",
                "start_date": "2026-06-05",
                "end_date": "2026-06-05",
                "data_source": "tongdaxin",
            },
        )

    assert response.status_code == 200
    assert manager.sync_minute_data.call_args.kwargs["data_source"] == "tongdaxin"
