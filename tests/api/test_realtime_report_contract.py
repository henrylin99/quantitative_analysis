from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app.api.realtime_report import realtime_report_bp
from app.extensions import db


def _build_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TESTING=True,
    )
    db.init_app(app)
    app.register_blueprint(realtime_report_bp, url_prefix="/api/realtime-analysis/reports")
    return app


class _CountQuery:
    def __init__(self, total, filtered_counts=None, filters=None):
        self.total = total
        self.filtered_counts = filtered_counts or {}
        self.filters = filters or {}

    def filter_by(self, **kwargs):
        next_filters = dict(self.filters)
        next_filters.update(kwargs)
        return _CountQuery(self.total, self.filtered_counts, next_filters)

    def count(self):
        key = tuple(sorted(self.filters.items()))
        return self.filtered_counts.get(key, self.total)


class _ReportTypeGroupQuery:
    def group_by(self, *args, **kwargs):
        return self

    def all(self):
        return [
            SimpleNamespace(report_type="daily_summary", count=2),
            SimpleNamespace(report_type="market_overview", count=1),
        ]


def test_reports_blueprint_is_registered_under_expected_prefix():
    app = _build_app()
    client = app.test_client()

    response = client.get("/api/realtime-analysis/reports/report-types")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "daily_summary" in data["data"]
    assert "market_overview" in data["data"]


def test_generate_report_forwards_payload_and_accepts_valid_types():
    app = _build_app()
    client = app.test_client()

    payload = {
        "report_type": "signal_analysis",
        "template_id": 7,
        "report_name": "Tongdaxin 5min Snapshot",
        "parameters": {"period_type": "5min", "scope": "market"},
        "generated_by": "ui",
    }

    with patch("app.api.realtime_report.report_generator.generate_report", return_value={"success": True, "data": {"report_id": 88}}) as generate_report:
        response = client.post("/api/realtime-analysis/reports/generate-report", json=payload)

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["report_id"] == 88
    assert generate_report.call_args.kwargs == payload


def test_generate_report_rejects_invalid_report_type():
    app = _build_app()
    client = app.test_client()

    response = client.post(
        "/api/realtime-analysis/reports/generate-report",
        json={"report_type": "not_supported"},
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "无效的报告类型" in data["message"]


def test_report_metadata_endpoints_expose_stable_response_shape():
    app = _build_app()
    client = app.test_client()

    report_query = _CountQuery(
        total=5,
        filtered_counts={
            (("report_status", "completed"),): 4,
            (("report_status", "failed"),): 1,
        },
    )
    template_query = _CountQuery(
        total=3,
        filtered_counts={
            (("is_active", True),): 2,
        },
    )
    subscription_query = _CountQuery(
        total=4,
        filtered_counts={
            (("is_active", True),): 3,
        },
    )

    with app.app_context():
        with (
            patch("app.api.realtime_report.RealtimeReport.query", report_query),
            patch("app.api.realtime_report.ReportTemplate.query", template_query),
            patch("app.api.realtime_report.ReportSubscription.query", subscription_query),
            patch("app.models.realtime_report.db.session.query", return_value=_ReportTypeGroupQuery()),
        ):
            report_types = client.get("/api/realtime-analysis/reports/report-types")
            schedule_types = client.get("/api/realtime-analysis/reports/schedule-types")
            statistics = client.get("/api/realtime-analysis/reports/statistics")

    assert report_types.status_code == 200
    assert schedule_types.status_code == 200
    assert statistics.status_code == 200

    report_types_data = report_types.get_json()
    schedule_types_data = schedule_types.get_json()
    statistics_data = statistics.get_json()

    assert report_types_data["success"] is True
    assert "daily_summary" in report_types_data["data"]
    assert schedule_types_data["success"] is True
    assert "daily" in schedule_types_data["data"]
    assert statistics_data["success"] is True
    assert set(statistics_data["data"].keys()) == {"reports", "templates", "subscriptions", "report_type_stats"}
    assert statistics_data["data"]["reports"]["total"] == 5
    assert statistics_data["data"]["templates"]["active"] == 2
    assert statistics_data["data"]["subscriptions"]["active"] == 3
    assert statistics_data["data"]["report_type_stats"]["daily_summary"] == 2


def test_update_report_template_forwards_updated_fields():
    app = _build_app()
    client = app.test_client()

    template = SimpleNamespace(
        id=12,
        template_name="原模板",
        template_type="daily_summary",
        description="原描述",
        is_active=True,
        is_default=False,
        to_dict=lambda: {
            "id": 12,
            "template_name": "原模板",
            "template_type": "daily_summary",
            "description": "原描述",
            "components": [],
            "is_active": True,
            "is_default": False,
        },
    )

    updated_template = SimpleNamespace(
        to_dict=lambda: {
            "id": 12,
            "template_name": "新模板",
            "template_type": "market_overview",
            "description": "新描述",
            "components": ["summary"],
            "is_active": False,
            "is_default": True,
        }
    )

    with (
        patch("app.api.realtime_report.ReportTemplate.get_by_id", return_value=template),
        patch("app.api.realtime_report.ReportTemplate.update_template_by_id", return_value=updated_template) as update_template,
    ):
        response = client.put(
            "/api/realtime-analysis/reports/templates/12",
            json={
                "template_name": "新模板",
                "template_type": "market_overview",
                "description": "新描述",
                "components": ["summary"],
                "is_active": False,
                "is_default": True,
            },
        )

    assert response.status_code == 200
    assert update_template.call_args.kwargs == {
        "template_name": "新模板",
        "template_type": "market_overview",
        "description": "新描述",
        "components": ["summary"],
        "is_active": False,
        "is_default": True,
    }
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["template_name"] == "新模板"
