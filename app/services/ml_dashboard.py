"""ML 因子仪表盘的数据聚合服务。

从 app/api/ml_factor_api.py 抽取——仪表盘聚合逻辑（模型表现/因子有效性/
组合表现/风险分析）属于业务层，不应内嵌在路由文件里。

依赖说明: 持仓快照只能算出区间收益率、1日VaR、最大持仓权重；
最大回撤/夏普/胜率需要净值序列，快照数据算不出来，返回 None 由
前端显示为"—"，禁止用别的指标冒充。
"""


import numpy as np
import pandas as pd
from loguru import logger

from app.services.factor_engine import FactorEngine
from app.services.ml_models import MLModelManager
from app.services.parquet_state_store import ParquetStateStore, PortfolioRepository
from app.utils.time_utils import now_local, now_local_iso

# 延迟初始化的服务实例（本模块自持，避免与 API 模块共享可变全局）
_ml_manager = None
_factor_engine = None
_portfolio_repo = None


def get_ml_manager():
    global _ml_manager
    if _ml_manager is None:
        _ml_manager = MLModelManager()
    return _ml_manager


def get_factor_engine():
    global _factor_engine
    if _factor_engine is None:
        _factor_engine = FactorEngine()
    return _factor_engine


def get_portfolio_repo():
    global _portfolio_repo
    if _portfolio_repo is None:
        _portfolio_repo = PortfolioRepository(ParquetStateStore())
    return _portfolio_repo


def _latest_snapshot(model_id):
    """模型最新训练快照；无快照（未训练过）返回 None。"""
    try:
        from app.services.model_experiments import TrainingSnapshotRepository
        for snap in TrainingSnapshotRepository().list_snapshots(model_id=model_id):
            return snap
    except Exception as exc:
        logger.warning(f"读取训练快照失败: {model_id}, {exc}")
    return None


def build_model_performance_summary():
    manager = get_ml_manager()
    models = manager.get_model_list()
    performance_data = []
    comparison_data = []
    best_r2 = 0.0

    for model in models:
        model_id = model.get("model_id")
        # 指标直接取最新训练快照（test_r2/mae，秒级）：实时 evaluate 要为
        # 全部预测股拉全市场行情，模型一多仪表盘就是分钟级；深度评估走
        # POST /models/evaluate
        snap = _latest_snapshot(model_id)
        if not snap:
            continue
        snap_metrics = snap.get("metrics") or {}
        r2_score = float(snap_metrics.get("test_r2") or 0.0)
        mae_score = float(snap_metrics.get("test_mae") or 0.0)
        best_r2 = max(best_r2, r2_score)
        performance_data.append({
            "date": (snap.get("created_at") or model.get("created_at", now_local_iso()))[:10],
            "train_r2": r2_score,
            "test_r2": None,
            "mae": mae_score,
        })
        comparison_data.append({
            "model_type": model.get("model_type"),
            "r2_score": r2_score,
            "mae_score": mae_score,
        })

    return {
        "total_models": len(models),
        "best_r2": best_r2,
        "performance_data": performance_data,
        "comparison_data": comparison_data,
    }


def build_factor_effectiveness_summary():
    engine = get_factor_engine()
    definitions = [f for f in engine.get_factor_list(is_active=True) if f.get("is_active", True)]
    active_factors = len(definitions)
    importance_data = []
    factor_stats = []

    # 逐因子调 get_factor_exposure 会把同一份最新日分区重复整读 N 次
    # （215 因子 ≈ 30s+）；这里一次读取后按 factor_id 分组计算
    latest_date = engine.data_reader.get_stock_business_latest_date() or now_local().strftime("%Y-%m-%d")
    exposure_all = engine.factor_repo.get_values(trade_date=latest_date)
    if not exposure_all.empty:
        value_col = "z_score" if "z_score" in exposure_all.columns else "factor_value"
        exposure_all[value_col] = pd.to_numeric(exposure_all[value_col], errors="coerce")

    stats_by_factor = {}
    if not exposure_all.empty:
        for factor_id, group in exposure_all.groupby("factor_id"):
            # 与原 get_factor_exposure 口径一致：整列降序（NaN 沉底）、保留
            # NaN 参与位次，corr 自动跳过 NaN 行——位次含 NaN 空位是原口径
            series = group[value_col].sort_values(ascending=False, na_position="last").reset_index(drop=True)
            if series.dropna().empty:
                continue
            stats_by_factor[factor_id] = {
                "importance": float(series.abs().mean()),
                "correlation": float(series.corr(pd.Series(range(len(series))))) if len(series) > 1 else 0.0,
            }

    for factor in definitions:
        factor_id = factor["factor_id"]
        stats = stats_by_factor.get(factor_id, {"importance": 0.0, "correlation": 0.0})
        importance_data.append({
            "factor_name": factor.get("factor_name", factor_id),
            **stats,
        })
        factor_stats.append({
            "factor_name": factor.get("factor_name", factor_id),
            **stats,
        })

    importance_data.sort(key=lambda item: item["importance"], reverse=True)
    return {
        "active_factors": active_factors,
        "importance_data": importance_data,
        "factor_stats": factor_stats,
    }


def build_portfolio_performance_summary():
    portfolio_repo = get_portfolio_repo()
    portfolio_ids = portfolio_repo.list_portfolio_ids(active_only=True)
    performance_data = []
    portfolio_metrics = []
    all_sector_distribution = {}
    returns = []
    var_1ds = []
    max_position_weights = []

    for portfolio_id in portfolio_ids:
        metrics = portfolio_repo.calculate_metrics(portfolio_id)
        if not metrics:
            continue
        portfolio_metrics.append(metrics)
        return_pct = float(metrics.get("total_pnl_percentage") or 0.0)
        var_1d = float(metrics.get("portfolio_var_1d") or 0.0)
        max_weight = float(metrics.get("max_position_weight") or 0.0)
        returns.append(return_pct)
        var_1ds.append(var_1d)
        max_position_weights.append(max_weight)
        performance_data.append({
            "date": portfolio_id,
            "portfolio_return": return_pct,
            "benchmark_return": None,
        })
        for sector, weight in (metrics.get("sector_distribution") or {}).items():
            all_sector_distribution[sector] = all_sector_distribution.get(sector, 0.0) + float(weight or 0.0)

    return {
        "portfolio_count": len(portfolio_ids),
        "annual_return": float(np.mean(returns)) if returns else 0.0,
        "max_drawdown": None,
        "sharpe_ratio": None,
        "win_rate": None,
        "portfolio_var_1d": float(np.mean(var_1ds)) if var_1ds else 0.0,
        "max_position_weight": float(np.mean(max_position_weights)) if max_position_weights else 0.0,
        "performance_data": performance_data,
        "sector_distribution": all_sector_distribution,
        "portfolio_metrics": portfolio_metrics,
    }


def build_risk_analysis_summary():
    portfolio_summary = build_portfolio_performance_summary()
    risk_data = [
        {"name": name, "value": value}
        for name, value in sorted(portfolio_summary["sector_distribution"].items(), key=lambda item: item[1], reverse=True)
    ]
    return {
        "risk_data": risk_data,
    }


def build_analysis_report():
    model_summary = build_model_performance_summary()
    factor_summary = build_factor_effectiveness_summary()
    portfolio_summary = build_portfolio_performance_summary()
    risk_summary = build_risk_analysis_summary()
    return {
        "generated_at": now_local_iso(),
        "model_performance": model_summary,
        "factor_effectiveness": factor_summary,
        "portfolio_performance": portfolio_summary,
        "risk_analysis": risk_summary,
    }
