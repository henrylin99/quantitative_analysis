"""
SQL生成引擎
负责根据解析的意图和实体生成相应的SQL查询语句
"""

import re
from typing import Dict, List, Any, Optional
from app.models.text2sql_metadata import QueryTemplate
from app.extensions import db


class SQLGenerator:
    """SQL生成器"""
    
    def __init__(self):
        self.template_manager = TemplateManager()
        self.query_builder = QueryBuilder()
    
    def generate_sql(self, intent_result: Dict[str, Any]) -> Dict[str, Any]:
        """生成SQL查询"""
        try:
            intent = intent_result['intent']['name']
            entities = intent_result['entities']
            
            # 检查是否有多条件查询
            if 'conditions' in entities and len(entities['conditions']) > 1:
                # 处理多条件查询
                sql = self._build_multi_condition_sql(entities)
                template_used = 'multi_condition_dynamic'
            else:
                # 1. 尝试使用模板生成
                template_result = self.template_manager.generate_from_template(intent, entities)
                
                if template_result['success']:
                    sql = template_result['sql']
                    template_used = template_result['template_id']
                else:
                    # 2. 使用动态构建器生成
                    sql = self.query_builder.build_dynamic_sql(intent, entities)
                    template_used = None
            
            # 3. SQL优化和验证
            optimized_sql = self._optimize_sql(sql)
            validation_result = self._validate_sql(optimized_sql)
            
            return {
                'success': validation_result['valid'],
                'sql': optimized_sql,
                'template_used': template_used,
                'error': validation_result.get('error'),
                'explanation': self._generate_explanation(intent, entities)
            }
            
        except Exception as e:
            return {
                'success': False,
                'sql': None,
                'template_used': None,
                'error': str(e),
                'explanation': None
            }
    
    def _optimize_sql(self, sql: str) -> str:
        """优化SQL查询"""
        if not sql:
            return sql
        
        # 移除多余的空格和换行
        sql = re.sub(r'\s+', ' ', sql.strip())
        
        # 确保SQL以分号结尾
        if not sql.endswith(';'):
            sql += ';'
        
        return sql
    
    def _validate_sql(self, sql: str) -> Dict[str, Any]:
        """验证SQL语法"""
        if not sql:
            return {'valid': False, 'error': 'SQL为空'}
        
        # 基本的SQL关键字检查
        required_keywords = ['SELECT', 'FROM']
        sql_upper = sql.upper()
        
        for keyword in required_keywords:
            if keyword not in sql_upper:
                return {'valid': False, 'error': f'缺少必要的SQL关键字: {keyword}'}
        
        # 检查是否有潜在的SQL注入
        dangerous_patterns = [
            r';\s*DROP\s+', r';\s*DELETE\s+', r';\s*UPDATE\s+',
            r';\s*INSERT\s+', r';\s*ALTER\s+', r';\s*CREATE\s+'
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, sql_upper):
                return {'valid': False, 'error': '检测到潜在的危险SQL操作'}
        
        return {'valid': True}
    
    def _generate_explanation(self, intent: str, entities: Dict[str, Any]) -> str:
        """生成查询解释"""
        explanations = {
            'stock_screening': '股票筛选查询',
            'technical_indicator': '技术指标分析查询',
            'fundamental_analysis': '基本面分析查询',
            'money_flow': '资金流向分析查询',
            'factor_analysis': '因子分析查询',
            'ranking': '排名查询'
        }
        
        base_explanation = explanations.get(intent, '数据查询')
        
        # 添加具体的查询条件说明
        conditions = []
        if 'fields' in entities:
            field_names = [field['name'] for field in entities['fields']]
            conditions.append(f"查询字段: {', '.join(field_names)}")
        
        if 'comparison' in entities:
            conditions.append(f"比较条件: {entities['comparison']}")
        
        if 'limit' in entities:
            conditions.append(f"结果限制: 前{entities['limit']}条")
        
        if conditions:
            return f"{base_explanation} - {'; '.join(conditions)}"
        
        return base_explanation
    
    def _build_multi_condition_sql(self, entities: Dict[str, Any]) -> str:
        """构建多条件查询SQL"""
        conditions = entities['conditions']
        
        # 分析需要的表
        tables_needed = set(['stock_business'])  # 主表
        technical_conditions = []
        business_conditions = []
        
        for condition in conditions:
            field_info = condition.get('field', {})
            field_category = field_info.get('category', '')
            
            if field_category == 'technical_fields' or 'MACD' in field_info.get('name', ''):
                tables_needed.add('stock_factor')
                technical_conditions.append(condition)
            else:
                business_conditions.append(condition)
        
        # 构建SELECT子句
        select_fields = ['sb.ts_code', 'sb.stock_name']
        
        # 添加查询条件中涉及的字段
        for condition in conditions:
            field_info = condition.get('field', {})
            db_field = field_info.get('db_field', field_info.get('name', ''))
            
            if field_info.get('category') == 'technical_fields':
                if 'MACD' in field_info.get('name', ''):
                    select_fields.extend(['sf.macd_dif', 'sf.macd_dea', 'sf.macd'])
                else:
                    select_fields.append(f'sf.{db_field}')
            else:
                if db_field not in ['ts_code', 'stock_name']:
                    select_fields.append(f'sb.{db_field}')
        
        # 去重
        select_fields = list(dict.fromkeys(select_fields))
        
        # 构建FROM子句
        from_clause = "FROM stock_business sb"
        if 'stock_factor' in tables_needed:
            from_clause += "\nJOIN stock_factor sf ON sb.ts_code = sf.ts_code"
        
        # 构建WHERE子句
        where_conditions = []
        
        # 处理业务条件
        for condition in business_conditions:
            condition_sql = self._build_single_condition_sql(condition, 'sb')
            if condition_sql:
                where_conditions.append(condition_sql)
        
        # 处理技术指标条件
        for condition in technical_conditions:
            condition_sql = self._build_technical_condition_sql(condition)
            if condition_sql:
                where_conditions.append(condition_sql)
        
        # 确保取最新数据
        if 'stock_factor' in tables_needed:
            where_conditions.append("""sf.trade_date = (
                SELECT MAX(trade_date) FROM stock_factor WHERE ts_code = sb.ts_code
            )""")
        
        # 基本过滤条件
        where_conditions.append("sb.ts_code IS NOT NULL")
        
        # 组装SQL
        sql_parts = [
            f"SELECT {', '.join(select_fields)}",
            from_clause,
            f"WHERE {' AND '.join(where_conditions)}"
        ]
        
        # 添加排序和限制
        limit = entities.get('limit', 20)
        
        # 根据查询类型确定排序
        if technical_conditions:
            # 如果有技术指标条件，按技术指标排序
            for condition in technical_conditions:
                if 'MACD' in condition.get('field', {}).get('name', ''):
                    sql_parts.append("ORDER BY sf.macd DESC")
                    break
        else:
            # 否则按第一个数值字段排序
            for condition in business_conditions:
                field_info = condition.get('field', {})
                db_field = field_info.get('db_field', '')
                if db_field and condition.get('comparison') in ['greater_than', 'less_than']:
                    order = 'DESC' if condition.get('comparison') == 'greater_than' else 'ASC'
                    sql_parts.append(f"ORDER BY sb.{db_field} {order}")
                    break
        
        sql_parts.append(f"LIMIT {limit}")
        
        return '\n'.join(sql_parts)
    
    def _build_single_condition_sql(self, condition: Dict[str, Any], table_alias: str = '') -> Optional[str]:
        """构建单个条件的SQL"""
        if 'field' not in condition or 'comparison' not in condition or 'value' not in condition:
            return None
        
        field_info = condition['field']
        comparison = condition['comparison']
        value = condition['value']
        
        # 获取数据库字段名
        db_field = field_info.get('db_field', field_info['name'])
        
        # 添加表别名
        if table_alias:
            field_ref = f"{table_alias}.{db_field}"
        else:
            field_ref = db_field
        
        # 构建比较条件
        if comparison == 'greater_than':
            return f"{field_ref} > {value}"
        elif comparison == 'less_than':
            return f"{field_ref} < {value}"
        elif comparison == 'equal':
            return f"{field_ref} = {value}"
        elif comparison == 'between':
            return f"{field_ref} >= {value}"
        
        return None
    
    def _build_technical_condition_sql(self, condition: Dict[str, Any]) -> Optional[str]:
        """构建技术指标条件的SQL"""
        field_info = condition.get('field', {})
        field_name = field_info.get('name', '')
        comparison = condition.get('comparison', '')
        value = condition.get('value')
        
        if 'MACD' in field_name:
            if comparison == 'golden_cross' or value == 'golden_cross':
                # MACD金叉条件：DIF > DEA
                return "sf.macd_dif > sf.macd_dea"
            elif comparison == 'death_cross' or value == 'death_cross':
                # MACD死叉条件：DIF < DEA
                return "sf.macd_dif < sf.macd_dea"
            else:
                # 其他MACD数值条件
                if comparison == 'greater_than' and value is not None:
                    return f"sf.macd > {value}"
                elif comparison == 'less_than' and value is not None:
                    return f"sf.macd < {value}"
        
        elif 'RSI' in field_name:
            # RSI条件
            if comparison and value is not None:
                if comparison == 'greater_than':
                    return f"sf.rsi_6 > {value}"
                elif comparison == 'less_than':
                    return f"sf.rsi_6 < {value}"
        
        elif 'KDJ' in field_name:
            # KDJ条件
            if comparison == 'golden_cross':
                return "sf.kdj_k > sf.kdj_d"
            elif comparison == 'death_cross':
                return "sf.kdj_k < sf.kdj_d"
        
        return None


