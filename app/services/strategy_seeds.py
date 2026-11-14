"""常用策略预置（数据初始化末尾自动创建）。

初始化链路跑完因子计算后，检查策略库中是否已有这些预置策略，缺哪个补
哪个（同名已有则不升版，用户改过不会被覆盖）。因子引用对真实注册表做
存在性校验：注册表不可用或因子缺失时跳过该条并记录原因，不阻断初始化。

预置策略只是「能直接跑的起点」：回测区间按预置时点动态取近两年，用户
可在策略管理页派生编辑或用 run_strategy overrides 换区间重跑。
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_BACKTEST_YEARS = 2


def _seed_window() -> Dict[str, str]:
    """预置回测区间：近两年到今天（保存时固化，重跑可 overrides 覆盖）。"""
    today = datetime.now()
    start = today - timedelta(days=_BACKTEST_YEARS * 365)
    return {
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": today.strftime("%Y-%m-%d"),
    }


def _seed_definitions() -> List[Dict[str, Any]]:
    """预置策略清单（名字 → 组装参数）。"""
    w = _seed_window()
    common = {
        "top_n": 20,
        "benchmark_index": "000300.SH",
        "rebalance_frequency": "monthly",
        **w,
    }
    return [
        {
            "name": "动量低估值",
            "description": (
                "DSL 规则策略：20日动量前30% 且 PE 分位 < 0.4，"
                "按动量排序取前 20，月度调仓"
            ),
            "dsl_filter": "rank(momentum_20d) > 0.7 and pe_percentile < 0.4",
            "dsl_order_by": "rank(momentum_20d) - 0.3 * pe_percentile",
            **common,
        },
        {
            "name": "质量价值",
            "description": (
                "因子加权策略：40% ROE + 30% 盈利增长 - 30% PE 分位，"
                "取前 20，月度调仓"
            ),
            "factor_ids": ["roe_ttm", "profit_growth", "pe_percentile"],
            "weights": {"roe_ttm": 0.4, "profit_growth": 0.3, "pe_percentile": -0.3},
            "factor_directions": {
                "roe_ttm": "high",
                "profit_growth": "high",
                "pe_percentile": "low",
            },
            **common,
        },
        {
            "name": "低波动",
            "description": "因子加权策略：低 20 日波动率优先，取前 20，月度调仓",
            "factor_ids": ["volatility_20d"],
            "weights": {"volatility_20d": -1.0},
            "factor_directions": {"volatility_20d": "low"},
            **common,
        },
    ]


def seed_default_strategies() -> Dict[str, Any]:
    """补齐缺失的预置策略；返回 {created, skipped, failed} 明细。"""
    from app.services.parquet_state_store import (
        BacktestRepository,
        ParquetStateStore,
        StrategyRepository,
    )
    from app.services.strategy_service import (
        StrategyService,
        StrategyError,
        _factor_registry_ids,
        build_strategy_config,
    )

    store = ParquetStateStore()
    svc = StrategyService(StrategyRepository(store), BacktestRepository(store))

    existing = {s["name"] for s in svc.strategy_repo.list_strategies()}
    known = _factor_registry_ids()
    created: List[str] = []
    skipped: List[str] = []
    failed: List[Dict[str, str]] = []

    for seed in _seed_definitions():
        name = seed["name"]
        if name in existing:
            skipped.append(name)
            continue
        try:
            if seed.get("dsl_order_by"):
                config = build_strategy_config(
                    dsl_filter=seed["dsl_filter"],
                    dsl_order_by=seed["dsl_order_by"],
                    known_factors=known,
                    top_n=seed["top_n"],
                    benchmark_index=seed["benchmark_index"],
                    start_date=seed["start_date"],
                    end_date=seed["end_date"],
                    rebalance_frequency=seed["rebalance_frequency"],
                )
            else:
                missing = [f for f in seed["factor_ids"] if f not in known]
                if missing:
                    failed.append({"name": name, "reason": f"因子不在注册表: {missing}"})
                    continue
                config = build_strategy_config(
                    factor_ids=seed["factor_ids"],
                    weights=seed["weights"],
                    factor_directions=seed["factor_directions"],
                    top_n=seed["top_n"],
                    benchmark_index=seed["benchmark_index"],
                    start_date=seed["start_date"],
                    end_date=seed["end_date"],
                    rebalance_frequency=seed["rebalance_frequency"],
                )
            svc.save_strategy(name, config, description=seed["description"])
            created.append(name)
        except StrategyError as exc:
            failed.append({"name": name, "reason": str(exc)})
        except Exception:  # noqa: BLE001 - 单条失败不阻断其余预置
            logger.warning("预置策略 %s 保存失败", name, exc_info=True)
            failed.append({"name": name, "reason": "保存异常（详见服务日志）"})

    return {"created": created, "skipped": skipped, "failed": failed}
