"""
Text2SQL API接口
提供自然语言查询的REST API服务
"""

import logging
from flask import Blueprint, request, jsonify, render_template
from app.services.text2sql_engine import get_text2sql_engine
from app.models.text2sql_metadata import QueryHistory, QueryTemplate, BusinessDictionary
from app.extensions import db

# 创建蓝图
text2sql_bp = Blueprint('text2sql', __name__, url_prefix='/api/text2sql')

# 配置日志
logger = logging.getLogger(__name__)


@text2sql_bp.route('/', methods=['GET'])
def text2sql_page():
    """Text2SQL页面"""
    return render_template('text2sql/index.html')


@text2sql_bp.route('/query', methods=['POST'])
def process_query():
    """处理自然语言查询"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': '请求数据为空'}), 400
        
        user_query = data.get('query', '').strip()
        
        if not user_query:
            return jsonify({'error': '查询内容不能为空'}), 400
        
        if len(user_query) > 500:
            return jsonify({'error': '查询内容过长，请控制在500字符以内'}), 400
        
        # 处理查询
        engine = get_text2sql_engine()
        result = engine.process_query(user_query)
        
        if result['success']:
            return jsonify({
                'success': True,
                'query': result['query'],
                'intent': result['intent'],
                'entities': result['entities'],
                'sql': result['sql'],
                'data': result['data'],
                'formatted_data': result['formatted_data'],
                'chart_config': result.get('chart_config'),
                'explanation': result.get('explanation'),
                'execution_time': result['execution_time'],
                'result_count': result['result_count']
            })
        else:
            return jsonify({
                'success': False,
                'query': result['query'],
                'error': result['error'],
                'intent': result.get('intent'),
                'entities': result.get('entities'),
                'sql': result.get('sql'),
                'execution_time': result['execution_time']
            }), 400
        
    except Exception as e:
        logger.error(f"处理查询失败: {e}")
        return jsonify({'error': f'服务器内部错误: {str(e)}'}), 500


@text2sql_bp.route('/suggestions', methods=['GET'])
def get_query_suggestions():
    """获取查询建议"""
    try:
        engine = get_text2sql_engine()
        suggestions = engine.get_query_suggestions()
        
        return jsonify({
            'success': True,
            'suggestions': suggestions
        })
        
    except Exception as e:
        logger.error(f"获取查询建议失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/history', methods=['GET'])
def get_query_history():
    """获取查询历史"""
    try:
        limit = request.args.get('limit', 10, type=int)
        limit = min(limit, 100)  # 最大限制100条
        
        engine = get_text2sql_engine()
        history = engine.get_query_history(limit)
        
        return jsonify({
            'success': True,
            'history': history,
            'count': len(history)
        })
        
    except Exception as e:
        logger.error(f"获取查询历史失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/templates', methods=['GET'])
def get_query_templates():
    """获取查询模板"""
    try:
        templates = QueryTemplate.query.filter_by(is_active=True).all()
        
        template_list = []
        for template in templates:
            template_dict = template.to_dict()
            template_list.append({
                'id': template_dict['template_id'],
                'name': template_dict['template_name'],
                'pattern': template_dict['intent_pattern'],
                'usage_count': template_dict['usage_count'],
                'description': template_dict.get('description', '')
            })
        
        return jsonify({
            'success': True,
            'templates': template_list,
            'count': len(template_list)
        })
        
    except Exception as e:
        logger.error(f"获取查询模板失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/templates', methods=['POST'])
def create_query_template():
    """创建查询模板"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': '请求数据为空'}), 400
        
        required_fields = ['template_id', 'template_name', 'sql_template']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'缺少必要字段: {field}'}), 400
        
        # 检查模板ID是否已存在
        existing_template = QueryTemplate.query.get(data['template_id'])
        if existing_template:
            return jsonify({'error': '模板ID已存在'}), 400
        
        # 创建新模板
        template = QueryTemplate(
            template_id=data['template_id'],
            template_name=data['template_name'],
            intent_pattern=data.get('intent_pattern'),
            sql_template=data['sql_template'],
            parameters=data.get('parameters', {}),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(template)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '模板创建成功',
            'template': template.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建查询模板失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/templates/<template_id>', methods=['PUT'])
def update_query_template(template_id):
    """更新查询模板"""
    try:
        template = QueryTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': '模板不存在'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求数据为空'}), 400
        
        # 更新模板字段
        if 'template_name' in data:
            template.template_name = data['template_name']
        if 'intent_pattern' in data:
            template.intent_pattern = data['intent_pattern']
        if 'sql_template' in data:
            template.sql_template = data['sql_template']
        if 'parameters' in data:
            template.parameters = data['parameters']
        if 'is_active' in data:
            template.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '模板更新成功',
            'template': template.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新查询模板失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/templates/<template_id>', methods=['DELETE'])
