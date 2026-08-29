"""回测异步任务。

长区间/日频调仓的回测在同步 HTTP 请求里跑会超时：请求先创建回测记录，
再交给 Celery 执行，完整结果落盘到 BacktestRepository，前端凭 run_id
轮询 /backtest/runs/<id>（summary.status）与 /backtest/runs/<id>/result。

任何异常都必须把 run 标记为 failed，否则状态会永远停在 running。
"""
from __future__ import annotations

from typing import Any, Dict

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


@celery.task(name="backtest.run")
def run_backtest_task(run_id: int, strategy_config: Dict[str, Any],
                      start_date: str, end_date: str,
                      initial_capital: float = 1000000.0,
                      rebalance_frequency: str = "monthly") -> Dict[str, Any]:
    """执行异步回测并把完整结果写入 BacktestRepository。"""
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
        result = _build_engine().run_backtest(
            strategy_config, start_date, end_date,
            initial_capital, rebalance_frequency,
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
