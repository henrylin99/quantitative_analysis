"""回测 worker 子进程入口：`python -m app.tasks.backtest_worker <run_id>`。

由 backtest_tasks._run_in_subprocess spawn。职责：
- 落 pid 心跳文件（web 进程重启后孤儿清理凭它识别"还在跑"）；
- 自带软超时（SIGALRM，防监督线程的 web 进程先死导致 worker 无限跑）；
- 从 BacktestRepository 读 run 参数执行并写回结果（与线程内模式同一执行体）。
"""
from __future__ import annotations

import os
import signal
import sys


class _BacktestTimeout(Exception):
    pass


def main(run_id: int) -> int:
    from app.tasks import backtest_tasks

    backtest_tasks._write_worker_pid(run_id)

    def _on_alarm(signum, frame):
        raise _BacktestTimeout(f"回测超过 {backtest_tasks._timeout_seconds()}s")

    try:
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(backtest_tasks._timeout_seconds())
    except (ValueError, AttributeError):
        pass  # 非主线程/不支持 SIGALRM 的平台：依赖监督进程兜底
    try:
        backtest_tasks.execute_run(run_id)
        return 0
    except _BacktestTimeout as e:
        from loguru import logger

        logger.error(f"回测 worker 超时 run_id={run_id}: {e}")
        try:
            backtest_tasks._build_repo().update_summary(
                run_id, {"status": "failed", "error": str(e)})
        except Exception:
            pass
        return 124
    except Exception as e:
        from loguru import logger

        logger.error(f"回测 worker 异常 run_id={run_id}: {e}")
        try:
            backtest_tasks._build_repo().update_summary(
                run_id, {"status": "failed", "error": str(e)})
        except Exception:
            pass
        return 1
    finally:
        backtest_tasks._remove_worker_pid(run_id)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python -m app.tasks.backtest_worker <run_id>", file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(main(int(sys.argv[1])))
    except ValueError:
        print("run_id 必须是整数", file=sys.stderr)
        sys.exit(2)