class TemplateManager:
    """模板管理器"""
    
    def __init__(self):
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Dict[str, Any]]:
        """加载查询模板"""
        try:
            # 从数据库加载模板
            db_templates = QueryTemplate.query.filter_by(is_active=True).all()
            templates = {}
            
            for template in db_templates:
                templates[template.template_id] = {
                    'name': template.template_name,
                    'pattern': template.intent_pattern,
                    'sql': template.sql_template,
                    'parameters': template.parameters or {},
                    'usage_count': template.usage_count
                }
            
            return templates
            
        except Exception:
            # 如果数据库还没有初始化，使用默认模板
            return self._get_default_templates()
    
    def _get_default_templates(self) -> Dict[str, Dict[str, Any]]:
        """获取默认模板"""
        return {
            'stock_screening_by_price': {
                'name': '按价格筛选股票',
                'pattern': r'收盘价.*大于.*的股票',
                'sql': '''
                    SELECT ts_code, stock_name, daily_close, factor_pct_change, vol
                    FROM stock_business 
                    WHERE daily_close > {price_threshold}
                    ORDER BY daily_close DESC
                    LIMIT {limit}
                ''',
                'parameters': ['price_threshold', 'limit']
            },
            
            'stock_screening_by_pct_change': {
                'name': '按涨跌幅筛选股票',
                'pattern': r'涨幅.*大于.*的股票',
                'sql': '''
                    SELECT ts_code, stock_name, daily_close, factor_pct_change, vol
                    FROM stock_business 
                    WHERE factor_pct_change > {pct_threshold}
                    ORDER BY factor_pct_change DESC
                    LIMIT {limit}
                ''',
                'parameters': ['pct_threshold', 'limit']
            },
            
            'stock_screening_by_volume': {
                'name': '按成交量筛选股票',
                'pattern': r'成交量.*大于.*的股票',
                'sql': '''
                    SELECT ts_code, stock_name, daily_close, factor_pct_change, vol
                    FROM stock_business 
                    WHERE vol > {volume_threshold}
                    ORDER BY vol DESC
                    LIMIT {limit}
                ''',
                'parameters': ['volume_threshold', 'limit']
            },
            
            'technical_indicator_macd': {
                'name': 'MACD技术指标查询',
                'pattern': r'MACD.*金叉.*股票',
                'sql': '''
                    SELECT sb.ts_code, sb.stock_name, sf.macd_dif, sf.macd_dea, sf.macd
                    FROM stock_business sb
                    JOIN stock_factor sf ON sb.ts_code = sf.ts_code
                    WHERE sf.macd_dif > sf.macd_dea 
                    AND sf.trade_date = (
                        SELECT MAX(trade_date) FROM stock_factor WHERE ts_code = sb.ts_code
                    )
                    ORDER BY sf.macd DESC
                    LIMIT {limit}
                ''',
                'parameters': ['limit']
            },
            
            'fundamental_analysis_pe': {
                'name': '市盈率基本面分析',
                'pattern': r'市盈率.*小于.*的股票',
                'sql': '''
                    SELECT ts_code, stock_name, daily_close, pe_ttm, pb
                    FROM stock_business 
                    WHERE pe_ttm > 0 AND pe_ttm < {pe_threshold}
                    ORDER BY pe_ttm ASC
                    LIMIT {limit}
                ''',
                'parameters': ['pe_threshold', 'limit']
            },
            
            'money_flow_analysis': {
                'name': '资金流向分析',
                'pattern': r'资金.*净流入.*股票',
                'sql': '''
                    SELECT sb.ts_code, sb.stock_name, sm.net_mf_amount, sm.net_mf_vol
                    FROM stock_business sb
                    JOIN stock_moneyflow sm ON sb.ts_code = sm.ts_code
                    WHERE sm.net_mf_amount > 0
                    ORDER BY sm.net_mf_amount DESC
                    LIMIT {limit}
                ''',
                'parameters': ['limit']
            }
        }
    
    def generate_from_template(self, intent: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """从模板生成SQL"""
        # 查找匹配的模板
        matched_template = self._find_matching_template(intent, entities)
        
        if not matched_template:
            return {'success': False, 'sql': None, 'template_id': None}
        
        template_id, template = matched_template
        
        try:
            # 提取参数
            parameters = self._extract_parameters(template, entities)
            
            # 替换模板中的参数
            sql = template['sql']
            for param, value in parameters.items():
                sql = sql.replace(f'{{{param}}}', str(value))
            
            # 更新模板使用次数
            self._update_template_usage(template_id)
            
            return {
                'success': True,
                'sql': sql,
                'template_id': template_id,
                'parameters': parameters
            }
            
        except Exception as e:
            return {
                'success': False,
                'sql': None,
                'template_id': template_id,
                'error': str(e)
            }
    
    def _find_matching_template(self, intent: str, entities: Dict[str, Any]) -> Optional[tuple]:
        """查找匹配的模板"""
        for template_id, template in self.templates.items():
            # 检查意图匹配
            if intent in template_id:
                # 检查实体匹配
                if self._check_entity_match(template, entities):
                    return template_id, template
        
        return None
    
    def _check_entity_match(self, template: Dict[str, Any], entities: Dict[str, Any]) -> bool:
        """检查实体是否匹配模板"""
        # 简单的匹配逻辑，可以根据需要扩展
        if 'price' in template['name'] and 'price' in entities:
            return True
        if 'pct_change' in template['name'] and 'percentage' in entities:
            return True
        if 'volume' in template['name'] and 'volume_fields' in str(entities):
            return True
        if 'MACD' in template['name'] and any('MACD' in str(field) for field in entities.get('fields', [])):
            return True
        if 'PE' in template['name'] and any('市盈率' in str(field) for field in entities.get('fields', [])):
            return True
        if 'money_flow' in template['name'] and any('资金' in str(field) for field in entities.get('fields', [])):
            return True
        
        return False
    
    def _extract_parameters(self, template: Dict[str, Any], entities: Dict[str, Any]) -> Dict[str, Any]:
        """提取模板参数"""
        parameters = {}
        
        # 设置默认限制
        parameters['limit'] = entities.get('limit', 20)
        
        # 提取数值参数
        if 'price' in entities:
            parameters['price_threshold'] = entities['price'][0]
        
        if 'percentage' in entities:
            parameters['pct_threshold'] = entities['percentage'][0]
        
        if 'count' in entities:
            parameters['volume_threshold'] = entities['count'][0] * 10000  # 假设单位是万
        
        if 'ratio' in entities:
            parameters['pe_threshold'] = entities['ratio'][0]
        
        return parameters
    
    def _update_template_usage(self, template_id: str):
        """更新模板使用次数"""
        try:
            template = QueryTemplate.query.get(template_id)
            if template:
                template.increment_usage()
        except Exception:
            # 如果是默认模板，忽略更新
            pass


class QueryBuilder:
    """动态查询构建器"""
    
    def __init__(self):
        self.table_mappings = {
            'stock_screening': 'stock_business',
            'technical_indicator': 'stock_factor',
            'fundamental_analysis': 'stock_business',
            'money_flow': 'stock_moneyflow',
            'factor_analysis': 'factor_values',
            'ranking': 'stock_business'
        }
        
        self.field_mappings = {
            '收盘价': {'table': 'stock_business', 'field': 'daily_close'},
            '涨跌幅': {'table': 'stock_business', 'field': 'factor_pct_change'},
            '成交量': {'table': 'stock_business', 'field': 'factor_vol'},
            '成交额': {'table': 'stock_business', 'field': 'amount'},
            '市盈率': {'table': 'stock_business', 'field': 'pe_ttm'},
            '市净率': {'table': 'stock_business', 'field': 'pb'},
            'MACD': {'table': 'stock_factor', 'field': 'macd'},
            'RSI': {'table': 'stock_factor', 'field': 'rsi_6'},
            '均线': {'table': 'stock_ma_data', 'field': 'ma5'},
            '资金流': {'table': 'stock_moneyflow', 'field': 'net_mf_amount'}
        }
    
    def build_dynamic_sql(self, intent: str, entities: Dict[str, Any]) -> str:
        """动态构建SQL"""
        try:
            # 1. 确定主表
            main_table = self._determine_main_table(intent, entities)
            
            # 2. 构建SELECT子句
            select_clause = self._build_select_clause(entities, main_table)
            
            # 3. 构建FROM子句（包含JOIN）
            from_clause = self._build_from_clause(main_table, entities)
            
            # 4. 构建WHERE子句 - 支持新的条件结构
            where_clause = self._build_where_clause_v2(entities)
            
            # 5. 构建ORDER BY子句
            order_clause = self._build_order_clause(entities)
            
            # 6. 构建LIMIT子句
            limit_clause = self._build_limit_clause(entities)
            
            # 7. 组装SQL
            sql_parts = [select_clause, from_clause]
            
            if where_clause:
                sql_parts.append(where_clause)
            
            if order_clause:
                sql_parts.append(order_clause)
            
            if limit_clause:
                sql_parts.append(limit_clause)
            
            sql = '\n'.join(sql_parts)
            
            return sql.strip()
            
        except Exception as e:
            # 返回一个基本的查询作为fallback
            return f"SELECT ts_code, stock_name, daily_close FROM stock_business LIMIT 20;"
    
    def _determine_main_table(self, intent: str, entities: Dict[str, Any]) -> str:
        """确定主表"""
        # 根据字段确定主表
        if 'fields' in entities:
            for field in entities['fields']:
                field_name = field['name']
                if field_name in self.field_mappings:
                    return self.field_mappings[field_name]['table']
        
        # 根据意图确定主表
        return self.table_mappings.get(intent, 'stock_business')
    
    def _build_select_clause(self, entities: Dict[str, Any], main_table: str) -> str:
        """构建SELECT子句"""
        select_fields = []
        
        # 基础字段
        if main_table == 'stock_business':
            select_fields.extend(['ts_code', 'stock_name'])
        elif main_table == 'stock_factor':
            select_fields.extend(['ts_code', 'trade_date'])
        elif main_table == 'stock_moneyflow':
            select_fields.extend(['ts_code', 'trade_date'])
        
        # 根据新的条件结构添加字段
        if 'conditions' in entities:
            for condition in entities['conditions']:
                if 'field' in condition:
                    field_info = condition['field']
                    db_field = field_info.get('db_field', field_info['name'])
                    if db_field not in select_fields:
                        select_fields.append(db_field)
        
        # 兼容旧的实体结构
        if 'fields' in entities:
            for field in entities['fields']:
                field_name = field['name']
                if field_name in self.field_mappings:
                    mapping = self.field_mappings[field_name]
                    if mapping['table'] == main_table:
                        if mapping['field'] not in select_fields:
                            select_fields.append(mapping['field'])
        
        # 如果没有特定字段，添加常用字段
        if len(select_fields) <= 2:  # 只有基础字段
            if main_table == 'stock_business':
                select_fields.extend(['daily_close', 'factor_pct_change'])
        
        # 去重并格式化
        select_fields = list(dict.fromkeys(select_fields))  # 去重保持顺序
        
        return f"SELECT {', '.join(select_fields)}"
    
    def _build_from_clause(self, main_table: str, entities: Dict[str, Any]) -> str:
        """构建FROM子句"""
        from_clause = f"FROM {main_table}"
        
        # 检查是否需要JOIN其他表
        join_tables = set()
        
        if 'fields' in entities:
            for field in entities['fields']:
                field_name = field['name']
                if field_name in self.field_mappings:
                    mapping = self.field_mappings[field_name]
                    if mapping['table'] != main_table:
                        join_tables.add(mapping['table'])
        
        # 添加JOIN子句
        for join_table in join_tables:
            if join_table == 'stock_factor' and main_table == 'stock_business':
                from_clause += f"\nJOIN {join_table} sf ON {main_table}.ts_code = sf.ts_code"
            elif join_table == 'stock_moneyflow' and main_table == 'stock_business':
                from_clause += f"\nJOIN {join_table} sm ON {main_table}.ts_code = sm.ts_code"
            elif join_table == 'stock_ma_data' and main_table == 'stock_business':
                from_clause += f"\nJOIN {join_table} sma ON {main_table}.ts_code = sma.ts_code"
        
        return from_clause
    
    def _build_where_clause_v2(self, entities: Dict[str, Any]) -> str:
        """构建WHERE子句 - 支持新的条件结构"""
        conditions = []
        
        # 处理新的条件结构
        if 'conditions' in entities:
            for condition in entities['conditions']:
                condition_sql = self._build_single_condition(condition)
                if condition_sql:
                    conditions.append(condition_sql)
        else:
            # 兼容旧的条件结构
            old_conditions = self._build_where_clause_old(entities)
            if old_conditions:
                return old_conditions
        
        # 添加基本过滤条件
        conditions.append("ts_code IS NOT NULL")
        
        if conditions:
            return f"WHERE {' AND '.join(conditions)}"
        
        return ""
    
    def _build_single_condition(self, condition: Dict[str, Any]) -> Optional[str]:
        """构建单个条件的SQL"""
        if 'field' not in condition or 'comparison' not in condition or 'value' not in condition:
            return None
        
        field_info = condition['field']
        comparison = condition['comparison']
        value = condition['value']
        
        # 获取数据库字段名
        db_field = field_info.get('db_field', field_info['name'])
        
        # 构建比较条件
        if comparison == 'greater_than':
            return f"{db_field} > {value}"
        elif comparison == 'less_than':
            return f"{db_field} < {value}"
        elif comparison == 'equal':
            return f"{db_field} = {value}"
        elif comparison == 'between':
            # 这里需要处理范围条件，暂时简化
            return f"{db_field} >= {value}"
        
        return None
    
    def _build_where_clause_old(self, entities: Dict[str, Any]) -> str:
        """构建WHERE子句 - 兼容旧的条件结构"""
        conditions = []
        
        # 处理比较条件
        if 'comparison' in entities and 'fields' in entities:
            comparison = entities['comparison']
            
            # 处理数值条件
            for field in entities['fields']:
                field_name = field['name']
                if field_name in self.field_mappings:
                    mapping = self.field_mappings[field_name]
                    field_ref = mapping['field']
                    
                    # 根据字段类型和比较操作符构建条件
                    if comparison == 'greater_than':
                        if 'price' in entities:
                            conditions.append(f"{field_ref} > {entities['price'][0]}")
                        elif 'percentage' in entities:
                            conditions.append(f"{field_ref} > {entities['percentage'][0]}")
                        elif 'count' in entities:
                            conditions.append(f"{field_ref} > {entities['count'][0]}")
                    
                    elif comparison == 'less_than':
                        if 'price' in entities:
                            conditions.append(f"{field_ref} < {entities['price'][0]}")
                        elif 'percentage' in entities:
                            conditions.append(f"{field_ref} < {entities['percentage'][0]}")
                        elif 'ratio' in entities:
                            conditions.append(f"{field_ref} < {entities['ratio'][0]}")
        
        # 添加基本过滤条件
        conditions.append("ts_code IS NOT NULL")
        
        if conditions:
            return f"WHERE {' AND '.join(conditions)}"
        
        return ""
    
    def _build_order_clause(self, entities: Dict[str, Any]) -> str:
        """构建ORDER BY子句"""
        if 'sort' in entities:
            order = entities.get('order', 'desc').upper()
            
            # 确定排序字段
            if 'fields' in entities:
                field = entities['fields'][0]  # 使用第一个字段排序
                field_name = field['name']
                if field_name in self.field_mappings:
                    mapping = self.field_mappings[field_name]
                    return f"ORDER BY {mapping['field']} {order}"
            
            # 默认排序
            return "ORDER BY daily_close DESC"
        
        return ""
    
    def _build_limit_clause(self, entities: Dict[str, Any]) -> str:
        """构建LIMIT子句"""
        limit = entities.get('limit', 20)
        return f"LIMIT {limit}" 