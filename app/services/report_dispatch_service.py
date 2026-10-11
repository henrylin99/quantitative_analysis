from typing import Any, Dict, List, Optional

from loguru import logger

from app.models.realtime_report import ReportSubscription, RealtimeReport
from app.services.realtime_report_generator import RealtimeReportGenerator

# 支持真实外发的渠道类型（与 alert_push_service._CHANNEL_TYPES 对齐）
_DELIVERABLE_CHANNELS = ("serverchan", "wecom_webhook", "dingtalk_webhook", "webhook")


class ReportDispatchService:
    """报告订阅分发服务。

    - 查找待发送订阅 → 生成报告 → 按订阅声明的渠道真实外发
      （复用每日预警的推送渠道配置：data/alerts/push_config.json）
    - 渠道未配置参数 / 推送失败时记录逐渠道结果，不影响分发主流程
    - "log" 渠道只记日志（历史上仅支持记录时的兼容默认值）
    """

    def __init__(self, generator: Optional[RealtimeReportGenerator] = None):
        self.generator = generator or RealtimeReportGenerator()

    def dispatch_pending_subscriptions(self) -> Dict[str, Any]:
        try:
            subscriptions = ReportSubscription.get_pending_subscriptions()
            results: List[Dict[str, Any]] = []

            for subscription in subscriptions:
                dispatch_result = self._dispatch_subscription(subscription)
                results.append(dispatch_result)

            return {
                "success": True,
                "dispatched": len([item for item in results if item.get("success")]),
                "failed": len([item for item in results if not item.get("success")]),
                "results": results,
            }
        except Exception as exc:
            logger.error(f"分发订阅失败: {exc}")
            return {"success": False, "message": str(exc), "dispatched": 0, "failed": 0, "results": []}

    def _dispatch_subscription(self, subscription: ReportSubscription) -> Dict[str, Any]:
        template = subscription.template
        if template is None:
            return {"success": False, "subscription_id": subscription.id, "message": "模板不存在"}

        parameters = {}
        schedule_config = subscription.schedule_config if isinstance(subscription.schedule_config, dict) else {}
        if isinstance(schedule_config, dict):
            parameters.update(schedule_config.get("parameters") or {})

        result = self.generator.generate_report(
            report_type=template.template_type,
            template_id=template.id,
            report_name=None,
            parameters=parameters,
            generated_by="subscription_dispatch",
        )
        if not result.get("success"):
            return {
                "success": False,
                "subscription_id": subscription.id,
                "message": result.get("message", "生成报告失败"),
            }

        report_id = result.get("data", {}).get("report_id")
        report = RealtimeReport.get_by_id(report_id) if report_id else None

        delivery_results: List[Dict[str, Any]] = []
        channels: List[str] = ["log"]
        if report is not None:
            requested = (
                subscription.notification_channels
                if isinstance(subscription.notification_channels, list) else []
            )
            channels = requested or ["log"]
            delivery_results = self._deliver(report, requested)
            report.attach_dispatch_metadata(
                subscription_id=subscription.id,
                channels=channels,
                subscriber_email=subscription.subscriber_email,
                subscriber_phone=subscription.subscriber_phone,
                delivery_results=delivery_results,
            )

        subscription.update_send_time()

        logger.info(f"订阅 {subscription.id} 分发完成，外发渠道 {channels}")
        return {
            "success": True,
            "subscription_id": subscription.id,
            "report_id": report_id,
            "channels": channels,
            "delivery_results": delivery_results,
            "message": "分发完成",
        }

    def _deliver(self, report: RealtimeReport, requested_channels: List[str]) -> List[Dict[str, Any]]:
        """把报告摘要推到订阅声明的可外发渠道；返回逐渠道结果。

        渠道参数取自每日预警的推送配置（data/alerts/push_config.json）：
        订阅只选择"用哪个渠道"，渠道的 url/send_key 统一在市场简报页配置。
        未配置参数或类型不支持时记录原因，绝不静默假装发送成功。
        """
        deliverable = [c for c in requested_channels if c in _DELIVERABLE_CHANNELS]
        if not deliverable:
            return [{"type": "log", "ok": True, "message": "无外发渠道，仅记录"}]

        delivery_results: List[Dict[str, Any]] = []
        from app.services.alert_push_service import AlertPushService
        from app.services.report_export_service import report_digest_text

        try:
            configured = {
                ch.get("type"): ch
                for ch in AlertPushService().get_config().get("channels") or []
            }
            channels = []
            for ctype in deliverable:
                entry = configured.get(ctype)
                if not entry:
                    delivery_results.append({"type": ctype, "ok": False, "message": "渠道未配置参数，跳过外发"})
                else:
                    channels.append(entry)
            if not channels:
                return delivery_results

            title, _, text = report_digest_text(report).partition("\n")
            results = AlertPushService().push_text(title, text, channels=channels, log_tag="report_dispatch")
            return delivery_results + results
        except Exception as exc:  # noqa: BLE001
            logger.error(f"报告外发失败 report_id={getattr(report, 'id', '?')}: {exc}")
            return delivery_results + [{"type": "unknown", "ok": False, "message": f"外发异常: {exc}"}]
