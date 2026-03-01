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

    def task(self, name=None):
        def _decorator(func):
            wrapper = _LocalTaskWrapper(func)
            wrapper.name = name or func.__name__
            return wrapper

        return _decorator


def make_celery(config_name: str = "default"):
    cfg = config[config_name]
    broker = f"redis://{cfg.REDIS_HOST}:{cfg.REDIS_PORT}/{cfg.REDIS_DB}"

    if Celery is None:
        return _LocalCelery()

    celery = Celery("quant_data_jobs", broker=broker, backend=broker)
    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=False,
    )
    return celery


celery = make_celery()
