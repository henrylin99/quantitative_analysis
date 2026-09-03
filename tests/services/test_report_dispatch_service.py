from types import SimpleNamespace
from unittest.mock import patch

from app.services.report_dispatch_service import ReportDispatchService


def test_dispatch_service_attaches_metadata_through_model_helper():
    subscription = SimpleNamespace(
        id=8,
        template=SimpleNamespace(id=3, template_type="daily_summary"),
        schedule_config='{"parameters": {"portfolio_id": "growth_a"}}',
        notification_channels='["email", "log"]',
        subscriber_email="user@example.com",
        subscriber_phone="13800000000",
        update_send_time=lambda: None,
    )
    report = SimpleNamespace(
        report_data='{"existing": true}',
        attach_dispatch_metadata=lambda **kwargs: kwargs,
    )

    generator_result = {
        "success": True,
        "data": {"report_id": 99},
        "message": "报告生成成功",
    }

    with (
        patch("app.services.report_dispatch_service.ReportSubscription.get_pending_subscriptions", return_value=[subscription]),
        patch("app.services.report_dispatch_service.RealtimeReport.get_by_id", return_value=report),
        patch.object(ReportDispatchService, "__init__", lambda self, generator=None: setattr(self, "generator", SimpleNamespace(generate_report=lambda **kwargs: generator_result))),
    ):
        service = ReportDispatchService()
        result = service.dispatch_pending_subscriptions()

    assert result["success"] is True
    assert result["dispatched"] == 1
