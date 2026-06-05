from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager


DEFAULT_HOSTS = (
    ("default", "119.147.212.81", 7709),
    ("server_1", "115.238.56.198", 7709),
    ("server_2", "115.238.90.165", 7709),
    ("server_3", "180.153.18.170", 7709),
)


def create_hq_api(**overrides):
    from pytdx.hq import TdxHq_API

    options = {
        "heartbeat": True,
        "auto_retry": True,
        "raise_exception": False,
    }
    options.update(overrides)
    return TdxHq_API(**options)


def normalize_hosts(hosts: Iterable[tuple[str, str, int]] | None = None) -> list[tuple[str, str, int]]:
    normalized = []
    for name, host, port in (hosts or DEFAULT_HOSTS):
        normalized.append((str(name), str(host), int(port)))
    return normalized


def connect_first_available(api, hosts: Iterable[tuple[str, str, int]] | None = None) -> tuple[str, str, int]:
    last_error = None
    for name, host, port in normalize_hosts(hosts):
        try:
            if api.connect(host, port):
                return name, host, port
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise ConnectionError("No available pytdx hosts") from last_error
    raise ConnectionError("No available pytdx hosts")


@contextmanager
def connected_session(api, hosts: Iterable[tuple[str, str, int]] | None = None):
    connect_first_available(api, hosts)
    try:
        yield api
    finally:
        api.disconnect()
