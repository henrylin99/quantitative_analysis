"""
Text2SQL核心引擎
整合自然语言处理、SQL生成和查询执行功能
"""

import logging
import os
import re
import sqlite3
import threading
import time
from typing import Dict, List, Any, Optional, Set

try:
    import fcntl  # 跨进程文件锁（POSIX）；Windows 降级为仅进程内锁
except ImportError:  # pragma: no cover
    fcntl = None

logger = logging.getLogger(__name__)
from flask import request
from app.services.nlp_processor import NLPProcessor
from app.services.sql_generator import SQLGenerator, validate_readonly_sql
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
                'data_scope': execution_result.get('data_scope'),
                'llm_enhanced': sql_result.get('template_used') == 'llm_enhanced'
            }
            
        except Exception:
            execution_time = time.time() - start_time
            # 完整异常进日志；返回值与查询历史（会经 /history API 暴露）只保留通用消息
            logger.exception("Text2SQL 查询处理失败: %s", user_query[:200])
            error_msg = '查询处理失败，请调整查询后重试（详情见服务日志）'

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
            
        except Exception:
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
            logger.warning(f"大模型增强失败: {e}")
            return None


class QueryExecutor:
    """查询执行器
    自动将 Parquet 数据按正确列名映射加载到 SQLite 临时表，
    使生成的 SQL 可以直接在 SQLite 上执行。
    """

    # 进程级加载锁：并发请求触发同一虚拟表加载时串行执行，
    # 配合"临时表 + 事务内改名"保证读连接要么看到旧表要么看到新表
    _load_lock = threading.Lock()

    # 单次加载行数上限：日期范围过大时截断保留最近的数据，
    # 防止全历史加载把请求拖到分钟级（可用 TEXT2SQL_MAX_LOAD_ROWS 调整）
    MAX_LOAD_ROWS = int(os.getenv('TEXT2SQL_MAX_LOAD_ROWS', '500000'))

    # SQL 中的日期字面量（'YYYY-MM-DD' 或 'YYYYMMDD'）
    _DATE_LITERAL_RE = re.compile(r"'(\d{4}-\d{2}-\d{2}|\d{8})'")

    def __init__(self):
        self.max_result_count = 1000
        # {虚拟表名: 加载时的日期范围 key} — 范围不同的查询会触发重新加载
        self._loaded_tables: Dict[str, str] = {}
        # {parquet_abs_path: mtime_at_load} — 用于检测文件是否被重建
        self._file_mtimes: Dict[str, float] = {}
        # {(虚拟表名, 范围 key)} — 加载时被行数上限截断的范围，命中即拒绝执行
        self._truncated_scopes: Set[Any] = set()

    def invalidate_cache(self):
        """清除已加载的临时表记录，下次查询时重新从 Parquet 加载。"""
        self._loaded_tables.clear()
        self._file_mtimes.clear()
        self._truncated_scopes.clear()

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
        """执行SQL查询。

        安全约束（chokepoint，规则生成/模板/LLM 增强的 SQL 都经过这里）:
        - 只允许单条只读 SELECT（详见 validate_readonly_sql）
        - 查询在独立的只读 SQLite 连接上执行，与应用主库
          （query_history/query_templates 等应用数据）物理隔离，
          即使校验被绕过也无法读写应用数据
        """
        scope = None
        try:
            if not sql:
                return {'success': False, 'error': 'SQL为空'}

            readonly_ok, readonly_error = validate_readonly_sql(sql)
            if not readonly_ok:
                logger.warning(f"拒绝执行非只读SQL: {readonly_error}; sql={sql[:200]}")
                return {'success': False, 'error': f'仅允许只读SELECT查询: {readonly_error}'}

            # 确保 SQL 引用的数据表已按查询日期范围加载到查询库
            scope = self._ensure_data_tables(sql)

            # fail-closed：目标范围加载时被行数上限截断（含缓存命中），
            # 拒绝返回可能不完整的结果，而不是静默给出近似数据
            needed_tables = [t for t in self._extract_table_names(sql) if t in self.TABLE_COLUMNS]
            if any((t, scope['key']) in self._truncated_scopes for t in needed_tables):
                return {
                    'success': False,
                    'error': (
                        f"查询涉及的日期范围数据量超过加载上限"
                        f"（TEXT2SQL_MAX_LOAD_ROWS={self.MAX_LOAD_ROWS}），"
                        "为避免返回不完整结果已拒绝执行；请缩小日期范围或添加筛选条件"
                    ),
                    'data_scope': scope,
                }

            conn = self._open_readonly_connection()
            try:
                cursor = conn.execute(sql)
                columns = [desc[0] for desc in (cursor.description or [])]
                rows = cursor.fetchmany(self.max_result_count + 1)
            finally:
                conn.close()

            # 检查结果数量限制（fetchmany 多取一条用于判断超限）
            if len(rows) > self.max_result_count:
                return {
                    'success': False,
                    'error': f'查询结果过多(超过{self.max_result_count}条)，请添加更多筛选条件',
                    'data_scope': scope,
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
                'row_count': len(data),
                'data_scope': scope,
            }

        except sqlite3.OperationalError as e:
            error_msg = str(e)
            if 'no such table' in error_msg.lower():
                error_msg = '数据表不存在，请检查数据库配置'
            elif 'no such column' in error_msg.lower():
                error_msg = '字段不存在，请检查查询条件'
            elif 'readonly' in error_msg.lower():
                error_msg = '仅允许只读SELECT查询'
            return {
                'success': False,
                'error': error_msg,
                'data': [],
                'columns': [],
                'row_count': 0,
                'data_scope': scope,
            }
        except Exception:
            # 未知异常不外透细节：避免向客户端暴露 SQL/内部结构，
            # 完整堆栈留在服务日志
            logger.exception("查询执行失败")
            return {
                'success': False,
                'error': '查询执行失败，请调整查询后重试（详情见服务日志）',
                'data': [],
                'columns': [],
                'row_count': 0,
                'data_scope': scope,
            }

    # ---- private: 查询库连接 ----

    def _query_db_path(self) -> str:
        """text2sql 查询库路径：与应用主库隔离的独立 SQLite 文件。"""
        from flask import current_app
        data_dir = current_app.config.get('DATA_DIR', 'data')
        if not os.path.isabs(data_dir):
            data_dir = os.path.join(current_app.root_path, '..', data_dir)
        return os.path.join(data_dir, 'text2sql_query.db')

    def _open_readonly_connection(self) -> sqlite3.Connection:
        """以只读模式打开查询库（URI mode=ro，写操作会被 SQLite 本身拒绝）。

        timeout 为 busy handler 等待秒数：另一进程正在写查询库时
        读连接等待而非立即抛 database is locked。
        """
        path = self._query_db_path()
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            sqlite3.connect(path).close()  # 确保文件存在
        return sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=30)

    # ---- private: Parquet → SQLite 桥接 ----

    @classmethod
    def _resolve_date_scope(cls, sql: str) -> Dict[str, Any]:
        """根据 SQL 推断虚拟表需要覆盖的日期范围。

        - SQL 带日期字面量 → 加载 [min, max] 范围（受 MAX_LOAD_ROWS 上限，超出保留最近）
        - SQL 引用 trade_date 但无字面量（如 ORDER BY trade_date）→ 不限日期，同样受上限
        - 与日期无关的查询 → 仅加载最新交易日，保持 SQLite 轻量
        """
        mentions_trade_date = 'trade_date' in sql.lower()
        dates = []
        for raw in cls._DATE_LITERAL_RE.findall(sql):
            # Parquet 中 trade_date 为 'YYYY-MM-DD' 字符串，统一成该格式再比较
            dates.append(raw if '-' in raw else f"{raw[:4]}-{raw[4:6]}-{raw[6:]}")
        if dates:
            start, end = min(dates), max(dates)
            return {'mode': 'range', 'start': start, 'end': end, 'key': f'{start}~{end}', 'tables': {}}
        if mentions_trade_date:
            return {'mode': 'range', 'start': None, 'end': None, 'key': 'history', 'tables': {}}
        return {'mode': 'latest', 'start': None, 'end': None, 'key': 'latest', 'tables': {}}

    def _ensure_data_tables(self, sql: str) -> Dict[str, Any]:
        """检查 SQL 引用的表，按查询日期范围加载缺失/过期/口径不符的虚拟表。

        同一 Parquet 文件可能对应多个虚拟表（如 stock_business.parquet
        同时是 stock_business / stock_factor / stock_moneyflow 的源），
        文件变更时需重置所有共享该文件的已加载虚拟表。
        返回本次查询的数据范围说明（data_scope），随查询结果一并返回，
        让调用方知道虚拟表实际覆盖的日期，避免"看似成功实则缺历史"。
        """
        scope = self._resolve_date_scope(sql)
        tables = self._extract_table_names(sql)
        stale_tables = set()
        for tbl in tables:
            if tbl not in self.TABLE_COLUMNS:
                continue
            if self._loaded_tables.get(tbl) != scope['key']:
                stale_tables.add(tbl)
            elif self._is_parquet_stale(tbl):
                stale_tables.add(tbl)
                # 文件变更 → 重置所有共享同一 Parquet 源的已加载虚拟表
                stale_file = self.TABLE_SOURCES.get(tbl)
                for loaded_tbl in list(self._loaded_tables):
                    if self.TABLE_SOURCES.get(loaded_tbl) == stale_file:
                        stale_tables.add(loaded_tbl)

        for tbl in stale_tables:
            self._load_parquet_to_sqlite(tbl, scope)

        if scope['mode'] == 'latest':
            scope['note'] = '虚拟表仅包含最新交易日的数据（查询未涉及日期条件）'
        elif scope['start']:
            scope['note'] = f"虚拟表覆盖 {scope['start']} ~ {scope['end']} 的数据（受行数上限约束）"
        else:
            scope['note'] = '虚拟表包含历史数据（受行数上限约束，超限保留最近的数据）'
        return scope

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
            # 按 (table_name, parquet_path) 追踪，每个虚拟表独立记录
            cached_mtime = self._file_mtimes.get((table_name, parquet_path), 0)
            return current_mtime > cached_mtime
        except Exception:
            return False

    @staticmethod
    def _extract_table_names(sql: str) -> Set[str]:
        """从 FROM / JOIN 子句提取表名"""
        return set(re.findall(r'(?:FROM|JOIN)\s+(\w+)', sql, re.IGNORECASE))

    def _load_parquet_to_sqlite(self, table_name: str, scope: Dict[str, Any]):
        """按日期范围从 Parquet 加载数据到 SQLite 虚拟表。

        双层锁：
        - threading.Lock 串行化进程内并发请求
        - flock 文件锁串行化多进程部署（多个 gunicorn worker）下的加载
        加上"临时表 + 事务内改名"，读连接要么看到旧表要么看到新表
        """
        with QueryExecutor._load_lock:
            lock_path = self._query_db_path() + '.load.lock'
            os.makedirs(os.path.dirname(lock_path) or '.', exist_ok=True)
            with open(lock_path, 'a+') as lock_fh:
                if fcntl is not None:
                    fcntl.flock(lock_fh, fcntl.LOCK_EX)
                try:
                    self._load_parquet_to_sqlite_locked(table_name, scope)
                finally:
                    if fcntl is not None:
                        fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def _load_parquet_to_sqlite_locked(self, table_name: str, scope: Dict[str, Any]):
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

            current_mtime = os.path.getmtime(parquet_path)
            # 双重检查：等其他线程释放锁期间，同一 scope 可能已由别人加载完成
            if (self._loaded_tables.get(table_name) == scope['key']
                    and self._file_mtimes.get((table_name, parquet_path), 0) >= current_mtime):
                return

            df = pd.read_parquet(parquet_path)

            truncated = False
            if 'trade_date' in df.columns:
                if scope['mode'] == 'latest':
                    # 无日期条件的查询只取最新交易日（约 5K 行），保持 SQLite 轻量
                    latest_date = df['trade_date'].max()
                    df = df[df['trade_date'] == latest_date]
                else:
                    if scope.get('start'):
                        df = df[df['trade_date'] >= scope['start']]
                    if scope.get('end'):
                        df = df[df['trade_date'] <= scope['end']]
                    if len(df) > self.MAX_LOAD_ROWS:
                        # trade_date 为 ISO 字符串，字典序即时序；超限保留最近的数据
                        df = df.sort_values('trade_date', kind='stable').tail(self.MAX_LOAD_ROWS)
                        truncated = True

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

            # 先写入 staging 临时表，再在同一事务内 DROP 旧表 + 改名，
            # 保证并发读连接不会观察到表被清空的中间状态
            conn = sqlite3.connect(self._query_db_path(), timeout=30)
            staging = f"{table_name}__staging"
            try:
                df.to_sql(staging, conn, if_exists='replace', index=False)
                conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                conn.execute(f'ALTER TABLE "{staging}" RENAME TO "{table_name}"')
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

            self._loaded_tables[table_name] = scope['key']
            # 按 (虚拟表名, 文件路径) 记录 mtime，同一文件的不同虚拟表独立追踪
            self._file_mtimes[(table_name, parquet_path)] = current_mtime
            if truncated:
                self._truncated_scopes.add((table_name, scope['key']))
            else:
                self._truncated_scopes.discard((table_name, scope['key']))
            scope['tables'][table_name] = {
                'rows': int(len(df)),
                'loaded_start': str(df['trade_date'].min()) if 'trade_date' in df.columns and len(df) else None,
                'loaded_end': str(df['trade_date'].max()) if 'trade_date' in df.columns and len(df) else None,
                'truncated': truncated,
            }
            logger.info(
                f"Loaded {len(df)} rows into '{table_name}' from {parquet_file} "
                f"(scope={scope['key']}, truncated={truncated})"
            )

        except Exception as e:
            logger.error(f"Failed to load '{table_name}' from Parquet: {e}")


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
