from app import create_app
from app.celery_app import celery
from app.services.report_dispatch_service import ReportDispatchService


@celery.task(name="reports.dispatch_pending")
def dispatch_pending_reports():
    app = create_app("development")
    with app.app_context():
        service = ReportDispatchService()
        return service.dispatch_pending_subscriptions()
