"""AI 智能工作台的工具层。

把项目已有能力封装为大模型可调用的 function-calling 工具：
- 只读类（kind='read'）：SQL 查询、数据目录、任务/因子/模型清单
- 动作类（kind='action'）：下载更新数据、构建大宽表、计算因子、训练模型等

安全约束：
- 所有 SQL 查询复用 text2sql 的 QueryExecutor（单条只读 SELECT 校验 +
  独立只读 SQLite 查询库），模型生成的 SQL 无法写入任何数据
- 动作类工具只允许触发 JobRegistry 中已注册、非 dangerous 的任务，
  TUSHARE 数据源任务要求已配置 TUSHARE_TOKEN
- 动作类工具可在会话层整体关闭（allow_actions=False 时只保留只读工具）
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from flask import current_app

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """工具执行的业务性失败（信息可直接反馈给大模型）。"""


# 查询结果最多回传给大模型的行数（完整行列信息由前端/持久化层另行裁剪）
MAX_ROWS_FOR_LLM = 30
# 单个工具结果回传给大模型的最大字符数
MAX_RESULT_CHARS_FOR_LLM = 12000

# 分区数据集目录 → 数据任务映射（供数据目录扫描与增量更新推导）
DATASET_DIRS = {
    'daily_history': ('daily_history/daily', 'daily_history_by_date'),
    'daily_basic': ('daily_basic/daily', 'daily_basic'),
    'moneyflow': ('moneyflow/daily', 'moneyflow'),
    'stk_factor': ('stk_factor/daily', 'stk_factor'),
    'cyq_perf': ('cyq_perf/daily', 'cyq_perf'),
    'income_statement': ('income_statement', 'income_statement'),
    'balance_sheet': ('balance_sheet', 'balance_sheet'),
    'cash_flow': ('cash_flow', 'cash_flow'),
}


def _resolve_data_dir() -> Path:
    data_dir = current_app.config.get('DATA_DIR', 'data')
    path = Path(data_dir)
    if not path.is_absolute():
        path = Path(current_app.root_path).resolve().parent / data_dir
    return path


def _tushare_token_configured() -> bool:
    token = (os.getenv('TUSHARE_TOKEN') or '').strip()
    return token not in ('', 'your_tushare_token')


# ----------------------------------------------------------------------
# 惰性单例（避免模块导入期触发重资源初始化）
# ----------------------------------------------------------------------

_query_executor = None
_factor_engine = None
_training_service = None
_data_job_service = None


def _get_query_executor():
    global _query_executor
    if _query_executor is None:
        from app.services.text2sql_engine import get_text2sql_engine

        _query_executor = get_text2sql_engine().query_executor
    return _query_executor


def _get_factor_engine():
    global _factor_engine
    if _factor_engine is None:
        from app.services.factor_engine import FactorEngine

        _factor_engine = FactorEngine()
    return _factor_engine


def _get_training_service():
    global _training_service
    if _training_service is None:
        from app.services.model_training_job_service import ModelTrainingJobService

        _training_service = ModelTrainingJobService()
    return _training_service


def _get_data_job_service():
    global _data_job_service
    if _data_job_service is None:
        from app.services.data_jobs.service import DataJobService

        _data_job_service = DataJobService()
    return _data_job_service


def reset_singletons():
    """测试辅助：清理惰性单例。"""
    global _query_executor, _factor_engine, _training_service, _data_job_service
    _query_executor = None
    _factor_engine = None
    _training_service = None
    _data_job_service = None


# ----------------------------------------------------------------------
# 只读工具：数据查询与目录
# ----------------------------------------------------------------------

def _tool_query_data(args: Dict[str, Any]) -> Dict[str, Any]:
    sql = (args.get('sql') or '').strip()
    if not sql:
        raise ToolError('sql 参数不能为空')

    result = _get_query_executor().execute(sql)
    if not result.get('success'):
        raise ToolError(result.get('error') or 'SQL 执行失败')

    rows = result.get('data') or []
    columns = result.get('columns') or []
    truncated = len(rows) > MAX_ROWS_FOR_LLM
    return {
        'columns': columns,
        'row_count': len(rows),
        'rows': rows[:MAX_ROWS_FOR_LLM],
        'truncated': truncated,
        'note': f'结果超过 {MAX_ROWS_FOR_LLM} 行，仅返回前 {MAX_ROWS_FOR_LLM} 行，请用聚合查询或添加 LIMIT/WHERE 缩小范围'
        if truncated
        else None,
    }


def _describe_source_parquet(filename: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {'exists': False, 'row_count': None, 'latest_trade_date': None}
    path = _resolve_data_dir() / filename
    if not path.exists():
        return info
    info['exists'] = True
    try:
        import pandas as pd

        dates = pd.read_parquet(path, columns=['trade_date'])
        info['row_count'] = int(len(dates))
        if not dates.empty:
            info['latest_trade_date'] = str(dates['trade_date'].max())
    except Exception as exc:  # 元数据读取失败不影响目录返回
        info['error'] = str(exc)
    return info


def _tool_list_data_tables(_args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.text2sql_engine import QueryExecutor
    from app.services.wide_table_status import get_wide_table_status

    tables = []
    for table, columns in QueryExecutor.TABLE_COLUMNS.items():
        source = QueryExecutor.TABLE_SOURCES.get(table, '')
        meta = _describe_source_parquet(source)
        tables.append(
            {
                'table': table,
                'source_file': source,
                'columns': sorted(columns.keys()),
                'exists': meta['exists'],
                'row_count': meta['row_count'],
                'latest_trade_date': meta['latest_trade_date'],
            }
        )

    # 分区数据集清单与最新日期（增量更新前先看这里推导 start_date/end_date）
    datasets = []
    for name, (rel_path, job_type) in DATASET_DIRS.items():
        datasets.append(
            {
                'dataset': name,
                'job_type': job_type,
                'latest_date': _dataset_latest_date(rel_path),
            }
        )

    # 原始数据分区（更新数据/构建宽表前可先看各数据源新鲜度）
    wide_status = get_wide_table_status(str(_resolve_data_dir()))
    return {
        'query_tables': tables,
        'datasets': datasets,
        'latest_trade_date': _latest_open_trade_date(),
        'wide_table': {
            'exists': wide_status['exists'],
            'wide_table_date': wide_status['wide_table_date'],
            'source_dates': wide_status['source_dates'],
            'should_update': wide_status['should_update'],
            'reason': wide_status['reason'],
        },
        'hint': (
            'query_data 只能查询上面列出的 query_tables（最新交易日快照）；'
            'datasets 是原始分区数据集，增量更新用 run_data_job 传 '
            'start_date=数据集latest_date的次日、end_date=latest_trade_date'
        ),
    }


def _dataset_latest_date(rel_path: str) -> Optional[str]:
    from app.utils.parquet_job_helpers import latest_partition_date

    try:
        return latest_partition_date(rel_path, data_dir=str(_resolve_data_dir()))
    except Exception:
        return None


def _latest_open_trade_date() -> Optional[str]:
    """日历中 <= 今天的最新开市日（YYYYMMDD），供增量更新推导 end_date。"""
    try:
        import pandas as pd

        from app.utils.time_utils import now_local

        calendar_path = _resolve_data_dir() / 'stock_trade_calendar.parquet'
        if not calendar_path.exists():
            return None
        calendar = pd.read_parquet(calendar_path)
        if calendar.empty or not {'cal_date', 'is_open'}.issubset(calendar.columns):
            return None
        today = pd.Timestamp(now_local().strftime('%Y-%m-%d'))
        work = calendar.copy()
        work['cal_date'] = pd.to_datetime(work['cal_date'], errors='coerce')
        work['is_open'] = pd.to_numeric(work['is_open'], errors='coerce').fillna(0).astype(int)
        open_days = work.loc[work['is_open'] == 1, 'cal_date'].dropna()
        open_days = open_days[open_days <= today]
        if open_days.empty:
            return None
        return open_days.max().strftime('%Y%m%d')
    except Exception:
        return None


def _tool_get_table_schema(args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.text2sql_engine import QueryExecutor

    table = (args.get('table') or '').strip()
    if table not in QueryExecutor.TABLE_COLUMNS:
        raise ToolError(
            f'未知表 {table!r}，可用表: {sorted(QueryExecutor.TABLE_COLUMNS.keys())}'
        )

    columns = QueryExecutor.TABLE_COLUMNS[table]
    sample = _get_query_executor().execute(f'SELECT * FROM {table} LIMIT 5')
    return {
        'table': table,
        'columns': sorted(columns.keys()),
        'sample_rows': sample.get('data') or [],
        'hint': '请以 sample_rows 中的实际数据格式（尤其是 trade_date 的格式与单位）为准',
    }


# ----------------------------------------------------------------------
# 只读工具：数据任务 / 因子 / 模型
# ----------------------------------------------------------------------

def _tool_list_data_jobs(_args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.data_jobs.registry import JobRegistry

    jobs = []
    for definition in JobRegistry().list_jobs():
        jobs.append(
            {
                'job_type': definition.job_type,
                'display_name': definition.display_name,
                'group': definition.group,
                'description': definition.description,
                'dependencies': list(definition.dependencies or []),
                'needs_tushare_token': definition.source_name == 'tushare',
                'dangerous': bool(definition.dangerous),
                'visible': definition.job_type in JobRegistry()._visible_job_types,
            }
        )
    return {
        'jobs': jobs,
        'tushare_token_configured': _tushare_token_configured(),
        'execution_mode': current_app.config.get('DATA_JOB_EXECUTION_MODE', 'celery'),
    }


def _tool_get_data_job_status(args: Dict[str, Any]) -> Dict[str, Any]:
    run_id = args.get('run_id')
    if run_id is None:
        raise ToolError('缺少 run_id 参数')
    try:
        run_id = int(run_id)
    except (TypeError, ValueError):
        raise ToolError('run_id 必须是整数')

    run = _get_data_job_service().get_run(run_id)
    if run is None:
        raise ToolError(f'未找到任务运行记录 run_id={run_id}')
    return run.to_dict()


def _tool_get_wide_table_status(_args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.wide_table_status import get_wide_table_status

    return get_wide_table_status(str(_resolve_data_dir()))


def _tool_list_factors(args: Dict[str, Any]) -> Dict[str, Any]:
    factor_type = args.get('factor_type')
    factors = _get_factor_engine().get_factor_list(factor_type)
    return {'count': len(factors), 'factors': factors}


def _tool_list_ml_models(_args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.ml_models import MLModelManager

    models = MLModelManager().get_model_list()
    return {'count': len(models), 'models': models}


def _tool_get_ml_training_status(args: Dict[str, Any]) -> Dict[str, Any]:
    job_id = (args.get('job_id') or '').strip()
    if not job_id:
        raise ToolError('缺少 job_id 参数')
    snapshot = _get_training_service().get_job_snapshot(job_id)
    if snapshot is None:
        raise ToolError(f'未找到训练任务 job_id={job_id}（任务记录保存在进程内存中，重启后丢失）')
    return snapshot


# ----------------------------------------------------------------------
# 动作工具：数据下载更新 / 宽表 / 因子 / 模型
# ----------------------------------------------------------------------

# 允许通过 AI 触发的数据任务参数（与 ScriptRunner 的环境变量注入对齐）
_ALLOWED_JOB_PARAMS = {'start_date', 'end_date', 'trade_date', 'full_refresh'}


def _run_single_job(job_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """校验并提交一个数据任务（run_data_job / run_data_jobs 共用）。"""
    from app.services.data_jobs.registry import JobRegistry

    registry = JobRegistry()
    try:
        definition = registry.get_job(job_type)
    except KeyError:
        raise ToolError(
            f'未知任务类型 {job_type!r}，可用: {[j.job_type for j in registry.list_jobs()]}'
        )

    if definition.dangerous:
        raise ToolError(f'任务 {job_type} 被标记为危险任务，请在数据管理页面手动执行')

    if definition.source_name == 'tushare' and not _tushare_token_configured():
        raise ToolError(
            '该任务需要 Tushare 数据源，但尚未配置 TUSHARE_TOKEN。'
            '请在项目根目录 .env 中设置 TUSHARE_TOKEN 后重启服务再试'
        )

    if job_type == 'wide_table_builder':
        raise ToolError('大宽表构建请使用 build_wide_table 工具（含 18:00 校验）')

    try:
        run = _get_data_job_service().submit(job_type, params)
    except ValueError as exc:
        raise ToolError(f'任务提交失败: {exc}')

    return {
        'run_id': run.id,
        'job_type': run.job_type,
        'status': run.status,
        'progress': run.progress,
        'progress_message': run.progress_message,
        'error_message': run.error_message,
        'execution_mode': current_app.config.get('DATA_JOB_EXECUTION_MODE', 'celery'),
        'note': (
            'inline 模式下任务已同步执行完成，status 即为最终状态；'
            'celery 模式下任务已入队，可用 get_data_job_status(run_id=...) 轮询进度'
        ),
    }


def _tool_run_data_job(args: Dict[str, Any]) -> Dict[str, Any]:
    job_type = (args.get('job_type') or '').strip()
    if not job_type:
        raise ToolError('缺少 job_type 参数，请先调用 list_data_jobs 查看可用任务')

    raw_params = args.get('params') or {}
    if not isinstance(raw_params, dict):
        raise ToolError('params 必须是对象')
    params = {key: raw_params[key] for key in _ALLOWED_JOB_PARAMS if key in raw_params}
    if 'full_refresh' in params:
        params['full_refresh'] = bool(params['full_refresh'])

    return _run_single_job(job_type, params)


def _tool_run_data_jobs(args: Dict[str, Any]) -> Dict[str, Any]:
    """批量顺序执行多个数据任务，单个失败不阻断后续任务。"""
    job_types = args.get('job_types') or []
    if not isinstance(job_types, list) or not job_types:
        raise ToolError('job_types 必须是非空数组')

    raw_params = args.get('params') or {}
    if not isinstance(raw_params, dict):
        raise ToolError('params 必须是对象')
    params = {key: raw_params[key] for key in _ALLOWED_JOB_PARAMS if key in raw_params}
    if 'full_refresh' in params:
        params['full_refresh'] = bool(params['full_refresh'])

    results = []
    for job_type in job_types:
        try:
            summary = _run_single_job(str(job_type).strip(), dict(params))
            ok = summary['status'] not in ('failed', 'cancelled')
            results.append({'job_type': job_type, 'ok': ok, **summary})
        except ToolError as exc:
            results.append({'job_type': job_type, 'ok': False, 'error': str(exc)})

    succeeded = sum(1 for item in results if item['ok'])
    return {
        'total': len(results),
        'succeeded': succeeded,
        'failed': len(results) - succeeded,
        'results': results,
        'note': '任务按顺序同步执行，单条记录的 status/error_message 为该任务最终状态',
    }


def _tool_build_wide_table(_args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.wide_table_status import get_wide_table_status

    status = get_wide_table_status(str(_resolve_data_dir()))
    if not status['past_cutoff']:
        raise ToolError(
            '当前时间未过 18:00，数据源可能尚未下载完毕，暂不允许构建大宽表。'
            f"当前宽表日期: {status['wide_table_date'] or '不存在'}；"
            '请 18:00 后再试，或先检查各数据源日期'
        )

    try:
        run = _get_data_job_service().submit('wide_table_builder', {})
    except ValueError as exc:
        raise ToolError(f'任务提交失败: {exc}')

    if run.status == 'success':
        from app.services.data_reader import ParquetDataReader
        from app.services.text2sql_engine import get_text2sql_engine

        ParquetDataReader.invalidate_stock_business_cache()
        get_text2sql_engine().query_executor.invalidate_cache()

    return {
        'run_id': run.id,
        'status': run.status,
        'progress_message': run.progress_message,
        'error_message': run.error_message,
        'wide_table_status': get_wide_table_status(str(_resolve_data_dir())),
        'note': '构建成功后查询缓存已自动刷新，可直接用 query_data 查询最新宽表',
    }


def _normalize_trade_date(raw: str) -> str:
    """因子/模型服务层统一使用 YYYY-MM-DD 格式（factor_engine 内部按此 strptime）。"""
    text = str(raw or '').strip()
    compact = text.replace('-', '')
    if len(compact) != 8 or not compact.isdigit():
        raise ToolError(f'日期格式应为 YYYY-MM-DD 或 YYYYMMDD，收到: {raw!r}')
    return f'{compact[:4]}-{compact[4:6]}-{compact[6:]}'


def _tool_calculate_factors(args: Dict[str, Any]) -> Dict[str, Any]:
    trade_date = _normalize_trade_date(args.get('trade_date'))
    factor_ids = args.get('factor_ids') or []
    ts_codes = args.get('ts_codes') or []
    if not isinstance(factor_ids, list) or not isinstance(ts_codes, list):
        raise ToolError('factor_ids 与 ts_codes 必须是数组')

    engine = _get_factor_engine()

    if factor_ids:
        results = []
        for factor_id in factor_ids:
            try:
                result_df = engine.calculate_factor(factor_id, ts_codes, trade_date, trade_date)
                if result_df.empty:
                    results.append({'factor_id': factor_id, 'calculated_count': 0, 'error': '无数据'})
                    continue
                saved = engine.save_factor_values(result_df)
                results.append(
                    {'factor_id': factor_id, 'calculated_count': int(len(result_df)), 'saved': saved}
                )
            except Exception as exc:
                results.append({'factor_id': factor_id, 'error': str(exc)})
        return {'trade_date': trade_date, 'results': results}

    try:
        result_df = engine.calculate_all_factors(trade_date, ts_codes)
    except Exception as exc:
        raise ToolError(f'因子计算失败: {exc}')

    if result_df.empty:
        raise ToolError('计算结果为空，请确认该交易日数据已下载（可先查宽表最新日期）')

    saved = engine.save_factor_values(result_df)
    factor_stats = result_df.groupby('factor_id').size().to_dict() if 'factor_id' in result_df.columns else {}
    return {
        'trade_date': trade_date,
        'total_calculated': int(len(result_df)),
        'factor_stats': {key: int(value) for key, value in factor_stats.items()},
        'saved': saved,
    }


def _tool_create_custom_factor(args: Dict[str, Any]) -> Dict[str, Any]:
    factor_id = (args.get('factor_id') or '').strip()
    factor_name = (args.get('factor_name') or '').strip()
    formula = (args.get('factor_formula') or '').strip()
    factor_type = (args.get('factor_type') or 'custom').strip()
    if not factor_id or not factor_name or not formula:
        raise ToolError('factor_id、factor_name、factor_formula 均为必填')

    engine = _get_factor_engine()
    validation = engine.validate_custom_factor_formula(formula)
    if not validation.get('valid'):
        raise ToolError(f'因子公式未通过白名单校验: {validation.get("error")}')

    created = engine.create_factor_definition(
        factor_id,
        factor_name,
        formula,
        factor_type,
        description=args.get('description'),
        params=args.get('params'),
    )
    if not created:
        raise ToolError('因子创建失败（可能 factor_id 已存在）')
    return {
        'success': True,
        'factor_id': factor_id,
        'note': '因子定义已保存，还需调用 calculate_factors(trade_date=...) 生成因子值',
    }


def _tool_train_ml_model(args: Dict[str, Any]) -> Dict[str, Any]:
    model_id = (args.get('model_id') or '').strip()
    if not model_id:
        raise ToolError('缺少 model_id 参数，可先调用 list_ml_models 查看已有模型')

    snapshot = _get_training_service().submit_job(
        model_id, args.get('start_date') or '', args.get('end_date') or ''
    )
    return {
        'job_id': snapshot['job_id'],
        'status': snapshot['status'],
        'start_date': snapshot['start_date'],
        'end_date': snapshot['end_date'],
        'date_range_adjusted': snapshot.get('date_range_adjusted'),
        'note': '训练为异步任务，请用 get_ml_training_status(job_id=...) 轮询进度',
    }


def _tool_predict_ml_model(args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.ml_models import MLModelManager

    model_id = (args.get('model_id') or '').strip()
    if not model_id:
        raise ToolError('缺少 model_id 参数')
    trade_date = _normalize_trade_date(args.get('trade_date'))
    ts_codes = args.get('ts_codes') or []

    try:
        predictions = MLModelManager().predict(model_id, trade_date, ts_codes)
    except Exception as exc:
        raise ToolError(f'模型预测失败: {exc}')

    if predictions is None or predictions.empty:
        raise ToolError('预测结果为空（可能模型未训练、或该交易日因子数据缺失，可先计算因子）')

    score_column = next(
        (column for column in ('probability_score', 'predicted_return', 'prediction', 'score') if column in predictions.columns),
        None,
    )
    if score_column:
        predictions = predictions.sort_values(score_column, ascending=False)
    return {
        'trade_date': trade_date,
        'model_id': model_id,
        'total': int(len(predictions)),
        'score_column': score_column,
        'top_predictions': predictions.head(20).to_dict(orient='records'),
    }


# ----------------------------------------------------------------------
# 工具注册表
# ----------------------------------------------------------------------

class AiTool:
    def __init__(self, name: str, description: str, parameters: Dict[str, Any],
                 kind: str, handler: Callable[[Dict[str, Any]], Any]):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.kind = kind  # 'read' | 'action'
        self.handler = handler

    def to_spec(self) -> Dict[str, Any]:
        return {
            'type': 'function',
            'function': {
                'name': self.name,
                'description': self.description,
                'parameters': self.parameters,
            },
        }


AI_TOOLS: List[AiTool] = [
    AiTool(
        'query_data',
        '对本地行情数据库执行只读 SQL 查询（SQLite 方言）。可查表：stock_business（最新交易日全市场快照，含估值/换手/涨跌幅/技术指标/资金流）、stock_factor（技术指标）、stock_moneyflow（资金流）、stock_ma_data（均线）。仅允许单条 SELECT，结果最多返回 30 行。',
        {
            'type': 'object',
            'properties': {
                'sql': {'type': 'string', 'description': 'SQLite 只读 SELECT 语句'},
            },
            'required': ['sql'],
        },
        'read',
        _tool_query_data,
    ),
    AiTool(
        'list_data_tables',
        '数据目录：可查询表及列名/行数/最新交易日、各分区数据集(daily_history/daily_basic/moneyflow/stk_factor/cyq_perf/财务三表)的最新日期、最新交易日历开市日、大宽表状态。做数据更新或分析前先调用本工具。',
        {'type': 'object', 'properties': {}},
        'read',
        _tool_list_data_tables,
    ),
    AiTool(
        'get_table_schema',
        '查看某张可查询表的列清单和 5 行样例数据（用于确认字段格式、trade_date 格式与数值单位）。',
        {
            'type': 'object',
            'properties': {
                'table': {'type': 'string', 'enum': ['stock_business', 'stock_factor', 'stock_moneyflow', 'stock_ma_data']},
            },
            'required': ['table'],
        },
        'read',
        _tool_get_table_schema,
    ),
    AiTool(
        'list_data_jobs',
        '列出系统支持的数据下载/更新任务类型（job_type）、用途说明、依赖关系，以及是否需要 TUSHARE_TOKEN。',
        {'type': 'object', 'properties': {}},
        'read',
        _tool_list_data_jobs,
    ),
    AiTool(
        'run_data_job',
        '提交单个数据下载/更新任务。需要已配置 TUSHARE_TOKEN。增量更新务必先用 list_data_tables 查看数据集 latest_date 与 latest_trade_date，再传 params.start_date=latest_date次日、end_date=latest_trade_date（不传日期时部分任务只下载最新交易日一天，会留缺口）。财务三表（income_statement/balance_sheet/cash_flow）走 vip 接口按报告期增量更新。inline 模式同步执行完返回结果；celery 模式返回 run_id 供轮询。',
        {
            'type': 'object',
            'properties': {
                'job_type': {'type': 'string', 'description': '任务类型，见 list_data_jobs'},
                'params': {
                    'type': 'object',
                    'properties': {
                        'start_date': {'type': 'string', 'description': '起始日期 YYYYMMDD（增量起点=本地最新日期+1）'},
                        'end_date': {'type': 'string', 'description': '结束日期 YYYYMMDD（一般=latest_trade_date）'},
                        'trade_date': {'type': 'string', 'description': '单日补数时的交易日 YYYYMMDD'},
                        'full_refresh': {'type': 'boolean', 'description': '全量刷新，慎用，需先与用户确认'},
                    },
                },
            },
            'required': ['job_type'],
        },
        'action',
        _tool_run_data_job,
    ),
    AiTool(
        'run_data_jobs',
        '按顺序批量执行多个数据任务（用于"更新所有数据"等场景），单个失败不阻断后续任务，返回逐任务结果。参数同 run_data_job。',
        {
            'type': 'object',
            'properties': {
                'job_types': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': '任务类型列表，按依赖顺序排列',
                },
                'params': {
                    'type': 'object',
                    'properties': {
                        'start_date': {'type': 'string'},
                        'end_date': {'type': 'string'},
                        'trade_date': {'type': 'string'},
                        'full_refresh': {'type': 'boolean'},
                    },
                },
            },
            'required': ['job_types'],
        },
        'action',
        _tool_run_data_jobs,
    ),
    AiTool(
        'get_data_job_status',
        '查询数据任务的执行状态与进度（run_id 来自 run_data_job / build_wide_table 的返回）。',
        {
            'type': 'object',
            'properties': {'run_id': {'type': 'integer'}},
            'required': ['run_id'],
        },
        'read',
        _tool_get_data_job_status,
    ),
    AiTool(
        'build_wide_table',
        '构建/更新大宽表（stock_business，合并日线指标、技术因子、资金流与股票基础资料，供 query_data 查询）。仅 18:00 后允许构建；构建后自动刷新查询缓存。',
        {'type': 'object', 'properties': {}},
        'action',
        _tool_build_wide_table,
    ),
    AiTool(
        'get_wide_table_status',
        '查询大宽表状态：是否存在、宽表日期、各数据源最新分区日期、是否需要更新、是否已过 18:00。',
        {'type': 'object', 'properties': {}},
        'read',
        _tool_get_wide_table_status,
    ),
    AiTool(
        'list_factors',
        '列出系统内置因子与已创建的自定义因子（factor_id、类型、公式等）。',
        {
            'type': 'object',
            'properties': {
                'factor_type': {'type': 'string', 'description': '可选，按类型过滤'},
            },
        },
        'read',
        _tool_list_factors,
    ),
    AiTool(
        'calculate_factors',
        '计算指定交易日的因子值并保存。不传 factor_ids 时计算全部因子。全市场计算可能耗时较长。',
        {
            'type': 'object',
            'properties': {
                'trade_date': {'type': 'string', 'description': '交易日 YYYY-MM-DD（如 2026-08-21）'},
                'factor_ids': {'type': 'array', 'items': {'type': 'string'}},
                'ts_codes': {'type': 'array', 'items': {'type': 'string'}, 'description': '可选，股票代码列表，如 000001.SZ'},
            },
            'required': ['trade_date'],
        },
        'action',
        _tool_calculate_factors,
    ),
    AiTool(
        'create_custom_factor',
        '创建自定义因子定义（公式仅支持白名单表达式，如 close/open、均值、涨幅等算术表达式）。',
        {
            'type': 'object',
            'properties': {
                'factor_id': {'type': 'string'},
                'factor_name': {'type': 'string'},
                'factor_formula': {'type': 'string', 'description': '如 (close - open) / open * 100'},
                'factor_type': {'type': 'string', 'description': '如 custom / technical / fundamental'},
                'description': {'type': 'string'},
                'params': {'type': 'object'},
            },
            'required': ['factor_id', 'factor_name', 'factor_formula'],
        },
        'action',
        _tool_create_custom_factor,
    ),
    AiTool(
        'list_ml_models',
        '列出已创建的机器学习模型（model_id、类型、训练状态等）。',
        {'type': 'object', 'properties': {}},
        'read',
        _tool_list_ml_models,
    ),
    AiTool(
        'train_ml_model',
        '提交模型训练任务（异步执行），返回 job_id。日期可不传由系统解析可用区间。',
        {
            'type': 'object',
            'properties': {
                'model_id': {'type': 'string'},
                'start_date': {'type': 'string', 'description': 'YYYYMMDD，可选'},
                'end_date': {'type': 'string', 'description': 'YYYYMMDD，可选'},
            },
            'required': ['model_id'],
        },
        'action',
        _tool_train_ml_model,
    ),
    AiTool(
        'get_ml_training_status',
        '查询模型训练任务的进度、日志与结果。',
        {
            'type': 'object',
            'properties': {'job_id': {'type': 'string'}},
            'required': ['job_id'],
        },
        'read',
        _tool_get_ml_training_status,
    ),
    AiTool(
        'predict_ml_model',
        '用已训练的模型对指定交易日生成预测评分，返回得分最高的前 20 只股票。',
        {
            'type': 'object',
            'properties': {
                'model_id': {'type': 'string'},
                'trade_date': {'type': 'string', 'description': 'YYYY-MM-DD'},
                'ts_codes': {'type': 'array', 'items': {'type': 'string'}},
            },
            'required': ['model_id', 'trade_date'],
        },
        'action',
        _tool_predict_ml_model,
    ),
]

_TOOL_INDEX: Dict[str, AiTool] = {tool.name: tool for tool in AI_TOOLS}


def get_tool_specs(allow_actions: bool = True) -> List[Dict[str, Any]]:
    """返回传给大模型的 tools 参数；只读模式下剔除动作类工具。"""
    return [tool.to_spec() for tool in AI_TOOLS if allow_actions or tool.kind == 'read']


def list_tool_summaries(allow_actions: bool = True) -> List[Dict[str, str]]:
    return [
        {'name': tool.name, 'kind': tool.kind, 'description': tool.description}
        for tool in AI_TOOLS
        if allow_actions or tool.kind == 'read'
    ]


def _truncate_for_llm(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= MAX_RESULT_CHARS_FOR_LLM:
        return text
    return text[:MAX_RESULT_CHARS_FOR_LLM] + f'...（结果过长，已截断至 {MAX_RESULT_CHARS_FOR_LLM} 字符）'


def execute_tool(name: str, arguments: Dict[str, Any], allow_actions: bool = True) -> Dict[str, Any]:
    """执行一个工具调用，返回统一结构 {ok, name, result|error}。

    动作类工具在 allow_actions=False 时直接拒绝。
    """
    tool = _TOOL_INDEX.get(name)
    if tool is None:
        return {'ok': False, 'name': name, 'error': f'未知工具 {name!r}'}
    if tool.kind == 'action' and not allow_actions:
        return {
            'ok': False,
            'name': name,
            'error': '当前会话为只读模式，动作类工具已被禁用；请在页面开启「操作模式」后重试',
        }

    try:
        result = tool.handler(arguments or {})
        return {'ok': True, 'name': name, 'result': result, 'result_for_llm': _truncate_for_llm(result)}
    except ToolError as exc:
        return {'ok': False, 'name': name, 'error': str(exc), 'result_for_llm': json.dumps(
            {'error': str(exc)}, ensure_ascii=False)}
    except Exception as exc:  # 工具内部异常不中断会话，反馈给模型自行调整
        logger.exception('AI 工具 %s 执行异常', name)
        return {
            'ok': False,
            'name': name,
            'error': f'工具内部错误: {exc}',
            'result_for_llm': json.dumps({'error': f'工具内部错误: {exc}'}, ensure_ascii=False),
        }