def delete_query_template(template_id):
    """删除查询模板"""
    try:
        template = QueryTemplate.query.get(template_id)
        if not template:
            return jsonify({'error': '模板不存在'}), 404
        
        # 软删除：设置为非激活状态
        template.is_active = False
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '模板删除成功'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除查询模板失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/dictionary', methods=['GET'])
def get_business_dictionary():
    """获取业务词典"""
    try:
        category = request.args.get('category')
        
        query = BusinessDictionary.query.filter_by(is_active=True)
        if category:
            query = query.filter_by(category=category)
        
        dictionaries = query.all()
        
        dict_list = []
        for dictionary in dictionaries:
            dict_list.append(dictionary.to_dict())
        
        return jsonify({
            'success': True,
            'dictionaries': dict_list,
            'count': len(dict_list)
        })
        
    except Exception as e:
        logger.error(f"获取业务词典失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/dictionary', methods=['POST'])
def create_business_dictionary():
    """创建业务词典条目"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': '请求数据为空'}), 400
        
        required_fields = ['category', 'standard_term']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'缺少必要字段: {field}'}), 400
        
        # 创建新词典条目
        dictionary = BusinessDictionary(
            category=data['category'],
            standard_term=data['standard_term'],
            synonyms=data.get('synonyms', []),
            description=data.get('description'),
            mapping_field=data.get('mapping_field'),
            mapping_table=data.get('mapping_table'),
            is_active=data.get('is_active', True)
        )
        
        db.session.add(dictionary)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '词典条目创建成功',
            'dictionary': dictionary.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建业务词典失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/statistics', methods=['GET'])
def get_query_statistics():
    """获取查询统计信息"""
    try:
        # 总查询次数
        total_queries = QueryHistory.query.count()
        
        # 成功查询次数
        successful_queries = QueryHistory.query.filter_by(is_successful=True).count()
        
        # 成功率
        success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
        
        # 平均执行时间
        avg_execution_time = db.session.query(
            db.func.avg(QueryHistory.execution_time)
        ).filter_by(is_successful=True).scalar() or 0
        
        # 最常用的意图
        intent_stats = db.session.query(
            QueryHistory.intent,
            db.func.count(QueryHistory.intent).label('count')
        ).filter(
            QueryHistory.intent.isnot(None)
        ).group_by(QueryHistory.intent).order_by(
            db.func.count(QueryHistory.intent).desc()
        ).limit(5).all()
        
        # 最常用的模板
        template_stats = db.session.query(
            QueryHistory.template_used,
            db.func.count(QueryHistory.template_used).label('count')
        ).filter(
            QueryHistory.template_used.isnot(None)
        ).group_by(QueryHistory.template_used).order_by(
            db.func.count(QueryHistory.template_used).desc()
        ).limit(5).all()
        
        return jsonify({
            'success': True,
            'statistics': {
                'total_queries': total_queries,
                'successful_queries': successful_queries,
                'success_rate': round(success_rate, 2),
                'avg_execution_time': round(float(avg_execution_time), 3),
                'top_intents': [{'intent': intent, 'count': count} for intent, count in intent_stats],
                'top_templates': [{'template': template, 'count': count} for template, count in template_stats]
            }
        })
        
    except Exception as e:
        logger.error(f"获取查询统计失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/validate', methods=['POST'])
def validate_query():
    """验证查询语句"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': '请求数据为空'}), 400
        
        user_query = data.get('query', '').strip()
        
        if not user_query:
            return jsonify({'error': '查询内容不能为空'}), 400
        
        # 只进行NLP解析和SQL生成，不执行查询
        engine = get_text2sql_engine()
        
        # 1. 自然语言理解
        intent_result = engine.nlp_processor.parse_intent(user_query)
        
        # 2. SQL生成
        sql_result = engine.sql_generator.generate_sql(intent_result)
        
        return jsonify({
            'success': True,
            'query': user_query,
            'intent': intent_result['intent'],
            'entities': intent_result['entities'],
            'sql_valid': sql_result['success'],
            'sql': sql_result.get('sql'),
            'sql_error': sql_result.get('error'),
            'explanation': sql_result.get('explanation')
        })
        
    except Exception as e:
        logger.error(f"验证查询失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/export', methods=['POST'])
def export_query_result():
    """导出查询结果"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': '请求数据为空'}), 400
        
        query_data = data.get('data', [])
        export_format = data.get('format', 'csv').lower()
        
        if not query_data:
            return jsonify({'error': '没有数据可导出'}), 400
        
        if export_format not in ['csv', 'excel', 'json']:
            return jsonify({'error': '不支持的导出格式'}), 400
        
        # 这里可以实现具体的导出逻辑
        # 为了简化，现在只返回成功消息
        return jsonify({
            'success': True,
            'message': f'数据已准备导出为{export_format.upper()}格式',
            'record_count': len(query_data)
        })
        
    except Exception as e:
        logger.error(f"导出查询结果失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/llm/status', methods=['GET'])
def get_llm_status():
    """获取大模型服务状态"""
    try:
        from app.services.llm_service import get_llm_service
        
        llm_service = get_llm_service()
        status = llm_service.check_service_status()
        
        return jsonify({
            'success': True,
            'status': status
        })
        
    except Exception as e:
        logger.error(f"获取大模型状态失败: {e}")
        return jsonify({'error': str(e)}), 500


@text2sql_bp.route('/llm/test', methods=['POST'])
def test_llm_service():
    """测试大模型服务"""
    try:
        from app.services.llm_service import get_llm_service
        
        data = request.get_json()
        test_query = data.get('query', '找出收盘价大于100元的股票')
        
        llm_service = get_llm_service()
        
        # 构建测试上下文
        context = {
            'intent': {'name': 'stock_screening'},
            'entities': {'price': [100], 'comparison': 'greater_than'},
            'tables_info': {}
        }
        
        # 测试SQL生成
        result_sql = llm_service.enhance_sql_generation(test_query, context)
        
        if result_sql:
            return jsonify({
                'success': True,
                'test_query': test_query,
                'generated_sql': result_sql,
                'message': '大模型服务测试成功'
            })
        else:
            return jsonify({
                'success': False,
                'test_query': test_query,
                'message': '大模型服务测试失败'
            }), 400
        
    except Exception as e:
        logger.error(f"测试大模型服务失败: {e}")
        return jsonify({'error': str(e)}), 500


# 错误处理
@text2sql_bp.errorhandler(404)
def not_found(error):
    return jsonify({'error': '接口不存在'}), 404


@text2sql_bp.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': '请求方法不允许'}), 405


@text2sql_bp.errorhandler(500)
def internal_error(error):
    return jsonify({'error': '服务器内部错误'}), 500 