"""进程内任务注册表（原 Celery 入口，去 Redis 化后无外部 broker）。

`@celery.task` 只负责注册任务，`task.delay(...)` 等价于同步直接调用；
长任务的非阻塞执行由调用方自行开线程（见 ml_factor_api 的 async 回测）。
保留模块路径 `app.celery_app.celery`，app/tasks/* 及既有调用方无需改动。
"""
from types import SimpleNamespace


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
    """保留原签名。无外部 broker，任务在调用进程内直接执行。"""
    return _LocalCelery()


celery = make_celery()

# Import all task modules so they register on the local registry.
from app.tasks import data_jobs_tasks  # noqa: E402,F401
from app.tasks import report_tasks  # noqa: E402,F401
from app.tasks import backtest_tasks  # noqa: E402,F401
