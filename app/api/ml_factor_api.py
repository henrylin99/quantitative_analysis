from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from loguru import logger
import pandas as pd
import numpy as np
import json
from flask import Response
from app.services.factor_engine import FactorEngine
from app.services.ml_models import MLModelManager
from app.services.stock_scoring import StockScoringEngine
from app.services.portfolio_optimizer import PortfolioOptimizer
from app.services.backtest_engine import BacktestEngine
from app.services.model_training_job_service import ModelTrainingJobService
from app.services.data_reader import ParquetDataReader
from app.services.parquet_state_store import BacktestRepository, ParquetStateStore, PortfolioRepository

_data_reader = ParquetDataReader()
_state_store = ParquetStateStore()
_portfolio_repo = PortfolioRepository(_state_store)
_backtest_repo = BacktestRepository(_state_store)

# 创建蓝图
ml_factor_bp = Blueprint('ml_factor', __name__, url_prefix='/api/ml-factor')

# 延迟初始化服务实例
factor_engine = None
ml_manager = None
scoring_engine = None
portfolio_optimizer = None
backtest_engine = None
training_job_service = None

SUPPORTED_FACTOR_SCORING_METHODS = {"equal_weight", "factor_weight", "ml_ensemble", "rank_ic"}
SUPPORTED_PORTFOLIO_OPTIMIZATION_METHODS = {"mean_variance", "risk_parity", "equal_weight", "factor_neutral", "black_litterman"}

