from types import SimpleNamespace

from config import config

try:
    from celery import Celery
except ModuleNotFoundError:  # pragma: no cover - local fallback for environments without celery
    Celery = None


class _LocalTaskWrapper:
    def __init__(self, func):
        self._func = func
        self.__name__ = getattr(func, "__name__", "task")

    def __call__(self, *args, **kwargs):
        return self._func(*args, **kwargs)

    def delay(self, *args, **kwargs):
        return self._func(*args, **kwargs)


class _LocalCelery:
    def __init__(self):
        self.conf = SimpleNamespace(update=lambda **kwargs: None)
        self.tasks = {}

    def task(self, name=None):
        def _decorator(func):
            wrapper = _LocalTaskWrapper(func)
            task_name = name or func.__name__
            wrapper.name = task_name
            self.tasks[task_name] = wrapper
            return wrapper

        return _decorator


def make_celery(config_name: str = "default"):
    cfg = config[config_name]

    if Celery is None:
        logger = __import__("logging").getLogger(__name__)
        logger.warning(
            "未安装 celery，数据任务将以本地内联方式执行（不适合生产环境）"
        )
        return _LocalCelery()

    # 优先使用完整的 CELERY_BROKER_URL / CELERY_RESULT_BACKEND，
    # 支持带密码等无法用 host/port 拼接表达的形式
    broker = getattr(cfg, "CELERY_BROKER_URL", None) or (
        f"redis://{cfg.REDIS_HOST}:{cfg.REDIS_PORT}/{cfg.REDIS_DB}"
    )
    backend = getattr(cfg, "CELERY_RESULT_BACKEND", None) or broker

    celery = Celery("quant_data_jobs", broker=broker, backend=backend)
    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=False,
    )
    return celery


celery = make_celery()

# Ensure all task modules are imported so worker can discover registered tasks.
from app.tasks import data_jobs_tasks  # noqa: E402,F401
