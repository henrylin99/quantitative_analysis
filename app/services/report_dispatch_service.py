import json
from typing import Any, Dict, List, Optional

from loguru import logger

from app.extensions import db
from app.models.realtime_report import ReportSubscription, RealtimeReport
from app.services.realtime_report_generator import RealtimeReportGenerator


class ReportDispatchService:
    """最小可用的报告订阅分发服务。

    当前阶段不强依赖外部邮件或短信网关，只完成：
    - 查找待发送订阅
    - 生成报告
    - 更新订阅发送时间
    - 将分发信息写入报告数据与服务日志
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
        schedule_config = json.loads(subscription.schedule_config) if subscription.schedule_config else {}
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
        report = RealtimeReport.query.get(report_id) if report_id else None
        if report is not None:
            report.report_data = json.dumps({
                **(json.loads(report.report_data) if report.report_data else {}),
                "dispatch": {
                    "subscription_id": subscription.id,
                    "channels": json.loads(subscription.notification_channels) if subscription.notification_channels else ["log"],
                    "subscriber_email": subscription.subscriber_email,
                    "subscriber_phone": subscription.subscriber_phone,
                },
            })

        subscription.update_send_time()
        db.session.commit()

        logger.info(f"订阅 {subscription.id} 分发完成")
        return {
            "success": True,
            "subscription_id": subscription.id,
            "report_id": report_id,
            "message": "分发完成",
        }