# JSON序列化辅助函数
def convert_numpy_types(obj):
    """将numpy类型转换为Python原生类型，用于JSON序列化"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj

def get_factor_engine():
    """获取因子引擎实例（延迟初始化）"""
    global factor_engine
    if factor_engine is None:
        factor_engine = FactorEngine()
    return factor_engine

def get_ml_manager():
    """获取ML管理器实例（延迟初始化）"""
    global ml_manager
    if ml_manager is None:
        ml_manager = MLModelManager()
    return ml_manager

def get_scoring_engine():
    """获取评分引擎实例（延迟初始化）"""
    global scoring_engine
    if scoring_engine is None:
        scoring_engine = StockScoringEngine()
    return scoring_engine

def get_portfolio_optimizer():
    """获取投资组合优化器实例（延迟初始化）"""
    global portfolio_optimizer
    if portfolio_optimizer is None:
        portfolio_optimizer = PortfolioOptimizer()
    return portfolio_optimizer

def get_backtest_engine():
    """获取回测引擎实例（延迟初始化）"""
    global backtest_engine
    if backtest_engine is None:
        backtest_engine = BacktestEngine()
    return backtest_engine


def get_training_job_service():
    """获取模型训练任务服务实例（延迟初始化）"""
    global training_job_service
    if training_job_service is None:
        training_job_service = ModelTrainingJobService()
    return training_job_service


def _get_latest_scoring_trade_date():
    """获取评分模块可用的最新交易日期。"""
    try:
        factor_df = get_scoring_engine().factor_repo.get_values()
        if not factor_df.empty and "trade_date" in factor_df.columns:
            latest_trade_date = pd.to_datetime(factor_df["trade_date"], errors="coerce").dropna().max()
            if pd.notna(latest_trade_date):
                return latest_trade_date.strftime("%Y-%m-%d")
    except Exception as e:
        logger.warning(f"读取因子最新交易日期失败: {e}")

    try:
        latest_trade_date = get_factor_engine().data_reader.get_stock_business_latest_date()
        if latest_trade_date:
            return latest_trade_date
    except Exception as e:
        logger.warning(f"读取业务表最新交易日期失败: {e}")

    return datetime.utcnow().strftime("%Y-%m-%d")


def _get_latest_prediction_trade_date():
    """获取 ML 评分可用的最新预测日期。"""
    try:
        prediction_df = get_ml_manager().model_repo.get_predictions()
        if not prediction_df.empty and "trade_date" in prediction_df.columns:
            latest_trade_date = pd.to_datetime(prediction_df["trade_date"], errors="coerce").dropna().max()
            if pd.notna(latest_trade_date):
                return latest_trade_date.strftime("%Y-%m-%d")
    except Exception as e:
        logger.warning(f"读取最新预测日期失败: {e}")

    return None


def _build_model_performance_summary():
    manager = get_ml_manager()
    models = manager.get_model_list()
    performance_data = []
    comparison_data = []
    best_r2 = 0.0

    for model in models:
        model_id = model.get("model_id")
        metrics = manager.evaluate_model(model_id, model.get("created_at", "1970-01-01")[:10], datetime.utcnow().strftime("%Y-%m-%d"))
        if "error" in metrics:
            continue

        r2_score = float(metrics.get("r2") or 0.0)
        mae_score = float(metrics.get("mae") or 0.0)
        best_r2 = max(best_r2, r2_score)
        performance_data.append({
            "date": model.get("created_at", datetime.utcnow().isoformat())[:10],
            "train_r2": float(metrics.get("r2") or 0.0),
            "test_r2": float(metrics.get("r2") or 0.0),
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


def _build_factor_effectiveness_summary():
    definitions = get_factor_engine().get_factor_list(is_active=True)
    importance_data = []
    factor_stats = []
    active_factors = 0

    for factor in definitions:
        if not factor.get("is_active", True):
            continue
        active_factors += 1
        factor_id = factor["factor_id"]
        exposure = get_factor_engine().get_factor_exposure(
            factor_id, get_factor_engine().data_reader.get_stock_business_latest_date() or datetime.utcnow().strftime("%Y-%m-%d")
        )
        if exposure.empty:
            importance = 0.0
            correlation = 0.0
        else:
            series = pd.to_numeric(exposure.get("z_score", exposure.get("factor_value")), errors="coerce")
            importance = float(series.abs().mean()) if not series.empty else 0.0
            correlation = float(series.corr(pd.Series(range(len(series))))) if len(series) > 1 else 0.0

        importance_data.append({
            "factor_name": factor.get("factor_name", factor_id),
            "importance": importance,
            "correlation": correlation,
        })
        factor_stats.append({
            "factor_name": factor.get("factor_name", factor_id),
            "importance": importance,
            "correlation": correlation,
        })

    importance_data.sort(key=lambda item: item["importance"], reverse=True)
    return {
        "active_factors": active_factors,
        "importance_data": importance_data,
        "factor_stats": factor_stats,
    }


def _build_portfolio_performance_summary():
    portfolio_ids = _portfolio_repo.list_portfolio_ids(active_only=True)
    performance_data = []
    portfolio_metrics = []
    all_sector_distribution = {}
    annual_returns = []
    max_drawdowns = []
    sharpe_ratios = []
    win_rates = []

    for portfolio_id in portfolio_ids:
        metrics = _portfolio_repo.calculate_metrics(portfolio_id)
        if not metrics:
            continue
        portfolio_metrics.append(metrics)
        annual_return = float(metrics.get("total_pnl_percentage") or 0.0)
        max_drawdown = float(metrics.get("max_position_weight") or 0.0)
        sharpe_ratio = float(metrics.get("portfolio_var_1d") or 0.0)
        win_rate = 0.0
        annual_returns.append(annual_return)
        max_drawdowns.append(max_drawdown)
        sharpe_ratios.append(sharpe_ratio)
        win_rates.append(win_rate)
        performance_data.append({
            "date": portfolio_id,
            "portfolio_return": annual_return,
            "benchmark_return": 0.0,
        })
        for sector, weight in (metrics.get("sector_distribution") or {}).items():
            all_sector_distribution[sector] = all_sector_distribution.get(sector, 0.0) + float(weight or 0.0)

    return {
        "portfolio_count": len(portfolio_ids),
        "annual_return": float(np.mean(annual_returns)) if annual_returns else 0.0,
        "max_drawdown": float(np.mean(max_drawdowns)) if max_drawdowns else 0.0,
        "sharpe_ratio": float(np.mean(sharpe_ratios)) if sharpe_ratios else 0.0,
        "win_rate": float(np.mean(win_rates) * 100) if win_rates else 0.0,
        "performance_data": performance_data,
        "sector_distribution": all_sector_distribution,
        "portfolio_metrics": portfolio_metrics,
    }


def _build_risk_analysis_summary():
    portfolio_summary = _build_portfolio_performance_summary()
    risk_data = [
        {"name": name, "value": value}
        for name, value in sorted(portfolio_summary["sector_distribution"].items(), key=lambda item: item[1], reverse=True)
    ]
    return {
        "risk_data": risk_data,
    }


def _build_analysis_report():
    model_summary = _build_model_performance_summary()
    factor_summary = _build_factor_effectiveness_summary()
    portfolio_summary = _build_portfolio_performance_summary()
    risk_summary = _build_risk_analysis_summary()
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "model_performance": model_summary,
        "factor_effectiveness": factor_summary,
        "portfolio_performance": portfolio_summary,
        "risk_analysis": risk_summary,
    }


@ml_factor_bp.route('/analysis/model-performance', methods=['GET'])
def get_model_performance_analysis():
    """获取模型性能分析数据"""
    try:
        summary = _build_model_performance_summary()
        return jsonify({
            'success': True,
            **convert_numpy_types(summary),
        })
    except Exception as e:
        logger.error(f"获取模型性能分析失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/analysis/factor-effectiveness', methods=['GET'])
def get_factor_effectiveness_analysis():
    """获取因子有效性分析数据"""
    try:
        summary = _build_factor_effectiveness_summary()
        return jsonify({
            'success': True,
            **convert_numpy_types(summary),
        })
    except Exception as e:
        logger.error(f"获取因子有效性分析失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/analysis/portfolio-performance', methods=['GET'])
def get_portfolio_performance_analysis():
    """获取投资组合表现分析数据"""
    try:
        summary = _build_portfolio_performance_summary()
        return jsonify({
            'success': True,
            **convert_numpy_types(summary),
        })
    except Exception as e:
        logger.error(f"获取投资组合表现分析失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/analysis/risk-analysis', methods=['GET'])
def get_risk_analysis():
    """获取风险分析数据"""
    try:
        summary = _build_risk_analysis_summary()
        return jsonify({
            'success': True,
            **convert_numpy_types(summary),
        })
    except Exception as e:
        logger.error(f"获取风险分析失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/analysis/generate-report', methods=['POST'])
def generate_analysis_report():
    """生成分析报告"""
    try:
        report = _build_analysis_report()
        return jsonify({
            'success': True,
            'report': convert_numpy_types(report),
        })
    except Exception as e:
        logger.error(f"生成分析报告失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/analysis/export-report', methods=['GET'])
def export_analysis_report():
    """导出分析报告"""
    try:
        report = _build_analysis_report()
        payload = json.dumps(convert_numpy_types(report), ensure_ascii=False, indent=2)
        filename = f"ml_factor_analysis_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        response = Response(payload, mimetype='application/json')
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        return response
    except Exception as e:
        logger.error(f"导出分析报告失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/factors/calculate', methods=['POST'])
def calculate_factors():
    """计算因子值"""
    try:
        data = request.get_json()
        
        # 参数验证
        trade_date = data.get('trade_date')
        factor_ids = data.get('factor_ids', [])
        ts_codes = data.get('ts_codes', [])
        
        if not trade_date:
            return jsonify({'error': '缺少交易日期参数'}), 400
        
        # 如果没有指定股票代码，获取所有股票
        if not ts_codes:
            basic_df = _data_reader.get_stock_basic()
            ts_codes = basic_df["ts_code"].tolist()
        
        # 计算因子
        if factor_ids:
            # 计算指定因子
            results = []
            for factor_id in factor_ids:
                try:
                    result_df = get_factor_engine().calculate_factor(factor_id, ts_codes, trade_date, trade_date)
                    if not result_df.empty:
                        # 保存因子值
                        save_success = get_factor_engine().save_factor_values(result_df)
                        results.append({
                            'factor_id': factor_id,
                            'calculated_count': len(result_df),
                            'saved': save_success
                        })
                    else:
                        results.append({
                            'factor_id': factor_id,
                            'calculated_count': 0,
                            'error': '无数据'
                        })
                except Exception as e:
                    results.append({
                        'factor_id': factor_id,
                        'error': str(e)
                    })
        else:
            # 计算所有因子
            try:
                result_df = get_factor_engine().calculate_all_factors(trade_date, ts_codes)
                if not result_df.empty:
                    # 保存因子值
                    save_success = get_factor_engine().save_factor_values(result_df)
                    
                    # 统计各因子计算结果
                    factor_stats = result_df.groupby('factor_id').size().to_dict()
                    results = {
                        'total_calculated': len(result_df),
                        'factor_stats': factor_stats,
                        'saved': save_success
                    }
                else:
                    results = {
                        'total_calculated': 0,
                        'error': '无数据'
                    }
            except Exception as e:
                results = {'error': str(e)}
        
        return jsonify({
            'success': True,
            'trade_date': trade_date,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"计算因子失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/factors/custom', methods=['POST'])
def create_custom_factor():
    """创建自定义因子"""
    try:
        data = request.get_json()
        
        # 参数验证
        required_fields = ['factor_id', 'factor_name', 'factor_formula', 'factor_type']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'缺少必需参数: {field}'}), 400

        validation = get_factor_engine().validate_custom_factor_formula(data['factor_formula'])
        if not validation.get('valid'):
            return jsonify({
                'error': validation.get('error') or '自定义因子公式不合法'
            }), 400
        
        # 创建因子定义
        success = get_factor_engine().create_factor_definition(
            factor_id=data['factor_id'],
            factor_name=data['factor_name'],
            factor_formula=data['factor_formula'],
            factor_type=data['factor_type'],
            description=data.get('description'),
            params=data.get('params', {})
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': f"成功创建自定义因子: {data['factor_id']}"
            })
        else:
            return jsonify({'error': '创建因子失败'}), 500
        
    except Exception as e:
        logger.error(f"创建自定义因子失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/factors/custom-capabilities', methods=['GET'])
def get_custom_factor_capabilities():
    """获取自定义因子表达式能力说明"""
    try:
        return jsonify({
            'success': True,
            'capabilities': get_factor_engine().get_custom_factor_capabilities()
        })
    except Exception as e:
        logger.error(f"获取自定义因子能力失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/factors/builtin-validation-samples', methods=['GET'])
def get_builtin_factor_validation_samples():
    """获取核心内置因子的样例级校验说明"""
    try:
        return jsonify({
            'success': True,
            'samples': get_factor_engine().get_builtin_factor_validation_samples()
        })
    except Exception as e:
        logger.error(f"获取内置因子样例失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/factors/list', methods=['GET'])
def get_factor_list():
    """获取因子列表"""
    try:
        factor_type = request.args.get('factor_type')
        is_active = request.args.get('is_active', 'true').lower() == 'true'
        
        factors = get_factor_engine().get_factor_list(factor_type, is_active)
        
        return jsonify({
            'success': True,
            'factors': factors,
            'total_count': len(factors)
        })
        
    except Exception as e:
        logger.error(f"获取因子列表失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/models/create', methods=['POST'])
def create_ml_model():
    """创建机器学习模型"""
    try:
        data = request.get_json()
        
        # 参数验证
        required_fields = ['model_id', 'model_name', 'model_type', 'factor_list', 'target_type']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'缺少必需参数: {field}'}), 400

        if not get_ml_manager().is_supported_target_type(data['target_type']):
            return jsonify({
                'error': f"不支持的target_type: {data['target_type']}"
            }), 400
        
        # 创建模型定义
        success = get_ml_manager().create_model_definition(
            model_id=data['model_id'],
            model_name=data['model_name'],
            model_type=data['model_type'],
            factor_list=data['factor_list'],
            target_type=data['target_type'],
            model_params=data.get('model_params'),
            training_config=data.get('training_config')
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': f"成功创建模型定义: {data['model_id']}"
            })
        else:
            return jsonify({'error': '创建模型定义失败'}), 500
        
    except Exception as e:
        logger.error(f"创建机器学习模型失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/models/train', methods=['POST'])
def train_ml_model():
    """提交机器学习模型训练任务"""
    try:
        data = request.get_json()
        
        # 参数验证
        model_id = data.get('model_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not all([model_id, start_date, end_date]):
            return jsonify({'error': '缺少必需参数: model_id, start_date, end_date'}), 400
        
        job = get_training_job_service().submit_job(model_id, start_date, end_date)
        return jsonify({
            'success': True,
            'message': f"训练任务已提交: {model_id}",
            'job_id': job['job_id'],
            'status': job['status'],
            'progress': job.get('progress', 0.0),
            'step': job.get('step', ''),
            'logs': job.get('logs', []),
            'start_date': job.get('start_date'),
            'end_date': job.get('end_date'),
            'requested_start_date': job.get('requested_start_date'),
            'requested_end_date': job.get('requested_end_date'),
            'date_range_adjusted': job.get('date_range_adjusted', False),
        }), 202
        
    except Exception as e:
        logger.error(f"训练机器学习模型失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/models/<model_id>/training-date-range', methods=['GET'])
def suggest_model_training_date_range(model_id):
    """获取模型训练建议日期区间"""
    try:
        date_range = get_ml_manager().suggest_training_date_range(model_id)
        return jsonify({
            'success': True,
            'date_range': convert_numpy_types(date_range),
        })
    except Exception as e:
        logger.error(f"获取模型训练建议日期失败: {model_id}, 错误: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/models/train-jobs/<job_id>', methods=['GET'])
def get_train_job_status(job_id):
    """获取训练任务状态"""
    try:
        job = get_training_job_service().get_job_snapshot(job_id)
        if job is None:
            return jsonify({'error': f'未找到训练任务: {job_id}'}), 404
        return jsonify({
            'success': True,
            'job': convert_numpy_types(job)
        })
    except Exception as e:
        logger.error(f"获取训练任务状态失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/models/predict', methods=['POST'])
def predict_with_model():
    """使用模型进行预测"""
    try:
        data = request.get_json()
        
        # 参数验证
        model_id = data.get('model_id')
        trade_date = data.get('trade_date')
        ts_codes = data.get('ts_codes')
        
        if not all([model_id, trade_date]):
            return jsonify({'error': '缺少必需参数: model_id, trade_date'}), 400
        
        # 进行预测
        predictions = get_ml_manager().predict(model_id, trade_date, ts_codes)
        
        if predictions.empty:
            return jsonify({'error': '预测失败或无数据'}), 500
        
        # 保存预测结果
        save_success = get_ml_manager().save_predictions(predictions)
        
        # 转换预测结果为JSON可序列化格式
        predictions_dict = predictions.to_dict('records')
        predictions_dict = convert_numpy_types(predictions_dict)
        
        if save_success:
            return jsonify({
                'success': True,
                'message': f"预测完成: {len(predictions)} 只股票",
                'predictions': predictions_dict
            })
        else:
            return jsonify({
                'success': True,
                'message': f"预测完成但保存失败: {len(predictions)} 只股票",
                'predictions': predictions_dict
            })
        
    except Exception as e:
        logger.error(f"模型预测失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/models/evaluate', methods=['POST'])
def evaluate_model():
    """评估模型性能"""
    try:
        data = request.get_json()
        
        # 参数验证
        model_id = data.get('model_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not all([model_id, start_date, end_date]):
            return jsonify({'error': '缺少必需参数: model_id, start_date, end_date'}), 400
        
        # 评估模型
        metrics = get_ml_manager().evaluate_model(model_id, start_date, end_date)
        
        if 'error' in metrics:
            return jsonify({'error': metrics['error']}), 500
        
        return jsonify({
            'success': True,
            'model_id': model_id,
            'evaluation_period': f"{start_date} to {end_date}",
            'metrics': metrics
        })
        
    except Exception as e:
        logger.error(f"模型评估失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/models/list', methods=['GET'])
def get_model_list():
    """获取模型列表"""
    try:
        models = get_ml_manager().get_model_list()
        
        return jsonify({
            'success': True,
            'models': models,
            'total_count': len(models)
        })
        
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/models/<model_id>', methods=['GET'])
def get_model_detail(model_id):
    """获取模型详情"""
    try:
        model = get_ml_manager().get_model_detail(model_id)
        if not model:
            return jsonify({'error': f'未找到模型: {model_id}'}), 404
        return jsonify({
            'success': True,
            'model': convert_numpy_types(model),
        })
    except Exception as e:
        logger.error(f"获取模型详情失败: {model_id}, 错误: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/models/<model_id>', methods=['DELETE'])
def delete_model(model_id):
    """删除模型定义、预测结果和本地模型文件"""
    try:
        result = get_ml_manager().delete_model(model_id)

        if result.get('success'):
            return jsonify(result)

        error_message = result.get('error', '删除模型失败')
        status_code = 404 if '未找到模型定义' in error_message else 500
        return jsonify({'error': error_message}), status_code

    except Exception as e:
        logger.error(f"删除模型失败: {model_id}, 错误: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/scoring/factor-based', methods=['POST'])
def factor_based_scoring():
    """基于因子的股票打分"""
    try:
        data = request.get_json()
        
        # 参数验证
        trade_date = data.get('trade_date')
        if not trade_date:
            return jsonify({'error': '缺少交易日期参数'}), 400
        
        factor_list = data.get('factor_list')
        ts_codes = data.get('ts_codes')
        weights = data.get('weights', {})
        method = data.get('method', 'equal_weight')
        top_n = data.get('top_n', 50)
        filters = data.get('filters')

        if method not in SUPPORTED_FACTOR_SCORING_METHODS:
            return jsonify({
                'error': f"不支持的评分方法: {method}",
                'supported_methods': sorted(SUPPORTED_FACTOR_SCORING_METHODS)
            }), 400
        
        # 计算因子分数
        factor_scores = get_scoring_engine().calculate_factor_scores(trade_date, factor_list, ts_codes)
        
        if factor_scores.empty:
            return jsonify({'error': '未找到因子数据'}), 404
        
        # 计算综合分数
        composite_scores = get_scoring_engine().calculate_composite_score(factor_scores, weights, method)
        
        if composite_scores.empty:
            return jsonify({'error': '计算综合分数失败'}), 500
        
        # 股票排名选择
        top_stocks = get_scoring_engine().rank_stocks(composite_scores, top_n, filters)
        
        return jsonify({
            'success': True,
            'trade_date': trade_date,
            'method': method,
            'total_stocks': len(composite_scores),
            'selected_stocks': len(top_stocks),
            'top_stocks': top_stocks
        })
        
    except Exception as e:
        logger.error(f"基于因子的股票打分失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/scoring/latest-trade-date', methods=['GET'])
def latest_scoring_trade_date():
    """返回评分页面可用的最新交易日期。"""
    try:
        latest_trade_date = _get_latest_scoring_trade_date()
        return jsonify({
            'success': True,
            'latest_trade_date': latest_trade_date,
        })
    except Exception as e:
        logger.error(f"获取最新评分交易日期失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/scoring/latest-prediction-date', methods=['GET'])
def latest_prediction_trade_date():
    """返回 ML 评分页面可用的最新预测日期。"""
    try:
        latest_trade_date = _get_latest_prediction_trade_date()
        if not latest_trade_date:
            return jsonify({
                'success': False,
                'latest_trade_date': None,
                'error': '未找到预测数据',
            }), 404
        return jsonify({
            'success': True,
            'latest_trade_date': latest_trade_date,
        })
    except Exception as e:
        logger.error(f"获取最新预测日期失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/scoring/ml-based', methods=['POST'])
def ml_based_scoring():
    """基于机器学习的股票选择"""
    try:
        data = request.get_json()
        
        # 参数验证
        trade_date = data.get('trade_date')
        model_ids = data.get('model_ids', [])
        
        if not trade_date:
            return jsonify({'error': '缺少交易日期参数'}), 400
        
        if not model_ids:
            return jsonify({'error': '缺少模型ID参数'}), 400
        
        top_n = data.get('top_n', 50)
        ensemble_method = data.get('ensemble_method', 'average')
        
        # 基于ML模型选股
        top_stocks = get_scoring_engine().ml_based_selection(trade_date, model_ids, top_n, ensemble_method)
        
        if not top_stocks:
            return jsonify({'error': '未找到预测数据或选股失败'}), 404
        
        return jsonify({
            'success': True,
            'trade_date': trade_date,
            'model_ids': model_ids,
            'ensemble_method': ensemble_method,
            'selected_stocks': len(top_stocks),
            'top_stocks': top_stocks
        })
        
    except Exception as e:
        logger.error(f"基于机器学习的股票选择失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/analysis/factor-contribution', methods=['POST'])
def factor_contribution_analysis():
    """因子贡献度分析"""
    try:
        data = request.get_json()
        
        # 参数验证
        ts_code = data.get('ts_code')
        trade_date = data.get('trade_date')
        
        if not all([ts_code, trade_date]):
            return jsonify({'error': '缺少必需参数: ts_code, trade_date'}), 400
        
        factor_list = data.get('factor_list')
        
        # 进行因子贡献度分析
        analysis_result = get_scoring_engine().factor_contribution_analysis(ts_code, trade_date, factor_list)
        
        if 'error' in analysis_result:
            return jsonify({'error': analysis_result['error']}), 404
        
        return jsonify({
            'success': True,
            'analysis': analysis_result
        })
        
    except Exception as e:
        logger.error(f"因子贡献度分析失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/analysis/sector', methods=['POST'])
def sector_analysis():
    """行业分析"""
    try:
        data = request.get_json()
        
        # 参数验证
        trade_date = data.get('trade_date')
        if not trade_date:
            return jsonify({'error': '缺少交易日期参数'}), 400
        
        factor_list = data.get('factor_list')
        top_n = data.get('top_n', 10)
        
        # 进行行业分析
        analysis_result = get_scoring_engine().sector_analysis(trade_date, factor_list, top_n)
        
        if 'error' in analysis_result:
            return jsonify({'error': analysis_result['error']}), 404
        
        return jsonify({
            'success': True,
            'analysis': analysis_result
        })
        
    except Exception as e:
        logger.error(f"行业分析失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/batch/calculate-and-score', methods=['POST'])
def batch_calculate_and_score():
    """批量计算因子并打分"""
    try:
        data = request.get_json()
        
        # 参数验证
        trade_date = data.get('trade_date')
        if not trade_date:
            return jsonify({'error': '缺少交易日期参数'}), 400
        
        factor_list = data.get('factor_list', [])
        ts_codes = data.get('ts_codes')
        weights = data.get('weights', {})
        method = data.get('method', 'equal_weight')
        top_n = data.get('top_n', 50)
        
        # 步骤1: 计算因子
        if factor_list:
            factor_results = []
            for factor_id in factor_list:
                result = get_factor_engine().calculate_factor(factor_id, trade_date, ts_codes)
                factor_results.append({
                    'factor_id': factor_id,
                    'success': result['success'],
                    'calculated_count': result.get('calculated_count', 0)
                })
        else:
            # 计算所有因子
            factor_results = get_factor_engine().calculate_all_factors(trade_date, ts_codes)
        
        # 步骤2: 计算因子分数
        factor_scores = get_scoring_engine().calculate_factor_scores(trade_date, factor_list, ts_codes)
        
        if factor_scores.empty:
            return jsonify({
                'success': False,
                'error': '未找到因子数据',
                'factor_calculation': factor_results
            }), 404
        
        # 步骤3: 计算综合分数
        composite_scores = get_scoring_engine().calculate_composite_score(factor_scores, weights, method)
        
        # 步骤4: 股票排名选择
        top_stocks = get_scoring_engine().rank_stocks(composite_scores, top_n)
        
        return jsonify({
            'success': True,
            'trade_date': trade_date,
            'factor_calculation': factor_results,
            'scoring_method': method,
            'total_stocks': len(composite_scores),
            'selected_stocks': len(top_stocks),
            'top_stocks': top_stocks
        })
        
    except Exception as e:
        logger.error(f"批量计算因子并打分失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/batch/train-and-predict', methods=['POST'])
def batch_train_and_predict():
    """批量训练模型并预测"""
    try:
        data = request.get_json()
        
        # 参数验证
        model_configs = data.get('model_configs', [])
        train_start_date = data.get('train_start_date')
        train_end_date = data.get('train_end_date')
        predict_date = data.get('predict_date')
        
        if not all([model_configs, train_start_date, train_end_date, predict_date]):
            return jsonify({'error': '缺少必需参数'}), 400
        
        results = []
        
        for config in model_configs:
            try:
                model_id = config['model_id']
                
                # 创建模型定义
                create_success = get_ml_manager().create_model_definition(
                    model_id=model_id,
                    model_name=config['model_name'],
                    model_type=config['model_type'],
                    factor_list=config['factor_list'],
                    target_type=config['target_type'],
                    model_params=config.get('model_params'),
                    training_config=config.get('training_config')
                )
                
                if not create_success:
                    results.append({
                        'model_id': model_id,
                        'create_success': False,
                        'error': '创建模型定义失败'
                    })
                    continue
                
                # 训练模型
                train_result = get_ml_manager().train_model(model_id, train_start_date, train_end_date)
                
                if not train_result['success']:
                    results.append({
                        'model_id': model_id,
                        'create_success': True,
                        'train_success': False,
                        'error': train_result['error']
                    })
                    continue
                
                # 进行预测
                predictions = get_ml_manager().predict(model_id, predict_date)
                
                if predictions.empty:
                    results.append({
                        'model_id': model_id,
                        'create_success': True,
                        'train_success': True,
                        'predict_success': False,
                        'error': '预测失败'
                    })
                    continue
                
                # 保存预测结果
                save_success = get_ml_manager().save_predictions(predictions)
                
                results.append({
                    'model_id': model_id,
                    'create_success': True,
                    'train_success': True,
                    'predict_success': True,
                    'save_success': save_success,
                    'train_metrics': train_result['metrics'],
                    'prediction_count': len(predictions)
                })
                
            except Exception as e:
                results.append({
                    'model_id': config.get('model_id', 'unknown'),
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'train_period': f"{train_start_date} to {train_end_date}",
            'predict_date': predict_date,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"批量训练模型并预测失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/portfolio/optimize', methods=['POST'])
def optimize_portfolio():
    """组合优化"""
    try:
        data = request.get_json()
        
        # 参数验证
        expected_returns = data.get('expected_returns')
        if not expected_returns:
            return jsonify({'error': '缺少预期收益率数据'}), 400
        
        # 转换为pandas Series
        expected_returns_series = pd.Series(expected_returns)
        
        method = data.get('method', 'mean_variance')
        constraints = data.get('constraints')
        risk_model = data.get('risk_model')  # 可选，如果不提供会自动估计

        if method not in SUPPORTED_PORTFOLIO_OPTIMIZATION_METHODS:
            return jsonify({
                'error': f"不支持的优化方法: {method}",
                'supported_methods': sorted(SUPPORTED_PORTFOLIO_OPTIMIZATION_METHODS)
            }), 400

        # 转换风险模型
        risk_model_df = None
        if risk_model:
            risk_model_df = pd.DataFrame(risk_model)
        
        # 执行组合优化
        result = get_portfolio_optimizer().optimize_portfolio(
            expected_returns_series, 
            risk_model_df, 
            method, 
            constraints
        )
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"组合优化失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/portfolio/list', methods=['GET'])
def get_portfolio_list():
    """基于真实持仓表返回投资组合列表摘要"""
    try:
        portfolios = []
        for portfolio_id in _portfolio_repo.list_portfolio_ids(active_only=True):
            metrics = _portfolio_repo.calculate_metrics(portfolio_id)
            positions = _portfolio_repo.list_positions(portfolio_id, active_only=True)
            first_position = positions[0] if positions else None

            portfolios.append({
                'portfolio_id': portfolio_id,
                'name': portfolio_id,
                'position_count': metrics.get('total_positions', 0),
                'current_value': metrics.get('total_market_value', 0.0),
                'unrealized_pnl': metrics.get('total_unrealized_pnl', 0.0),
                'return_rate': (metrics.get('total_pnl_percentage', 0.0) or 0.0) / 100.0,
                'max_position_weight': (metrics.get('max_position_weight', 0.0) or 0.0) / 100.0,
                'created_at': first_position.get('created_at') if first_position else None,
            })

        return jsonify({
            'success': True,
            'portfolios': portfolios,
            'total_count': len(portfolios),
        })

    except Exception as e:
        logger.error(f"获取投资组合列表失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/portfolio/<portfolio_id>', methods=['GET'])
def get_portfolio_detail(portfolio_id):
    """获取真实投资组合详情"""
    try:
        positions = _portfolio_repo.list_positions(portfolio_id)
        metrics = _portfolio_repo.calculate_metrics(portfolio_id)

        if not positions or not metrics:
            return jsonify({'error': f'未找到投资组合: {portfolio_id}'}), 404

        return jsonify({
            'success': True,
            'portfolio': {
                'portfolio_id': portfolio_id,
                'name': portfolio_id,
                'metrics': metrics,
                'positions': positions,
            }
        })

    except Exception as e:
        logger.error(f"获取投资组合详情失败: {portfolio_id}, 错误: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/portfolio/<portfolio_id>', methods=['DELETE'])
def delete_portfolio(portfolio_id):
    """软删除整个投资组合下的所有持仓"""
    try:
        deactivated_count = _portfolio_repo.deactivate_portfolio(portfolio_id)
        if deactivated_count == 0:
            return jsonify({'error': f'未找到投资组合: {portfolio_id}'}), 404

        return jsonify({
            'success': True,
            'portfolio_id': portfolio_id,
            'deactivated_count': deactivated_count,
        })

    except Exception as e:
        logger.error(f"删除投资组合失败: {portfolio_id}, 错误: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/portfolio/save-optimized', methods=['POST'])
def save_optimized_portfolio():
    """将优化结果保存为真实组合持仓"""
    try:
        data = request.get_json()
        portfolio_id = data.get('portfolio_id')
        total_capital = float(data.get('total_capital', 0))
        weights = data.get('weights') or {}

        if not portfolio_id:
            return jsonify({'error': '缺少必需参数: portfolio_id'}), 400
        if total_capital <= 0:
            return jsonify({'error': 'total_capital必须大于0'}), 400
        if not weights:
            return jsonify({'error': '缺少必需参数: weights'}), 400

        existing = _portfolio_repo.list_positions(portfolio_id, active_only=True)
        if existing:
            return jsonify({'error': f'投资组合已存在: {portfolio_id}'}), 400

        created_count = 0
        for ts_code, weight in weights.items():
            allocation = total_capital * float(weight)
            close_price = _data_reader.get_latest_close(ts_code)
            if close_price is None:
                close_price = 1.0
            position_size = allocation / close_price if close_price > 0 else 0

            _portfolio_repo.upsert_position(
                {
                    'portfolio_id': portfolio_id,
                    'ts_code': ts_code,
                    'position_size': position_size,
                    'avg_cost': close_price,
                    'current_price': close_price,
                    'market_value': allocation,
                    'unrealized_pnl': 0.0,
                    'weight': float(weight) * 100,
                }
            )
            created_count += 1

        return jsonify({
            'success': True,
            'portfolio_id': portfolio_id,
            'created_count': created_count,
        })

    except Exception as e:
        logger.error(f"保存优化组合失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/portfolio', methods=['POST'])
def create_portfolio_position():
    """创建真实投资组合的首个持仓（parquet 存储）。"""
    try:
        data = request.get_json()
        portfolio_id = data.get('portfolio_id')
        ts_code = data.get('ts_code')
        position_size = data.get('position_size')
        avg_cost = data.get('avg_cost')
        sector = data.get('sector')

        if not all([portfolio_id, ts_code, position_size, avg_cost]):
            return jsonify({'success': False, 'message': '必填字段不能为空'}), 400

        existing_position = _portfolio_repo.get_position_by_stock(portfolio_id, ts_code)
        if existing_position:
            return jsonify({'success': False, 'message': '该股票持仓已存在'}), 200

        position = _portfolio_repo.upsert_position(
            {
                'portfolio_id': portfolio_id,
                'ts_code': ts_code,
                'position_size': float(position_size),
                'avg_cost': float(avg_cost),
                'current_price': float(avg_cost),
                'market_value': float(position_size) * float(avg_cost),
                'unrealized_pnl': 0.0,
                'sector': sector,
                'is_active': True,
            }
        )

        return jsonify({
            'success': True,
            'data': position,
            'message': '持仓创建成功',
        })

    except Exception as e:
        logger.error(f"创建持仓失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ml_factor_bp.route('/portfolio/<portfolio_id>/positions/<int:position_id>', methods=['PUT'])
def update_portfolio_position(portfolio_id, position_id):
    """更新真实投资组合持仓（parquet 存储）。"""
    try:
        data = request.get_json()
        positions = _portfolio_repo.list_positions(portfolio_id, active_only=False)
        target = next((pos for pos in positions if int(pos.get('id') or 0) == int(position_id)), None)
        if not target:
            return jsonify({'success': False, 'message': '持仓记录不存在'}), 404

        target.update({
            'position_size': float(data.get('position_size', target.get('position_size') or 0)),
            'avg_cost': float(data.get('avg_cost', target.get('avg_cost') or 0)),
            'current_price': float(data.get('current_price', target.get('current_price') or data.get('avg_cost', 0))),
            'sector': data.get('sector', target.get('sector')),
            'stop_loss_price': data.get('stop_loss_price', target.get('stop_loss_price')),
            'take_profit_price': data.get('take_profit_price', target.get('take_profit_price')),
            'is_active': True,
        })
        target['market_value'] = float(target['position_size']) * float(target['current_price'])
        target['unrealized_pnl'] = (float(target['current_price']) - float(target['avg_cost'])) * float(target['position_size'])
        _portfolio_repo.upsert_position(target)

        return jsonify({
            'success': True,
            'data': target,
            'message': '持仓更新成功',
        })

    except Exception as e:
        logger.error(f"更新持仓失败: {portfolio_id}, {position_id}, 错误: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ml_factor_bp.route('/portfolio/<portfolio_id>/positions/<int:position_id>', methods=['DELETE'])
def delete_portfolio_position(portfolio_id, position_id):
    """删除真实投资组合持仓（parquet 存储）。"""
    try:
        positions = _portfolio_repo.list_positions(portfolio_id, active_only=False)
        target = next((pos for pos in positions if int(pos.get('id') or 0) == int(position_id)), None)
        if not target:
            return jsonify({'success': False, 'message': '持仓记录不存在'}), 404

        target['is_active'] = False
        _portfolio_repo.upsert_position(target)
        return jsonify({
            'success': True,
            'message': '持仓删除成功',
        })

    except Exception as e:
        logger.error(f"删除持仓失败: {portfolio_id}, {position_id}, 错误: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@ml_factor_bp.route('/portfolio/rebalance', methods=['POST'])
def rebalance_portfolio():
    """组合再平衡"""
    try:
        data = request.get_json()
        
        # 参数验证
        current_weights = data.get('current_weights')
        target_weights = data.get('target_weights')
        
        if not all([current_weights, target_weights]):
            return jsonify({'error': '缺少必需参数: current_weights, target_weights'}), 400
        
        # 转换为pandas Series
        current_weights_series = pd.Series(current_weights)
        target_weights_series = pd.Series(target_weights)
        
        transaction_cost = data.get('transaction_cost', 0.001)
        
        # 执行再平衡
        result = get_portfolio_optimizer().rebalance_portfolio(
            current_weights_series,
            target_weights_series,
            transaction_cost
        )
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"组合再平衡失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/portfolio/rebalance/apply', methods=['POST'])
def apply_portfolio_rebalance():
    """按目标权重执行真实组合再平衡"""
    try:
        data = request.get_json()
        portfolio_id = data.get('portfolio_id')
        target_weights = data.get('target_weights') or {}
        rebalance_note = data.get('rebalance_note')

        if not portfolio_id:
            return jsonify({'error': '缺少必需参数: portfolio_id'}), 400
        if not target_weights:
            return jsonify({'error': '缺少必需参数: target_weights'}), 400

        positions = _portfolio_repo.list_positions(portfolio_id)
        if not positions:
            return jsonify({'error': f'未找到投资组合: {portfolio_id}'}), 404

        total_market_value = sum((float(position.get('market_value') or 0)) for position in positions)
        if total_market_value <= 0:
            return jsonify({'error': '组合缺少有效市值数据，无法执行再平衡'}), 400

        existing_by_code = {position['ts_code']: position for position in positions}
        updated_count = 0
        created_count = 0
        deactivated_count = 0

        for ts_code, weight in target_weights.items():
            target_weight = float(weight)
            allocation = total_market_value * target_weight
            close_price = _data_reader.get_latest_close(ts_code)

            existing_position = _portfolio_repo.get_position_by_stock(portfolio_id, ts_code)
            if close_price is None and existing_position and existing_position.get('current_price'):
                close_price = float(existing_position['current_price'])
            elif close_price is None and existing_position and existing_position.get('avg_cost'):
                close_price = float(existing_position['avg_cost'])
            elif close_price is None:
                close_price = 1.0

            position_size = allocation / close_price if close_price > 0 else 0

            if existing_position:
                existing_position.update({
                    'position_size': position_size,
                    'current_price': close_price,
                    'market_value': allocation,
                    'weight': target_weight * 100,
                    'is_active': True,
                })
                _portfolio_repo.upsert_position(existing_position)
                updated_count += 1
            else:
                _portfolio_repo.upsert_position(
                    {
                        'portfolio_id': portfolio_id,
                        'ts_code': ts_code,
                        'position_size': position_size,
                        'avg_cost': close_price,
                        'current_price': close_price,
                        'market_value': allocation,
                        'unrealized_pnl': 0.0,
                        'weight': target_weight * 100,
                        'is_active': True,
                    }
                )
                created_count += 1

        for ts_code, position in existing_by_code.items():
            if ts_code not in target_weights and position.get('is_active', True):
                position['is_active'] = False
                _portfolio_repo.upsert_position(position)
                deactivated_count += 1

        rebalance_summary = {
            'updated_count': updated_count,
            'created_count': created_count,
            'deactivated_count': deactivated_count,
            'target_weight_count': len(target_weights),
        }

        return jsonify({
            'success': True,
            'portfolio_id': portfolio_id,
            'updated_count': updated_count,
            'created_count': created_count,
            'deactivated_count': deactivated_count,
            'rebalance_run_id': None,
            'rebalance_note': rebalance_note,
        })

    except Exception as e:
        logger.error(f"执行组合再平衡失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/portfolio/integrated-selection', methods=['POST'])
def integrated_portfolio_selection():
    """集成选股和组合优化"""
    try:
        data = request.get_json()
        
        # 参数验证
        trade_date = data.get('trade_date')
        if not trade_date:
            return jsonify({'error': '缺少交易日期参数'}), 400
        
        # 选股参数
        selection_method = data.get('selection_method', 'factor_based')  # factor_based 或 ml_based
        factor_list = data.get('factor_list')
        model_ids = data.get('model_ids', [])
        weights_config = data.get('weights', {})
        top_n = data.get('top_n', 100)
        
        # 组合优化参数
        optimization_method = data.get('optimization_method', 'equal_weight')
        constraints = data.get('constraints')

        if optimization_method not in SUPPORTED_PORTFOLIO_OPTIMIZATION_METHODS:
            return jsonify({
                'error': f"不支持的优化方法: {optimization_method}",
                'supported_methods': sorted(SUPPORTED_PORTFOLIO_OPTIMIZATION_METHODS)
            }), 400

        # 步骤1: 股票选择
        if selection_method == 'ml_based' and model_ids:
            # 基于ML模型选股
            selected_stocks = get_scoring_engine().ml_based_selection(
                trade_date, model_ids, top_n, 'average'
            )
            
            if not selected_stocks:
                return jsonify({'error': 'ML选股失败'}), 500
            
            # 提取预期收益率
            expected_returns = pd.Series({
                stock['ts_code']: stock['ensemble_score'] 
                for stock in selected_stocks
            })
            
        else:
            # 基于因子选股
            factor_scores = get_scoring_engine().calculate_factor_scores(trade_date, factor_list)
            
            if factor_scores.empty:
                return jsonify({'error': '未找到因子数据'}), 404
            
            composite_scores = get_scoring_engine().calculate_composite_score(
                factor_scores, weights_config, 'factor_weight'
            )
            
            if composite_scores.empty:
                return jsonify({'error': '计算综合分数失败'}), 500
            
            # 选择前N只股票
            top_stocks_data = get_scoring_engine().rank_stocks(composite_scores, top_n)
            
            if not top_stocks_data:
                return jsonify({'error': '选股失败'}), 500
            
            # 提取预期收益率
            expected_returns = pd.Series({
                stock['ts_code']: stock['composite_score'] 
                for stock in top_stocks_data
            })
        
        # 步骤2: 组合优化
        optimization_result = get_portfolio_optimizer().optimize_portfolio(
            expected_returns,
            method=optimization_method,
            constraints=constraints
        )
        
        if 'error' in optimization_result:
            return jsonify({'error': f"组合优化失败: {optimization_result['error']}"}), 500
        
        # 整合结果
        final_result = {
            'success': True,
            'trade_date': trade_date,
            'selection_method': selection_method,
            'optimization_method': optimization_method,
            'stock_selection': {
                'total_candidates': len(expected_returns),
                'selection_scores': expected_returns.to_dict()
            },
            'portfolio_optimization': optimization_result,
            'final_portfolio': {
                'weights': optimization_result['weights'],
                'stats': optimization_result['portfolio_stats']
            }
        }
        
        return jsonify(final_result)
        
    except Exception as e:
        logger.error(f"集成选股和组合优化失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/backtest/run', methods=['POST'])
def run_backtest():
    """运行回测"""
    try:
        data = request.get_json()
        
        # 参数验证
        strategy_config = data.get('strategy_config')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not all([strategy_config, start_date, end_date]):
            return jsonify({'error': '缺少必需参数: strategy_config, start_date, end_date'}), 400
        
        initial_capital = data.get('initial_capital', 1000000.0)
        rebalance_frequency = data.get('rebalance_frequency', 'monthly')
        
        # 执行回测
        result = get_backtest_engine().run_backtest(
            strategy_config,
            start_date,
            end_date,
            initial_capital,
            rebalance_frequency
        )
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"回测失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/backtest/runs/<int:run_id>', methods=['GET'])
def get_backtest_run(run_id):
    """获取回测运行记录"""
    try:
        run = _backtest_repo.get_run(run_id)
        if run is None:
            return jsonify({'error': '回测记录不存在'}), 404
        return jsonify({
            'success': True,
            'run': run,
        })
    except Exception as e:
        logger.error(f"获取回测记录失败: {e}")
        return jsonify({'error': str(e)}), 500


@ml_factor_bp.route('/backtest/compare', methods=['POST'])
def compare_strategies():
    """比较多个策略"""
    try:
        data = request.get_json()
        
        # 参数验证
        strategies = data.get('strategies')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not all([strategies, start_date, end_date]):
            return jsonify({'error': '缺少必需参数: strategies, start_date, end_date'}), 400
        
        if not isinstance(strategies, list) or len(strategies) < 2:
            return jsonify({'error': '至少需要2个策略进行比较'}), 400
        
        # 执行策略比较
        result = get_backtest_engine().compare_strategies(strategies, start_date, end_date)
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 500
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"策略比较失败: {e}")
        return jsonify({'error': str(e)}), 500
