from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app.api.realtime_risk import realtime_risk_bp
from app.extensions import db


def _build_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TESTING=True,
    )
    db.init_app(app)
    app.register_blueprint(realtime_risk_bp, url_prefix="/api/realtime-analysis/risk")
    return app


def test_resolve_risk_alert_endpoint_uses_model_helper():
    app = _build_app()
    client = app.test_client()

    alert = SimpleNamespace(
        to_dict=lambda: {
            "id": 9,
            "ts_code": "000001.SZ",
            "alert_type": "stop_loss_triggered",
            "alert_level": "high",
            "is_active": False,
            "is_resolved": True,
        }
    )

    with patch("app.api.realtime_risk.RiskAlert.resolve_by_id", return_value=alert) as resolve_by_id:
        response = client.put("/api/realtime-analysis/risk/alerts/9/resolve")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["id"] == 9
    resolve_by_id.assert_called_once_with(9)
