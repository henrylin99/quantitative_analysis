"""
自然语言处理器
负责解析用户的自然语言查询，识别意图和提取实体
"""

import re
import jieba
import jieba.posseg as pseg
from typing import Dict, List, Any, Optional
from app.models.text2sql_metadata import BusinessDictionary
from app.extensions import db


class NLPProcessor:
    """自然语言处理器"""
    
    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.entity_extractor = EntityExtractor()
        self.business_dict = BusinessDictionaryManager()
        
        # 初始化jieba分词
        self._init_jieba()
    
    def _init_jieba(self):
        """初始化jieba分词器"""
        # 添加股票相关词汇
        stock_terms = [
            '股票', '涨幅', '跌幅', '收盘价', '开盘价', '最高价', '最低价',
            '成交量', '成交额', '换手率', '市盈率', '市净率', '总市值',
            'MACD', 'KDJ', 'RSI', '布林带', '均线', '金叉', '死叉',
            '主力', '资金流', '净流入', '净流出', '大单', '中单', '小单',
            'ROE', 'ROA', '营收', '利润', '负债率', '现金流'
        ]
        
        for term in stock_terms:
            jieba.add_word(term)
    
    def parse_intent(self, user_query: str) -> Dict[str, Any]:
        """解析用户意图"""
        try:
            # 1. 预处理
            cleaned_query = self._preprocess(user_query)
            
            # 2. 意图分类
            intent = self.intent_classifier.classify(cleaned_query)
            
            # 3. 实体抽取
            entities = self.entity_extractor.extract(cleaned_query)
            
            # 4. 业务术语标准化
            normalized_entities = self.business_dict.normalize(entities)
            
            return {
                'original_query': user_query,
                'cleaned_query': cleaned_query,
                'intent': intent,
                'entities': normalized_entities,
                'confidence': intent.get('confidence', 0.0)
            }
            
        except Exception as e:
            return {
                'original_query': user_query,
                'cleaned_query': user_query,
                'intent': {'name': 'unknown', 'confidence': 0.0},
                'entities': {},
                'confidence': 0.0,
                'error': str(e)
            }
    
    def _preprocess(self, query: str) -> str:
        """预处理查询文本"""
        # 去除多余空格
        query = re.sub(r'\s+', ' ', query.strip())
        
        # 统一标点符号
        query = query.replace('，', ',').replace('。', '.').replace('？', '?')
        
        # 统一数字格式
        query = re.sub(r'(\d+)%', r'\1百分比', query)
        query = re.sub(r'(\d+)元', r'\1', query)
        
        return query


class IntentClassifier:
    """意图分类器"""
    
    def __init__(self):
        self.intent_patterns = {
            'stock_screening': {
                'patterns': [
                    r'筛选.*股票', r'找.*股票', r'哪些股票', r'股票.*条件',
                    r'涨幅.*股票', r'跌幅.*股票', r'成交量.*股票', r'.*的股票',
                    r'收盘价.*大于', r'收盘价.*小于', r'价格.*范围'
                ],
                'keywords': ['筛选', '找', '哪些', '股票', '条件', '范围']
            },
            'factor_analysis': {
                'patterns': [
                    r'因子.*分析', r'.*因子.*排名', r'因子.*分布',
                    r'技术指标.*分析', r'基本面.*分析', r'.*因子.*表现'
                ],
                'keywords': ['因子', '分析', '排名', '分布', '表现']
            },
            'technical_indicator': {
                'patterns': [
                    r'MACD.*', r'KDJ.*', r'RSI.*', r'布林带.*',
                    r'均线.*', r'金叉.*', r'死叉.*', r'技术指标.*'
                ],
                'keywords': ['MACD', 'KDJ', 'RSI', '布林带', '均线', '金叉', '死叉', '技术指标']
            },
            'fundamental_analysis': {
                'patterns': [
                    r'PE.*', r'PB.*', r'ROE.*', r'营收.*', r'利润.*',
                    r'市盈率.*', r'市净率.*', r'财务.*', r'基本面.*'
                ],
                'keywords': ['PE', 'PB', 'ROE', '营收', '利润', '市盈率', '市净率', '财务', '基本面']
            },
            'money_flow': {
                'patterns': [
                    r'资金流.*', r'大单.*', r'主力.*', r'机构.*',
                    r'净流入.*', r'净流出.*', r'资金.*'
                ],
                'keywords': ['资金流', '大单', '主力', '机构', '净流入', '净流出', '资金']
            },
            'ranking': {
                'patterns': [
                    r'排名.*', r'排序.*', r'前.*名', r'最.*的',
                    r'top.*', r'最高.*', r'最低.*', r'最大.*', r'最小.*'
                ],
                'keywords': ['排名', '排序', '前', '最', 'top', '最高', '最低', '最大', '最小']
            }
        }
    
    def classify(self, query: str) -> Dict[str, Any]:
        """分类用户意图"""
        scores = {}
        
        for intent_name, intent_config in self.intent_patterns.items():
            score = 0
            
            # 模式匹配得分
            for pattern in intent_config['patterns']:
                if re.search(pattern, query, re.IGNORECASE):
                    score += 2
            
            # 关键词匹配得分
            for keyword in intent_config['keywords']:
                if keyword in query:
                    score += 1
            
            scores[intent_name] = score
        
        # 找到最高得分的意图
        if scores:
            best_intent = max(scores, key=scores.get)
            max_score = scores[best_intent]
            
            if max_score > 0:
                confidence = min(max_score / 5.0, 1.0)  # 归一化到0-1
                return {
                    'name': best_intent,
                    'confidence': confidence,
                    'scores': scores
                }
        
        # 默认意图
        return {
            'name': 'stock_screening',
            'confidence': 0.3,
            'scores': scores
        }


