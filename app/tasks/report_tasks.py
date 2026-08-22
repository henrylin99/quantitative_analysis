import threading

from app import create_app
from app.celery_app import celery
from app.services.report_dispatch_service import ReportDispatchService

# beat 周期触发时上一轮可能尚未结束；用进程内互斥防止订阅被重复派发
_dispatch_lock = threading.Lock()


@celery.task(name="reports.dispatch_pending")
def dispatch_pending_reports():
    if not _dispatch_lock.acquire(blocking=False):
        return {"status": "skipped", "reason": "previous dispatch still running"}
    try:
        app = create_app("development")
        with app.app_context():
            service = ReportDispatchService()
            return service.dispatch_pending_subscriptions()
    finally:
        _dispatch_lock.release()
