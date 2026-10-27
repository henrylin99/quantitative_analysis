"""回测异步任务。

长区间/日频调仓的回测在同步 HTTP 请求里跑会超时：请求先创建回测记录，
再交给后台执行，完整结果落盘到 BacktestRepository，前端凭 run_id
轮询 /backtest/runs/<id>（summary.status）与 /backtest/runs/<id>/result。

执行模式（BACKTEST_SUBPROCESS_ENABLED，默认开）：
- 子进程：后台线程 spawn `python -m app.tasks.backtest_worker <run_id>` 并监督。
  重计算不再占用 web 进程（GIL 崩溃/内存爆掉不拖垮服务）；web 进程重启后
  存活 worker 仍能写完结果（刷新/重启不丢任务）。worker 写 pid 心跳文件，
  存活判定 = 进程内注册表 OR pid 文件存活，孤儿清理不会误杀在跑的 worker。
- 线程内（兜底/开发）：行为与历史版本一致，同进程跑引擎。

任何异常都必须把 run 标记为 failed，否则状态会永远停在 running。
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Set

import numpy as np
from loguru import logger

from app.celery_app import celery
from app.services.parquet_state_store import BacktestRepository, ParquetStateStore


def _build_engine():
    # 延迟导入：backtest_engine 依赖较重，且便于测试中替换
    from app.services.backtest_engine import BacktestEngine

    return BacktestEngine()


def _build_repo() -> BacktestRepository:
    return BacktestRepository(ParquetStateStore())


def _to_jsonable(obj: Any) -> Any:
    """numpy 标量/数组递归转为 Python 原生类型，保证 result_json 可序列化。"""
    if isinstance(obj, dict):
        return {key: _to_jsonable(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(value) for value in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def _subprocess_enabled() -> bool:
    return os.getenv("BACKTEST_SUBPROCESS_ENABLED", "1").strip().lower() \
        not in ("0", "false", "no")


def _timeout_seconds() -> int:
    try:
        return max(60, int(os.getenv("BACKTEST_JOB_TIMEOUT", "3600")))
    except ValueError:
        return 3600


def _worker_pid_dir() -> str:
    data_dir = os.getenv(
        "DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
    )
    return os.path.join(data_dir, "backtest_worker_pids")


def _write_worker_pid(run_id: int) -> str:
    path = os.path.join(_worker_pid_dir(), f"{int(run_id)}.pid")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return path


def _remove_worker_pid(run_id: int) -> None:
    try:
        os.remove(os.path.join(_worker_pid_dir(), f"{int(run_id)}.pid"))
    except FileNotFoundError:
        pass


def _worker_pid_alive(run_id: int) -> bool:
    try:
        with open(os.path.join(_worker_pid_dir(), f"{int(run_id)}.pid"),
                  encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)  # 只探测存在性，不发信号
    except OSError:
        return False
    return True


# ---------------------------------------------------------------------------
# 进程内活性注册表
#
# 单机单进程（SocketIO threading 模式）：回测线程是 daemon 线程，只可能
# 随进程一起消失。因此"run 是否有活着的执行者"可用注册表精确判定：
#   在册            → 线程存活，绝不清理（长回测不会被误判超时）
#   pid 文件存活    → 子进程 worker 仍在执行（web 进程重启后依然成立）
#   两者皆无且仍处于 queued/running → 只可能是中断遗留的孤儿，安全清理
# 这取代了 created_at + 超时的猜测式判活。
# ---------------------------------------------------------------------------
_active_lock = threading.Lock()
_active_run_ids: Set[int] = set()
_orphans_reaped_since_boot = False


def mark_run_active(run_id: int) -> None:
    with _active_lock:
        _active_run_ids.add(int(run_id))


def clear_run_active(run_id: int) -> None:
    with _active_lock:
        _active_run_ids.discard(int(run_id))


def is_run_active(run_id: int) -> bool:
    with _active_lock:
        in_registry = int(run_id) in _active_run_ids
    return in_registry or _worker_pid_alive(run_id)


def reap_orphans_once() -> List[Dict[str, Any]]:
    """进程启动后首次调用时全量清理孤儿 run，之后 O(1) 跳过。

    本进程的回测要么在注册表里、要么由存活 worker 的 pid 文件保护，
    孤儿只可能来自"上一个进程且其 worker 也没了"——清理一次后不会再
    新增，轮询路径无需反复全表扫描。判活直接传注册表回调，由
    reap_stale_runs 在表锁内逐候选复查，消除"快照后才提交并在册"的窗口；
    扫描抛异常时标志不置位，下次提交重试（并发下最多重复扫描一次，
    标记 failed 幂等无害）。
    """
    global _orphans_reaped_since_boot
    with _active_lock:
        first_call = not _orphans_reaped_since_boot
    if not first_call:
        return []
    reaped = _build_repo().reap_stale_runs(is_run_active)
    if reaped:
        logger.info(f"启动后清理孤儿回测 run: {[r['id'] for r in reaped]}")
    with _active_lock:
        _orphans_reaped_since_boot = True
    return reaped


def execute_run(run_id: int) -> Dict[str, Any]:
    """在当前进程执行回测并写 BacktestRepository（线程与 worker 子进程共用）。"""
    repo = _build_repo()

    def merge_summary(update: Dict[str, Any]) -> None:
        # update_summary 是整行覆盖：先取现有 summary 合并，
        # 否则会把引擎写入的 final_value 等指标冲掉
        run = repo.get_run(int(run_id))
        summary = dict(run.get("summary") or {}) if run else {}
        summary.update(update)
        repo.update_summary(int(run_id), summary)

    try:
        merge_summary({"status": "running"})
        run = repo.get_run(int(run_id))
        if run is None:
            raise RuntimeError(f"run {run_id} 不存在")
        result = _build_engine().run_backtest(
            run["strategy_config"], run["start_date"], run["end_date"],
            run["initial_capital"], run["rebalance_frequency"],
            run_id=int(run_id),
        )
        succeeded = bool(result.get("success"))
        merge_summary({
            "status": "succeeded" if succeeded else "failed",
            "error": result.get("error"),
        })
        try:
            repo.save_result(int(run_id), _to_jsonable(result))
        except Exception as e:
            # 结果落盘失败不让任务假成功：状态里如实标记
            logger.error(f"回测结果 {run_id} 落盘失败: {e}")
            merge_summary({"status": "failed", "error": f"结果落盘失败: {e}"})
            return {"run_id": int(run_id), "status": "failed", "error": str(e)}
        return {"run_id": int(run_id), "status": "succeeded" if succeeded else "failed"}
    except Exception as e:
        logger.error(f"异步回测任务失败 run_id={run_id}: {e}")
        merge_summary({"status": "failed", "error": str(e)})
        return {"run_id": int(run_id), "status": "failed", "error": str(e)}


def _project_root() -> str:
    # app/tasks/backtest_tasks.py → 上两级 = 项目根（app 包所在目录）
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_in_subprocess(run_id: int) -> Dict[str, Any]:
    """spawn worker 子进程执行并监督（超时硬杀 → 标记 failed）。"""
    repo = _build_repo()
    mark_run_active(int(run_id))
    root = _project_root()
    cmd = [sys.executable, "-m", "app.tasks.backtest_worker", str(int(run_id))]
    env = dict(os.environ)
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.Popen(cmd, cwd=root, env=env)
    except Exception as e:
        clear_run_active(int(run_id))
        logger.error(f"回测 worker 启动失败 run_id={run_id}: {e}，回退线程内执行")
        return execute_run(int(run_id))
    deadline = time.monotonic() + _timeout_seconds()
    timed_out = False
    try:
        while True:
            try:
                proc.wait(timeout=30.0)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    timed_out = True
                    proc.kill()
                    proc.wait(timeout=30)
                    logger.error(f"回测 run {run_id} 超过 BACKTEST_JOB_TIMEOUT，已终止")
                    break
    finally:
        clear_run_active(int(run_id))
        _remove_worker_pid(int(run_id))  # worker 正常退出已自删，此处兜底
    if timed_out:
        repo.update_summary(int(run_id), {"status": "failed",
                                          "error": f"回测超过 {_timeout_seconds()}s 被终止"})
        return {"run_id": int(run_id), "status": "failed", "error": "timeout"}
    run = repo.get_run(int(run_id))
    status = ((run or {}).get("summary") or {}).get("status", "failed")
    return {"run_id": int(run_id), "status": status}


@celery.task(name="backtest.run")
def run_backtest_task(run_id: int, strategy_config: Dict[str, Any],
                      start_date: str, end_date: str,
                      initial_capital: float = 1000000.0,
                      rebalance_frequency: str = "monthly") -> Dict[str, Any]:
    """执行异步回测并把完整结果写入 BacktestRepository。

    子进程模式下参数以 BacktestRepository 里 create_run 落盘的为准
    （提交路径先建记录再派发，两者一致）；入参保留以兼容线程内模式。
    """
    if _subprocess_enabled():
        return _run_in_subprocess(int(run_id))
    # 线程内模式（兜底）：与 worker 同一执行体，参数同样以落盘记录为准
    mark_run_active(int(run_id))
    try:
        return execute_run(int(run_id))
    finally:
        clear_run_active(int(run_id))
