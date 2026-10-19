"""港美股快照同步服务：后台子进程运行 scripts/{market}_stock/build_snapshot.py。

POST /sync 立即返回，子进程日志落 data/sync_logs/；前端轮询 GET /sync 取状态。
进程正常结束后重载对应 service 的进程内 DataFrame 缓存，最新数据日期随 meta 生效。
"""
from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "data" / "sync_logs"

_MARKETS = {
    "hk": {
        "script": PROJECT_ROOT / "scripts" / "hk_stock" / "build_snapshot.py",
        "service": "hk_stock_service",
    },
    "us": {
        "script": PROJECT_ROOT / "scripts" / "us_stock" / "build_snapshot.py",
        "service": "us_stock_service",
    },
}

# build_snapshot 依赖 yfinance（装在 anaconda python；项目 .venv 没有），按序探测
_PYTHON_CANDIDATES = [
    Path.home() / "anaconda3" / "bin" / "python3",
    Path.home() / "miniconda3" / "bin" / "python3",
    Path("/opt/anaconda3/bin/python3"),
    Path("/opt/miniconda3/bin/python3"),
    Path(sys.executable),
]

_LOG_TAIL_CHARS = 2000

_STATE: dict[str, dict] = {
    market: {
        "status": "idle",  # idle | running | success | failed
        "message": "",
        "started_at": None,
        "finished_at": None,
        "returncode": None,
        "log_file": None,
    }
    for market in _MARKETS
}
_START_LOCK = threading.Lock()
_PYTHON_CACHE: str | None = None


def _resolve_python() -> str:
    global _PYTHON_CACHE
    if _PYTHON_CACHE:
        return _PYTHON_CACHE
    for py in _PYTHON_CANDIDATES:
        if not py.exists():
            continue
        try:
            probe = subprocess.run(
                [str(py), "-c", "import yfinance"],
                capture_output=True,
                timeout=120,
            )
            if probe.returncode == 0:
                _PYTHON_CACHE = str(py)
                return _PYTHON_CACHE
        except Exception:
            continue
    raise RuntimeError("未找到带 yfinance 的 Python 解释器（尝试过 anaconda/miniconda/当前解释器）")


def _log_tail(log_file: str | None) -> str | None:
    if not log_file:
        return None
    try:
        with open(log_file, encoding="utf-8", errors="replace") as f:
            return f.read()[-_LOG_TAIL_CHARS:]
    except Exception:
        return None


def _reload_service_cache(market: str) -> None:
    import importlib

    module = importlib.import_module(f"app.services.{_MARKETS[market]['service']}")
    module.load_snapshot()
    module.load_history()


def _wait_proc(market: str, proc: subprocess.Popen) -> None:
    state = _STATE[market]
    returncode = proc.wait()
    state["returncode"] = returncode
    state["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if returncode == 0:
        try:
            _reload_service_cache(market)
            state["status"] = "success"
            state["message"] = "同步完成，数据已更新"
        except Exception as e:
            state["status"] = "failed"
            state["message"] = f"同步进程结束但刷新数据失败: {e}"
    else:
        state["status"] = "failed"
        state["message"] = f"同步失败（退出码 {returncode}），详见日志"
    state["log_tail"] = _log_tail(state["log_file"])


def start_sync(market: str) -> tuple[dict, bool]:
    """启动同步。返回 (状态, 是否本次新启动)；已在运行时返回当前状态且 started=False。"""
    if market not in _MARKETS:
        raise ValueError(f"不支持的市场: {market}（可选: {', '.join(_MARKETS)}）")
    with _START_LOCK:
        state = _STATE[market]
        if state["status"] == "running":
            return dict(state), False

        script = _MARKETS[market]["script"]
        if not script.exists():
            raise ValueError(f"同步脚本不存在: {script}")
        python = _resolve_python()

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / f"{market}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_handle = open(log_file, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [python, str(script)],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            start_new_session=True,
        )
        log_handle.close()  # 句柄由子进程持有，父进程侧可关

        state.update(
            status="running",
            message=f"同步中（pid {proc.pid}），历史快照构建约需 3-8 分钟",
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            finished_at=None,
            returncode=None,
            log_file=str(log_file),
        )
        threading.Thread(target=_wait_proc, args=(market, proc), daemon=True).start()
        return dict(state), True


def get_status(market: str) -> dict:
    """同步状态 + 对应市场最新数据日期/数量（取自 service 缓存）。"""
    if market not in _MARKETS:
        raise ValueError(f"不支持的市场: {market}（可选: {', '.join(_MARKETS)}）")
    state = dict(_STATE[market])
    state["log_tail"] = _log_tail(state.get("log_file")) if state["status"] in ("running", "failed") else None
    try:
        import importlib

        module = importlib.import_module(f"app.services.{_MARKETS[market]['service']}")
        meta = module.build_meta()
        state["total"] = meta.get("total")
        state["trade_date"] = meta.get("trade_date")
    except Exception:
        state["total"] = None
        state["trade_date"] = None
    return state
