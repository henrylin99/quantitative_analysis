"""
Text2SQL核心引擎
整合自然语言处理、SQL生成和查询执行功能
"""

import logging
import os
import re
import time
import traceback
from typing import Dict, List, Any, Optional, Set

logger = logging.getLogger(__name__)
from flask import request
from sqlalchemy import text
from app.extensions import db
from app.services.nlp_processor import NLPProcessor
from app.services.sql_generator import SQLGenerator
from app.services.llm_service import get_llm_service
from app.models.text2sql_metadata import QueryHistory


class Text2SQLEngine:
    """Text2SQL引擎"""
    
    def __init__(self):
        self.nlp_processor = NLPProcessor()
        self.sql_generator = SQLGenerator()
        self.query_executor = QueryExecutor()
        self.result_formatter = ResultFormatter()
        self.llm_service = get_llm_service()
    
    def process_query(self, user_query: str) -> Dict[str, Any]:
        """处理用户查询"""
        start_time = time.time()
        
        try:
            # 1. 自然语言理解
            intent_result = self.nlp_processor.parse_intent(user_query)
            
            # 2. SQL生成
            sql_result = self.sql_generator.generate_sql(intent_result)
            
            # 3. 如果传统方法失败，尝试使用大模型增强
            if not sql_result['success']:
                enhanced_sql = self._try_llm_enhancement(user_query, intent_result)
                if enhanced_sql:
                    sql_result = {
                        'success': True,
                        'sql': enhanced_sql,
                        'template_used': 'llm_enhanced',
                        'explanation': '使用大模型增强生成的SQL'
                    }
            
            if not sql_result['success']:
                return self._create_error_response(
                    user_query, intent_result, None, 
                    sql_result.get('error', 'SQL生成失败'), 
                    time.time() - start_time
                )
            
            # 4. 执行查询
            execution_result = self.query_executor.execute(sql_result['sql'])
            
            if not execution_result['success']:
                return self._create_error_response(
                    user_query, intent_result, sql_result['sql'],
                    execution_result.get('error', '查询执行失败'),
                    time.time() - start_time
                )
            
            # 5. 结果格式化
            formatted_result = self.result_formatter.format(
                execution_result['data'], 
                intent_result['intent']['name'],
                intent_result['entities']
            )
            
            # 6. 记录查询历史
            execution_time = time.time() - start_time
            self._save_query_history(
                user_query, intent_result, sql_result['sql'],
                len(execution_result['data']), True, None,
                sql_result.get('template_used'), execution_time
            )
            
            return {
                'success': True,
                'query': user_query,
                'intent': intent_result['intent'],
                'entities': intent_result['entities'],
                'sql': sql_result['sql'],
                'data': execution_result['data'],
                'formatted_data': formatted_result['data'],
                'chart_config': formatted_result.get('chart_config'),
                'explanation': sql_result.get('explanation'),
                'execution_time': execution_time,
                'result_count': len(execution_result['data']),
                'llm_enhanced': sql_result.get('template_used') == 'llm_enhanced'
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            
            # 记录错误
            self._save_query_history(
                user_query, {}, None, 0, False, error_msg, None, execution_time
            )
            
            return {
                'success': False,
                'query': user_query,
                'error': error_msg,
                'execution_time': execution_time
            }
    
    def get_query_suggestions(self) -> List[Dict[str, Any]]:
        """获取查询建议"""
        suggestions = [
            {
                'text': '找出收盘价大于100元的股票',
                'category': '股票筛选',
                'description': '按价格筛选股票'
            },
            {
                'text': '涨幅超过5%的股票有哪些',
                'category': '股票筛选',
                'description': '按涨跌幅筛选股票'
            },
            {
                'text': 'MACD金叉的股票',
                'category': '技术指标',
                'description': 'MACD技术指标分析'
            },
            {
                'text': '市盈率小于20的股票排名',
                'category': '基本面分析',
                'description': '按市盈率筛选和排序'
            },
            {
                'text': '资金净流入最多的10只股票',
                'category': '资金流向',
                'description': '资金流向分析'
            },
            {
                'text': '成交量前20名的股票',
                'category': '排名查询',
                'description': '按成交量排名'
            },
            {
                'text': 'RSI超买的股票有哪些',
                'category': '技术指标',
                'description': 'RSI技术指标分析'
            },
            {
                'text': 'ROE大于15%的股票',
                'category': '基本面分析',
                'description': '按ROE筛选股票'
            }
        ]
        
        return suggestions
    
    def get_query_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取查询历史"""
        try:
            histories = QueryHistory.list_recent(limit=limit)
            
            return [history.to_dict() for history in histories]
            
        except Exception as e:
            return []
    
    def _create_error_response(self, user_query: str, intent_result: Dict[str, Any], 
                             sql: Optional[str], error: str, execution_time: float) -> Dict[str, Any]:
        """创建错误响应"""
        # 记录错误历史
        self._save_query_history(
            user_query, intent_result, sql, 0, False, error, None, execution_time
        )
        
        return {
            'success': False,
            'query': user_query,
            'intent': intent_result.get('intent'),
            'entities': intent_result.get('entities'),
            'sql': sql,
            'error': error,
            'execution_time': execution_time
        }
    
    def _save_query_history(self, user_query: str, intent_result: Dict[str, Any],
                           sql: Optional[str], result_count: int, is_successful: bool,
                           error_message: Optional[str], template_used: Optional[str],
                           execution_time: float):
        """保存查询历史"""
        try:
            # 获取用户信息
            user_ip = request.remote_addr if request else None
            user_agent = request.headers.get('User-Agent') if request else None
            
            QueryHistory.create_history(
                user_query=user_query,
                intent=intent_result.get('intent', {}).get('name'),
                entities=intent_result.get('entities'),
                generated_sql=sql,
                execution_time=execution_time,
                result_count=result_count,
                is_successful=is_successful,
                error_message=error_message,
                template_used=template_used,
                user_ip=user_ip,
                user_agent=user_agent
            )
        except Exception as e:
            # 记录历史失败不应该影响主流程
            logger.warning(f"保存查询历史失败: {e}")
    
    def _try_llm_enhancement(self, user_query: str, intent_result: Dict[str, Any]) -> Optional[str]:
        """尝试使用大模型增强SQL生成"""
        try:
            # 检查大模型服务状态
            status = self.llm_service.check_service_status()
            if status['status'] not in ['online', 'configured']:
                return None
            
            # 构建上下文
            context = {
                'intent': intent_result['intent'],
                'entities': intent_result['entities'],
                'tables_info': {}  # 可以从元数据中获取表结构信息
            }
            
            # 使用大模型生成SQL
            enhanced_sql = self.llm_service.enhance_sql_generation(user_query, context)
            
            return enhanced_sql
            
        except Exception as e:
            print(f"大模型增强失败: {e}")
            return None


class QueryExecutor:
    """查询执行器
    自动将 Parquet 数据按正确列名映射加载到 SQLite 临时表，
    使生成的 SQL 可以直接在 SQLite 上执行。
    """

    def __init__(self):
        self.max_result_count = 1000
        self._loaded_tables: Set[str] = set()
        # {parquet_abs_path: mtime_at_load} — 用于检测文件是否被重建
        self._file_mtimes: Dict[str, float] = {}

    def invalidate_cache(self):
        """清除已加载的临时表记录，下次查询时重新从 Parquet 加载。"""
        self._loaded_tables.clear()
        self._file_mtimes.clear()

    # ---- Parquet → SQLite 列名映射 ----
    # key = SQL 模板中使用的列名, value = Parquet 文件中的实际列名
    TABLE_COLUMNS = {
        'stock_business': {
            'ts_code': 'ts_code', 'stock_name': 'stock_name',
            'trade_date': 'trade_date', 'daily_close': 'close',
            'factor_pct_change': 'factor_pct_change',
            'vol': 'factor_vol', 'factor_vol': 'factor_vol',
            'amount': 'factor_amount', 'factor_amount': 'factor_amount',
            'pe_ttm': 'pe_ttm', 'pb': 'pb', 'pe': 'pe',
            'turnover_rate': 'turnover_rate',
            'total_mv': 'total_mv', 'circ_mv': 'circ_mv',
        },
        'stock_factor': {
            'ts_code': 'ts_code', 'trade_date': 'trade_date',
            'macd': 'factor_macd', 'macd_dif': 'factor_macd_dif',
            'macd_dea': 'factor_macd_dea',
            'rsi_6': 'factor_rsi_6', 'rsi_12': 'factor_rsi_12',
            'rsi_24': 'factor_rsi_24',
            'kdj_k': 'factor_kdj_k', 'kdj_d': 'factor_kdj_d',
            'kdj_j': 'factor_kdj_j',
        },
        'stock_moneyflow': {
            'ts_code': 'ts_code', 'trade_date': 'trade_date',
            'net_mf_amount': 'moneyflow_net_amount',
            'net_mf_vol': 'moneyflow_net_vol',
        },
        'stock_ma_data': {
            'ts_code': 'ts_code',
            'ma5': 'ma5', 'ma10': 'ma10', 'ma20': 'ma20',
            'ma30': 'ma30', 'ma60': 'ma60', 'ma120': 'ma120',
        },
    }

    # 每张虚拟表对应的 Parquet 源文件
    TABLE_SOURCES = {
        'stock_business':  'stock_business.parquet',
        'stock_factor':    'stock_business.parquet',   # 宽表已含因子数据
        'stock_moneyflow': 'stock_business.parquet',   # 宽表已含资金流数据
        'stock_ma_data':   'stock_ma_data.parquet',
    }

    # ---- public ----

    def execute(self, sql: str) -> Dict[str, Any]:
        """执行SQL查询"""
        try:
            if not sql:
                return {'success': False, 'error': 'SQL为空'}

            # 确保 SQL 引用的数据表已从 Parquet 加载到 SQLite
            self._ensure_data_tables(sql)

            # 执行查询
            result = db.session.execute(text(sql))

            # 获取列名
            columns = list(result.keys())

            # 获取数据
            rows = result.fetchall()

            # 检查结果数量限制
            if len(rows) > self.max_result_count:
                return {
                    'success': False,
                    'error': f'查询结果过多({len(rows)}条)，请添加更多筛选条件'
                }

            # 转换为字典列表
            data = []
            for row in rows:
                row_dict = {}
                for i, column in enumerate(columns):
                    value = row[i]
                    if value is not None:
                        if isinstance(value, (int, float)):
                            row_dict[column] = value
                        else:
                            row_dict[column] = str(value)
                    else:
                        row_dict[column] = None
                data.append(row_dict)

            return {
                'success': True,
                'data': data,
                'columns': columns,
                'row_count': len(data)
            }

        except Exception as e:
            error_msg = str(e)

            # 处理常见的数据库错误
            if 'no such table' in error_msg.lower():
                error_msg = '数据表不存在，请检查数据库配置'
            elif 'no such column' in error_msg.lower():
                error_msg = '字段不存在，请检查查询条件'
            elif 'syntax error' in error_msg.lower():
                error_msg = 'SQL语法错误'

            return {
                'success': False,
                'error': error_msg,
                'data': [],
                'columns': [],
                'row_count': 0
            }

    # ---- private: Parquet → SQLite 桥接 ----

    def _ensure_data_tables(self, sql: str):
        """检查 SQL 引用的表，若缺失或源文件已变更则重新加载"""
        tables = self._extract_table_names(sql)
        for tbl in tables:
            if tbl not in self.TABLE_COLUMNS:
                continue
            if tbl not in self._loaded_tables or self._is_parquet_stale(tbl):
                self._load_parquet_to_sqlite(tbl)

    def _is_parquet_stale(self, table_name: str) -> bool:
        """检测 Parquet 源文件是否在上次加载后被修改（跨进程安全）。"""
        try:
            from flask import current_app
            import os
            data_dir = current_app.config.get('DATA_DIR', 'data')
            if not os.path.isabs(data_dir):
                data_dir = os.path.join(current_app.root_path, '..', data_dir)
            parquet_file = self.TABLE_SOURCES.get(table_name)
            if not parquet_file:
                return False
            parquet_path = os.path.join(data_dir, parquet_file)
            if not os.path.exists(parquet_path):
                return False
            current_mtime = os.path.getmtime(parquet_path)
            cached_mtime = self._file_mtimes.get(parquet_path, 0)
            return current_mtime > cached_mtime
        except Exception:
            return False

    @staticmethod
    def _extract_table_names(sql: str) -> Set[str]:
        """从 FROM / JOIN 子句提取表名"""
        return set(re.findall(r'(?:FROM|JOIN)\s+(\w+)', sql, re.IGNORECASE))

    def _load_parquet_to_sqlite(self, table_name: str):
        """从 Parquet 文件加载数据到 SQLite 临时表"""
        try:
            import pandas as pd
            from flask import current_app

            parquet_file = self.TABLE_SOURCES[table_name]
            data_dir = current_app.config.get('DATA_DIR', 'data')
            if not os.path.isabs(data_dir):
                data_dir = os.path.join(current_app.root_path, '..', data_dir)
            parquet_path = os.path.join(data_dir, parquet_file)

            if not os.path.exists(parquet_path):
                logger.warning(f"Parquet 文件不存在: {parquet_path}")
                return

            df = pd.read_parquet(parquet_path)

            # 只取最新交易日数据（约 5K 行），保持 SQLite 轻量
            if 'trade_date' in df.columns:
                latest_date = df['trade_date'].max()
                df = df[df['trade_date'] == latest_date]

            # 按 TABLE_COLUMNS 映射选取并重命名列
            col_map = self.TABLE_COLUMNS[table_name]
            available = {sql_col: pq_col
                         for sql_col, pq_col in col_map.items()
                         if pq_col in df.columns}
            if not available:
                return

            # 去重 Parquet 列：多个 SQL 名可能映射到同一个 Parquet 列
            unique_pq_cols = list(dict.fromkeys(available.values()))
            df = df[unique_pq_cols].copy()

            # 建立重命名映射：每个 Parquet 列 → 第一个出现的 SQL 列名
            pq_to_first_sql = {}
            for sql_col, pq_col in available.items():
                if pq_col not in pq_to_first_sql:
                    pq_to_first_sql[pq_col] = sql_col
            df.rename(columns=pq_to_first_sql, inplace=True)

            # 补充别名列（同一 Parquet 列的其它 SQL 名）
            for sql_col, pq_col in available.items():
                primary_sql = pq_to_first_sql[pq_col]
                if sql_col != primary_sql and sql_col not in df.columns:
                    df[sql_col] = df[primary_sql]

            # NaN → None（SQLite 不支持 NaN）
            df = df.where(pd.notnull(df), None)

            # 写入 SQLite（通过 raw_connection 使用底层 sqlite3 连接，
            # 兼容 SQLAlchemy 2.0 + Pandas 3.x）
            raw_conn = db.engine.raw_connection()
            try:
                df.to_sql(table_name, raw_conn, if_exists='replace', index=False)
            finally:
                raw_conn.close()

            self._loaded_tables.add(table_name)
            # 记录文件 mtime，后续查询时检测文件是否被重建
            self._file_mtimes[parquet_path] = os.path.getmtime(parquet_path)
            logger.info(f"Loaded {len(df)} rows into '{table_name}' from {parquet_file}")

        except Exception as e:
            logger.error(f"Failed to load '{table_name}' from Parquet: {e}")
            db.session.rollback()


class ResultFormatter:
    """结果格式化器"""
    
    def format(self, data: List[Dict[str, Any]], intent: str, entities: Dict[str, Any]) -> Dict[str, Any]:
        """格式化查询结果"""
        if not data:
            return {
                'data': [],
                'summary': '未找到匹配的数据',
                'chart_config': None
            }
        
        # 格式化数据
        formatted_data = self._format_data(data)
        
        # 生成摘要
        summary = self._generate_summary(data, intent, entities)
        
        # 生成图表配置
        chart_config = self._generate_chart_config(data, intent, entities)
        
        return {
            'data': formatted_data,
            'summary': summary,
            'chart_config': chart_config
        }
    
    def _format_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """格式化数据"""
        formatted_data = []
        
        for row in data:
            formatted_row = {}
            for key, value in row.items():
                if value is not None:
                    # 格式化数值
                    if isinstance(value, (int, float)):
                        try:
                            if 'pct' in key.lower() or 'change' in key.lower():
                                formatted_row[key] = f"{float(value):.2f}%"
                            elif 'price' in key.lower() or 'close' in key.lower():
                                formatted_row[key] = f"¥{float(value):.2f}"
                            elif 'vol' in key.lower() and float(value) > 10000:
                                formatted_row[key] = f"{float(value)/10000:.2f}万"
                            elif 'amount' in key.lower() and float(value) > 100000000:
                                formatted_row[key] = f"{float(value)/100000000:.2f}亿"
                            else:
                                formatted_row[key] = round(float(value), 4)
                        except (ValueError, TypeError):
                            formatted_row[key] = str(value)
                    else:
                        formatted_row[key] = str(value)
                else:
                    formatted_row[key] = '-'
            
            formatted_data.append(formatted_row)
        
        return formatted_data
    
    def _generate_summary(self, data: List[Dict[str, Any]], intent: str, entities: Dict[str, Any]) -> str:
        """生成结果摘要"""
        count = len(data)
        
        if count == 0:
            return "未找到符合条件的股票"
        
        summary_templates = {
            'stock_screening': f"找到 {count} 只符合筛选条件的股票",
            'technical_indicator': f"找到 {count} 只符合技术指标条件的股票",
            'fundamental_analysis': f"找到 {count} 只符合基本面条件的股票",
            'money_flow': f"找到 {count} 只符合资金流向条件的股票",
            'ranking': f"按条件排序，显示前 {count} 只股票"
        }
        
        base_summary = summary_templates.get(intent, f"查询结果：{count} 条记录")
        
        # 添加统计信息
        if data and len(data) > 0:
            first_row = data[0]
            
            # 添加价格范围信息
            if 'daily_close' in first_row:
                prices = [row.get('daily_close', 0) for row in data if row.get('daily_close') is not None]
                if prices:
                    try:
                        min_price = min(float(p) for p in prices)
                        max_price = max(float(p) for p in prices)
                        base_summary += f"，价格范围：¥{min_price:.2f} - ¥{max_price:.2f}"
                    except (ValueError, TypeError):
                        pass
            
            # 添加涨跌幅信息
            if 'factor_pct_change' in first_row:
                changes = [row.get('factor_pct_change', 0) for row in data if row.get('factor_pct_change') is not None]
                if changes:
                    try:
                        min_change = min(float(c) for c in changes)
                        max_change = max(float(c) for c in changes)
                        base_summary += f"，涨跌幅范围：{min_change:.2f}% - {max_change:.2f}%"
                    except (ValueError, TypeError):
                        pass
        
        return base_summary
    
    def _generate_chart_config(self, data: List[Dict[str, Any]], intent: str, entities: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """生成图表配置"""
        if not data or len(data) == 0:
            return None
        
        first_row = data[0]
        
        # 根据数据类型生成不同的图表
        if 'daily_close' in first_row and 'stock_name' in first_row:
            # 价格柱状图
            return {
                'type': 'bar',
                'title': '股票价格分布',
                'x_field': 'stock_name',
                'y_field': 'daily_close',
                'x_label': '股票名称',
                'y_label': '收盘价(元)',
                'data': data[:20]  # 限制显示前20条
            }
        
        elif 'factor_pct_change' in first_row and 'stock_name' in first_row:
            # 涨跌幅柱状图
            return {
                'type': 'bar',
                'title': '股票涨跌幅分布',
                'x_field': 'stock_name',
                'y_field': 'factor_pct_change',
                'x_label': '股票名称',
                'y_label': '涨跌幅(%)',
                'data': data[:20]
            }
        
        elif 'vol' in first_row and 'stock_name' in first_row:
            # 成交量柱状图
            return {
                'type': 'bar',
                'title': '股票成交量分布',
                'x_field': 'stock_name',
                'y_field': 'vol',
                'x_label': '股票名称',
                'y_label': '成交量',
                'data': data[:20]
            }
        
        return None


# 全局Text2SQL引擎实例
_text2sql_engine = None

def get_text2sql_engine() -> Text2SQLEngine:
    """获取Text2SQL引擎实例"""
    global _text2sql_engine
    if _text2sql_engine is None:
        _text2sql_engine = Text2SQLEngine()
    return _text2sql_engine 