class EntityExtractor:
    """实体抽取器"""
    
    def __init__(self):
        # 数值模式
        self.number_patterns = {
            'price': r'(\d+(?:\.\d+)?)(?:元|块)',
            'percentage': r'(\d+(?:\.\d+)?)%',
            'ratio': r'(\d+(?:\.\d+)?)(?:倍|比)',
            'count': r'(\d+(?:\.\d+)?)(?:万|千|个|只|支)?'
        }
        
        # 比较操作符模式
        self.comparison_patterns = {
            'greater_than': r'大于|超过|高于|>|>=|以上',
            'less_than': r'小于|低于|少于|<|<=|以下',
            'equal': r'等于|=|是|为',
            'between': r'之间|到|至'
        }
        
        # 字段模式 - 扩展支持更多字段
        self.field_patterns = {
            'price_fields': ['收盘价', '开盘价', '最高价', '最低价', 'close', 'open', 'high', 'low', '价格'],
            'volume_fields': ['成交量', '成交额', 'vol', 'amount', 'volume', '交易量', '交易额'],
            'ratio_fields': ['涨跌幅', '涨幅', '跌幅', 'pct_change', '换手率', 'turnover_rate', '量比', 'volume_ratio'],
            'valuation_fields': ['市盈率', 'PE', 'pe_ttm', '市净率', 'PB', 'pb', 'pe'],
            'technical_fields': ['MACD', 'RSI', 'KDJ', '布林带', '均线', 'MA']
        }
        
        # 字段到数据库字段的映射
        self.field_db_mapping = {
            '市盈率': 'pe_ttm',
            'PE': 'pe_ttm', 
            'pe': 'pe_ttm',
            '市净率': 'pb',
            'PB': 'pb',
            'pb': 'pb',
            '量比': 'volume_ratio',
            '换手率': 'turnover_rate_f',
            'turnover_rate': 'turnover_rate_f',
            '收盘价': 'daily_close',
            '涨跌幅': 'factor_pct_change',
            '成交量': 'factor_vol',
            '成交额': 'amount'
        }
    
    def extract(self, query: str) -> Dict[str, Any]:
        """提取实体 - 支持复杂多条件查询"""
        entities = {}
        
        # 分割查询条件（支持"且"、"和"、"并且"等连接词）
        conditions = self._split_conditions(query)
        
        # 提取每个条件的实体
        all_conditions = []
        for condition in conditions:
            condition_entities = self._extract_single_condition(condition)
            if condition_entities:
                all_conditions.append(condition_entities)
        
        # 合并所有条件
        if all_conditions:
            entities['conditions'] = all_conditions
            
            # 为了兼容性，也提取全局信息
            entities.update(self._extract_global_info(query))
        else:
            # 如果没有识别到条件，使用原来的方法
            entities.update(self._extract_numbers(query))
            entities.update(self._extract_comparisons(query))
            entities.update(self._extract_fields(query))
        
        # 提取排序信息
        entities.update(self._extract_sorting(query))
        
        # 提取限制数量
        entities.update(self._extract_limits(query))
        
        return entities
    
    def _split_conditions(self, query: str) -> List[str]:
        """分割查询条件"""
        # 使用正则表达式分割条件
        separators = r'[，,]|且|和|并且|同时|以及'
        conditions = re.split(separators, query)
        
        # 清理条件
        cleaned_conditions = []
        for condition in conditions:
            condition = condition.strip()
            if condition and len(condition) > 2:  # 过滤太短的条件
                cleaned_conditions.append(condition)
        
        return cleaned_conditions if len(cleaned_conditions) > 1 else [query]
    
    def _extract_single_condition(self, condition: str) -> Optional[Dict[str, Any]]:
        """提取单个条件的实体"""
        condition_entity = {}
        
        # 特殊处理技术指标条件
        if self._is_technical_indicator_condition(condition):
            return self._extract_technical_condition(condition)
        
        # 提取字段
        field_info = self._extract_field_from_condition(condition)
        if not field_info:
            return None
        
        condition_entity['field'] = field_info
        
        # 提取比较操作符
        comparison = self._extract_comparison_from_condition(condition)
        if comparison:
            condition_entity['comparison'] = comparison
        
        # 提取数值
        value = self._extract_value_from_condition(condition, field_info['category'])
        if value is not None:
            condition_entity['value'] = value
        
        return condition_entity if len(condition_entity) >= 2 else None
    
    def _is_technical_indicator_condition(self, condition: str) -> bool:
        """判断是否为技术指标条件"""
        technical_patterns = [
            r'MACD.*金叉', r'MACD.*死叉', r'MACD.*向上', r'MACD.*向下',
            r'RSI.*超买', r'RSI.*超卖', r'RSI.*大于', r'RSI.*小于',
            r'KDJ.*金叉', r'KDJ.*死叉',
            r'均线.*金叉', r'均线.*死叉', r'均线.*多头', r'均线.*空头'
        ]
        
        for pattern in technical_patterns:
            if re.search(pattern, condition, re.IGNORECASE):
                return True
        
        return False
    
    def _extract_technical_condition(self, condition: str) -> Dict[str, Any]:
        """提取技术指标条件"""
        condition_entity = {}
        
        if 'MACD' in condition:
            condition_entity['field'] = {
                'name': 'MACD',
                'original': 'MACD',
                'category': 'technical_fields',
                'db_field': 'macd'
            }
            
            if '金叉' in condition:
                condition_entity['comparison'] = 'golden_cross'
                condition_entity['value'] = 'golden_cross'  # 特殊值表示金叉
            elif '死叉' in condition:
                condition_entity['comparison'] = 'death_cross'
                condition_entity['value'] = 'death_cross'
        
        elif 'RSI' in condition:
            condition_entity['field'] = {
                'name': 'RSI',
                'original': 'RSI',
                'category': 'technical_fields',
                'db_field': 'rsi_6'
            }
            
            # 提取RSI的数值条件
            comparison = self._extract_comparison_from_condition(condition)
            value = self._extract_value_from_condition(condition, 'technical_fields')
            
            if comparison and value is not None:
                condition_entity['comparison'] = comparison
                condition_entity['value'] = value
            elif '超买' in condition:
                condition_entity['comparison'] = 'greater_than'
                condition_entity['value'] = 70  # RSI超买阈值
            elif '超卖' in condition:
                condition_entity['comparison'] = 'less_than'
                condition_entity['value'] = 30  # RSI超卖阈值
        
        return condition_entity if len(condition_entity) >= 2 else {}
    
    def _extract_field_from_condition(self, condition: str) -> Optional[Dict[str, Any]]:
        """从条件中提取字段"""
        for field_category, field_list in self.field_patterns.items():
            for field in field_list:
                if field in condition:
                    # 标准化字段名
                    standard_field = self._standardize_field_name(field)
                    db_field = self.field_db_mapping.get(standard_field, field)
                    
                    return {
                        'name': standard_field,
                        'original': field,
                        'category': field_category,
                        'db_field': db_field
                    }
        return None
    
    def _extract_comparison_from_condition(self, condition: str) -> Optional[str]:
        """从条件中提取比较操作符"""
        for comp_type, pattern in self.comparison_patterns.items():
            if re.search(pattern, condition):
                return comp_type
        return None
    
    def _extract_value_from_condition(self, condition: str, field_category: str) -> Optional[float]:
        """从条件中提取数值"""
        # 根据字段类别选择合适的数值模式
        if field_category in ['ratio_fields', 'valuation_fields']:
            # 对于比率和估值字段，优先匹配纯数字
            number_match = re.search(r'(\d+(?:\.\d+)?)', condition)
            if number_match:
                return float(number_match.group(1))
        
        # 尝试所有数值模式
        for num_type, pattern in self.number_patterns.items():
            matches = re.findall(pattern, condition)
            if matches:
                return float(matches[0])
        
        return None
    
    def _standardize_field_name(self, field: str) -> str:
        """标准化字段名"""
        # 直接映射
        if field in self.field_db_mapping:
            return field
        
        # 反向查找标准字段名
        for standard_field, db_field in self.field_db_mapping.items():
            if field == db_field:
                return standard_field
        
        # 同义词映射
        field_mapping = {
            'pe_ttm': '市盈率',
            'PE': '市盈率',
            'pe': '市盈率',
            'PB': '市净率',
            'pb': '市净率',
            'volume_ratio': '量比',
            'turnover_rate': '换手率',
            'turnover_rate_f': '换手率',
            'daily_close': '收盘价',
            'factor_pct_change': '涨跌幅',
            'factor_vol': '成交量',
            'amount': '成交额',
            '价格': '收盘价',
            '涨幅': '涨跌幅',
            '跌幅': '涨跌幅'
        }
        
        return field_mapping.get(field, field)
    
    def _extract_global_info(self, query: str) -> Dict[str, Any]:
        """提取全局信息（为了兼容性）"""
        entities = {}
        
        # 提取数值
        entities.update(self._extract_numbers(query))
        
        # 提取比较操作符
        entities.update(self._extract_comparisons(query))
        
        # 提取字段名
        entities.update(self._extract_fields(query))
        
        return entities
    
    def _extract_numbers(self, query: str) -> Dict[str, Any]:
        """提取数值"""
        numbers = {}
        
        for num_type, pattern in self.number_patterns.items():
            matches = re.findall(pattern, query)
            if matches:
                numbers[num_type] = [float(match) for match in matches]
        
        return numbers
    
    def _extract_comparisons(self, query: str) -> Dict[str, Any]:
        """提取比较操作符"""
        comparisons = {}
        
        for comp_type, pattern in self.comparison_patterns.items():
            if re.search(pattern, query):
                comparisons['comparison'] = comp_type
                break
        
        return comparisons
    
    def _extract_fields(self, query: str) -> Dict[str, Any]:
        """提取字段名"""
        fields = {}
        
        for field_category, field_list in self.field_patterns.items():
            for field in field_list:
                if field in query:
                    if 'fields' not in fields:
                        fields['fields'] = []
                    fields['fields'].append({
                        'name': field,
                        'category': field_category
                    })
        
        return fields
    
    def _extract_sorting(self, query: str) -> Dict[str, Any]:
        """提取排序信息"""
        sorting = {}
        
        if re.search(r'排名|排序|排列', query):
            sorting['sort'] = True
            
            if re.search(r'升序|从小到大|asc', query):
                sorting['order'] = 'asc'
            elif re.search(r'降序|从大到小|desc', query):
                sorting['order'] = 'desc'
            else:
                sorting['order'] = 'desc'  # 默认降序
        
        return sorting
    
    def _extract_limits(self, query: str) -> Dict[str, Any]:
        """提取限制数量"""
        limits = {}
        
        # 提取前N名
        top_match = re.search(r'前(\d+)(?:名|个|只|支)?', query)
        if top_match:
            limits['limit'] = int(top_match.group(1))
        
        # 提取top N
        top_match = re.search(r'top\s*(\d+)', query, re.IGNORECASE)
        if top_match:
            limits['limit'] = int(top_match.group(1))
        
        # 默认限制
        if 'limit' not in limits:
            limits['limit'] = 20
        
        return limits


