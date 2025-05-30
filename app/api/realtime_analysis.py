"""
实时交易分析API路由
提供实时数据管理、技术指标、交易信号等功能的API接口
"""

from flask import Blueprint, request, jsonify
from app.services.realtime_data_manager import RealtimeDataManager
from app.models.stock_minute_data import StockMinuteData
from app.extensions import db
import logging

# 配置日志
logger = logging.getLogger(__name__)

# 创建蓝图
realtime_analysis_bp = Blueprint('realtime_analysis', __name__, url_prefix='/api/realtime-analysis')

# 初始化数据管理器
data_manager = RealtimeDataManager()


@realtime_analysis_bp.route('/data/sync', methods=['POST'])
def sync_minute_data():
    """同步分钟级数据"""
    try:
        data = request.get_json()
        ts_code = data.get('ts_code')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        period_type = data.get('period_type', '1min')
        use_baostock = data.get('use_baostock', True)
        
        if not ts_code:
            return jsonify({
                'success': False,
                'message': '股票代码不能为空'
            }), 400
        
        # 执行数据同步
        result = data_manager.sync_minute_data(
            ts_code, start_date, end_date, period_type, use_baostock
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"同步数据API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'同步失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/sync-multiple', methods=['POST'])
def sync_multiple_stocks():
    """批量同步多个股票的分钟数据"""
    try:
        data = request.get_json()
        stock_list = data.get('stock_list', [])
        period_type = data.get('period_type', '1min')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        batch_size = data.get('batch_size', 10)
        use_baostock = data.get('use_baostock', True)
        
        if not stock_list:
            return jsonify({
                'success': False,
                'message': '股票列表不能为空'
            }), 400
        
        # 执行批量同步
        result = data_manager.sync_multiple_stocks_data(
            stock_list, period_type, start_date, end_date, batch_size, use_baostock
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"批量同步API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'批量同步失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/sync-all-periods', methods=['POST'])
def sync_all_periods():
    """同步单个股票的所有周期数据"""
    try:
        data = request.get_json()
        ts_code = data.get('ts_code')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        use_baostock = data.get('use_baostock', True)
        
        if not ts_code:
            return jsonify({
                'success': False,
                'message': '股票代码不能为空'
            }), 400
        
        # 执行所有周期同步
        result = data_manager.sync_all_periods_for_stock(
            ts_code, start_date, end_date, use_baostock
        )
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        logger.error(f"同步所有周期API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'同步失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/stock-list', methods=['GET'])
def get_stock_list():
    """获取数据库中的股票列表"""
    try:
        stock_list = data_manager.get_stock_list_from_db()
        
        return jsonify({
            'success': True,
            'data': stock_list,
            'count': len(stock_list)
        })
        
    except Exception as e:
        logger.error(f"获取股票列表API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/sync-status', methods=['GET'])
def get_sync_status():
    """获取数据同步状态"""
    try:
        ts_code = request.args.get('ts_code')
        period_type = request.args.get('period_type', '1min')
        
        if not ts_code:
            return jsonify({
                'success': False,
                'message': '股票代码不能为空'
            }), 400
        
        # 获取最新数据时间
        latest_data = StockMinuteData.query.filter_by(
            ts_code=ts_code,
            period_type=period_type
        ).order_by(StockMinuteData.datetime.desc()).first()
        
        if latest_data:
            latest_time = latest_data.datetime.isoformat()
            data_count = StockMinuteData.query.filter_by(
                ts_code=ts_code,
                period_type=period_type
            ).count()
        else:
            latest_time = None
            data_count = 0
        
        return jsonify({
            'success': True,
            'data': {
                'ts_code': ts_code,
                'period_type': period_type,
                'latest_time': latest_time,
                'data_count': data_count,
                'has_data': data_count > 0
            }
        })
        
    except Exception as e:
        logger.error(f"获取同步状态API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/aggregate', methods=['POST'])
def aggregate_data():
    """数据聚合"""
    try:
        data = request.get_json()
        ts_code = data.get('ts_code')
        source_period = data.get('source_period', '1min')
        target_period = data.get('target_period', '5min')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not ts_code:
            return jsonify({
                'success': False,
                'message': '股票代码不能为空'
            }), 400
        
        # 执行数据聚合
        result = data_manager.aggregate_data(
            ts_code, source_period, target_period, start_date, end_date
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"数据聚合API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'聚合失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/quality', methods=['GET'])
def check_data_quality():
    """检查数据质量"""
    try:
        ts_code = request.args.get('ts_code')
        period_type = request.args.get('period_type', '1min')
        hours = int(request.args.get('hours', 24))
        
        if not ts_code:
            return jsonify({
                'success': False,
                'message': '股票代码不能为空'
            }), 400
        
        # 检查数据质量
        result = data_manager.check_data_quality(ts_code, period_type, hours)
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        logger.error(f"数据质量检查API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'检查失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/latest', methods=['GET'])
def get_latest_data():
    """获取最新数据"""
    try:
        ts_code = request.args.get('ts_code')
        period_type = request.args.get('period_type', '1min')
        limit = int(request.args.get('limit', 100))
        
        if not ts_code:
            return jsonify({
                'success': False,
                'message': '股票代码不能为空'
            }), 400
        
        # 获取最新数据
        data = StockMinuteData.get_latest_data(ts_code, period_type, limit)
        
        return jsonify({
            'success': True,
            'data': [item.to_dict() for item in data],
            'count': len(data)
        })
        
    except Exception as e:
        logger.error(f"获取最新数据API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/range', methods=['GET'])
def get_data_by_range():
    """根据时间范围获取数据"""
    try:
        ts_code = request.args.get('ts_code')
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        period_type = request.args.get('period_type', '1min')
        
        if not ts_code or not start_time or not end_time:
            return jsonify({
                'success': False,
                'message': '股票代码、开始时间和结束时间不能为空'
            }), 400
        
        from datetime import datetime
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        # 获取时间范围数据
        data = StockMinuteData.get_data_by_time_range(ts_code, start_dt, end_dt, period_type)
        
        return jsonify({
            'success': True,
            'data': [item.to_dict() for item in data],
            'count': len(data)
        })
        
    except Exception as e:
        logger.error(f"获取时间范围数据API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/price', methods=['GET'])
def get_realtime_price():
    """获取实时价格"""
    try:
        ts_code = request.args.get('ts_code')
        
        if not ts_code:
            return jsonify({
                'success': False,
                'message': '股票代码不能为空'
            }), 400
        
        # 获取实时价格
        result = data_manager.get_realtime_price(ts_code)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取实时价格API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/market-overview', methods=['GET'])
def get_market_overview():
    """获取市场概览"""
    try:
        # 获取市场概览
        result = data_manager.get_market_overview()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"获取市场概览API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/periods', methods=['GET'])
def get_supported_periods():
    """获取支持的周期类型"""
    try:
        periods = StockMinuteData.get_period_types()
        
        return jsonify({
            'success': True,
            'data': periods
        })
        
    except Exception as e:
        logger.error(f"获取周期类型API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/stocks', methods=['GET'])
def get_available_stocks():
    """获取可用的股票列表"""
    try:
        # 获取数据库中有数据的股票代码
        stocks = db.session.query(StockMinuteData.ts_code).distinct().all()
        stock_codes = [stock[0] for stock in stocks]
        
        return jsonify({
            'success': True,
            'data': stock_codes,
            'count': len(stock_codes)
        })
        
    except Exception as e:
        logger.error(f"获取股票列表API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/batch-sync', methods=['POST'])
def batch_sync_data():
    """批量同步数据"""
    try:
        data = request.get_json()
        stock_codes = data.get('stock_codes', [])
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not stock_codes:
            return jsonify({
                'success': False,
                'message': '股票代码列表不能为空'
            }), 400
        
        results = []
        success_count = 0
        
        for ts_code in stock_codes:
            try:
                result = data_manager.sync_minute_data(ts_code, start_date, end_date)
                results.append({
                    'ts_code': ts_code,
                    'result': result
                })
                if result['success']:
                    success_count += 1
            except Exception as e:
                results.append({
                    'ts_code': ts_code,
                    'result': {
                        'success': False,
                        'message': str(e)
                    }
                })
        
        return jsonify({
            'success': True,
            'message': f'批量同步完成，成功 {success_count}/{len(stock_codes)} 只股票',
            'results': results,
            'success_count': success_count,
            'total_count': len(stock_codes)
        })
        
    except Exception as e:
        logger.error(f"批量同步数据API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'批量同步失败: {str(e)}'
        }), 500


@realtime_analysis_bp.route('/data/stats', methods=['GET'])
def get_data_stats():
    """获取数据统计信息"""
    try:
        # 统计各周期数据量
        stats = {}
        periods = StockMinuteData.get_period_types()
        
        for period in periods:
            count = StockMinuteData.query.filter_by(period_type=period).count()
            stats[period] = count
        
        # 获取总股票数
        total_stocks = db.session.query(StockMinuteData.ts_code).distinct().count()
        
        # 获取最新数据时间
        latest_time = db.session.query(
            db.func.max(StockMinuteData.datetime)
        ).scalar()
        
        # 获取最早数据时间
        earliest_time = db.session.query(
            db.func.min(StockMinuteData.datetime)
        ).scalar()
        
        return jsonify({
            'success': True,
            'data': {
                'period_stats': stats,
                'total_stocks': total_stocks,
                'latest_time': latest_time.isoformat() if latest_time else None,
                'earliest_time': earliest_time.isoformat() if earliest_time else None,
                'total_records': sum(stats.values())
            }
        })
        
    except Exception as e:
        logger.error(f"获取数据统计API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取失败: {str(e)}'
        }), 500 