class BusinessDictionaryManager:
    """业务词典管理器"""
    
    def __init__(self):
        self.synonyms_cache = {}
        self._load_synonyms()
    
    def _load_synonyms(self):
        """加载同义词词典"""
        try:
            # 从数据库加载业务词典
            dictionaries = BusinessDictionary.query.filter_by(is_active=True).all()
            
            for dictionary in dictionaries:
                category = dictionary.category
                if category not in self.synonyms_cache:
                    self.synonyms_cache[category] = {}
                
                self.synonyms_cache[category][dictionary.standard_term] = dictionary.synonyms or []
            
        except Exception as e:
            # 如果数据库还没有初始化，使用默认词典
            self._load_default_synonyms()
    
    def _load_default_synonyms(self):
        """加载默认同义词词典"""
        self.synonyms_cache = {
            'stock_fields': {
                '股票代码': ['代码', '证券代码', 'ts_code', '股票'],
                '收盘价': ['收盘', '收价', 'close', '价格'],
                '涨跌幅': ['涨幅', '跌幅', '涨跌', 'pct_change', '涨跌率'],
                '成交量': ['量', 'vol', 'volume', '交易量'],
                '成交额': ['额', 'amount', '交易额', '成交金额'],
                '市盈率': ['PE', 'pe_ttm', 'P/E'],
                '市净率': ['PB', 'pb', 'P/B'],
                '换手率': ['turnover_rate', '换手']
            },
            'technical_indicators': {
                'MACD': ['macd', 'MACD指标', 'macd_dif', 'macd_dea'],
                'RSI': ['rsi', 'RSI指标', 'rsi_6', 'rsi_12', 'rsi_24'],
                '均线': ['MA', 'ma', '移动平均线', 'ma5', 'ma10', 'ma20'],
                'KDJ': ['kdj', 'KDJ指标', 'kdj_k', 'kdj_d', 'kdj_j'],
                '布林带': ['BOLL', 'boll', '布林线', 'bollinger']
            },
            'conditions': {
                '大于': ['>', '超过', '高于', '大于等于', '>='],
                '小于': ['<', '低于', '少于', '小于等于', '<='],
                '等于': ['=', '等于', '是', '为'],
                '排序': ['排名', '排序', '排列', 'order by'],
                '前': ['前', 'top', '最高', '最大'],
                '后': ['后', 'bottom', '最低', '最小']
            }
        }
    
    def normalize(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        """标准化实体"""
        normalized = entities.copy()
        
        # 标准化字段名
        if 'fields' in entities:
            normalized_fields = []
            for field in entities['fields']:
                standard_field = self._normalize_field(field['name'])
                normalized_fields.append({
                    'name': standard_field,
                    'original': field['name'],
                    'category': field['category']
                })
            normalized['fields'] = normalized_fields
        
        return normalized
    
    def _normalize_field(self, field_name: str) -> str:
        """标准化字段名"""
        for category, synonyms_dict in self.synonyms_cache.items():
            for standard_term, synonyms in synonyms_dict.items():
                if field_name in synonyms or field_name == standard_term:
                    return standard_term
        
        return field_name
    
    def get_field_mapping(self, field_name: str) -> Optional[Dict[str, str]]:
        """获取字段映射"""
        # 这里可以扩展为从数据库查询字段映射
        field_mappings = {
            '收盘价': {'table': 'stock_business', 'field': 'daily_close'},
            '涨跌幅': {'table': 'stock_business', 'field': 'factor_pct_change'},
            '成交量': {'table': 'stock_business', 'field': 'vol'},
            '成交额': {'table': 'stock_business', 'field': 'amount'},
            '市盈率': {'table': 'stock_business', 'field': 'pe_ttm'},
            '市净率': {'table': 'stock_business', 'field': 'pb'},
            'MACD': {'table': 'stock_factor', 'field': 'macd'},
            'RSI': {'table': 'stock_factor', 'field': 'rsi_6'},
            '均线': {'table': 'stock_ma_data', 'field': 'ma5'}
        }
        
        return field_mappings.get(field_name) 