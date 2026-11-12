"""命名策略服务：策略定义的组装、按名回测与多 run 对比。

AI 工作台 save_strategy / run_strategy / compare_backtests 三个工具的
业务层。策略 config schema：

    {
      "engine_config": {           # 原样作为 BacktestEngine 的 strategy_config
        "selection_method": "factor_based",
        "factor_list": [...],
        "weights": {"factor": 0.6, ...},   # 可选，负权重 = 反向因子
        "top_n": 50,
        "benchmark_index": "000300.SH"
      },
      "factor_directions": {"factor": "low"},  # 元信息，供展示
      "params": {                  # 回测运行参数
        "start_date": "...", "end_date": "...",
        "rebalance_frequency": "monthly", "initial_capital": 1000000
      }
    }
"""
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REBALANCE_FREQUENCIES = ('daily', 'weekly', 'monthly')
DEFAULT_BENCHMARK = '000300.SH'


class StrategyError(ValueError):
    """策略参数/状态非法（工具层转成用户可读的报错）。"""


def build_strategy_config(
    factor_ids: Optional[List[str]] = None,
    weights: Optional[Dict[str, float]] = None,
    top_n: int = 50,
    benchmark_index: str = DEFAULT_BENCHMARK,
    factor_directions: Optional[Dict[str, str]] = None,
    start_date: str = '',
    end_date: str = '',
    rebalance_frequency: str = 'monthly',
    initial_capital: float = 1000000.0,
    dsl_filter: str = '',
    dsl_order_by: str = '',
    known_factors: Optional[set] = None,
) -> Dict[str, Any]:
    """组装标准策略 config。校验失败抛 StrategyError。

    两种选股方式二选一：
    - 因子加权：factor_ids（可选 weights / factor_directions）
    - DSL 规则：dsl_order_by（必填）+ dsl_filter（可选）；
      known_factors 传入因子注册表 id 集合时做引用校验
    """
    if not 1 <= int(top_n) <= 500:
        raise StrategyError('top_n 需在 1~500 之间')
    if rebalance_frequency not in REBALANCE_FREQUENCIES:
        raise StrategyError(
            f'rebalance_frequency 仅支持 {" / ".join(REBALANCE_FREQUENCIES)}'
        )
    if float(initial_capital) <= 0:
        raise StrategyError('initial_capital 必须大于 0')

    is_dsl = bool(dsl_order_by or dsl_filter)
    if is_dsl and factor_ids:
        raise StrategyError(
            'factor_ids 与 dsl_filter/dsl_order_by 互斥：'
            'DSL 策略不需要 factor_ids/weights'
        )
    if is_dsl and (weights or factor_directions):
        raise StrategyError('DSL 策略不支持 weights / factor_directions')

    if is_dsl:
        from app.services.strategy_dsl import DslError, parse_dsl
        try:
            program = parse_dsl(
                dsl_filter, dsl_order_by,
                known_factors if known_factors is not None
                else _dsl_identifier_names(dsl_filter, dsl_order_by),
            )
        except DslError as exc:
            raise StrategyError(f'DSL 非法: {exc}') from exc
        engine_config: Dict[str, Any] = {
            'selection_method': 'dsl_rule',
            'dsl': {
                'filter': program.filter_text,
                'order_by': program.order_text,
            },
            'factor_list': sorted(program.referenced_factors),
            'top_n': int(top_n),
            'benchmark_index': str(benchmark_index or DEFAULT_BENCHMARK),
        }
        return {
            'engine_config': engine_config,
            'factor_directions': {},
            'params': _build_params(start_date, end_date, rebalance_frequency, initial_capital),
        }

    if not factor_ids:
        raise StrategyError('factor_ids 不能为空（或改用 dsl_order_by 定义规则策略）')

    engine_config = {
        'selection_method': 'factor_based',
        'factor_list': list(factor_ids),
        'top_n': int(top_n),
        'benchmark_index': str(benchmark_index or DEFAULT_BENCHMARK),
    }
    if weights:
        unknown = [fid for fid in weights if fid not in factor_ids]
        if unknown:
            raise StrategyError(
                f'weights 里出现了 factor_ids 之外的因子: {unknown}'
            )
        engine_config['weights'] = {k: float(v) for k, v in weights.items()}

    return {
        'engine_config': engine_config,
        'factor_directions': dict(factor_directions or {}),
        'params': _build_params(start_date, end_date, rebalance_frequency, initial_capital),
    }


def _build_params(start_date, end_date, rebalance_frequency, initial_capital):
    return {
        'start_date': start_date,
        'end_date': end_date,
        'rebalance_frequency': rebalance_frequency,
        'initial_capital': float(initial_capital),
    }


def _factor_registry_ids() -> set:
    """真实因子注册表 id 集合（拿不到注册表时返回空集=跳过校验）。"""
    try:
        from app.services.factor_engine import FactorEngine

        return {f['factor_id'] for f in FactorEngine().get_factor_list()}
    except Exception:  # noqa: BLE001 - 注册表不可用不阻断派生保存
        logger.warning('因子注册表不可用，DSL 新引用因子跳过存在性校验', exc_info=True)
        return set()


def _dsl_identifier_names(filter_text: str, order_by_text: str) -> set:
    """无注册表时提取 DSL 中出现的标识符名，仅做语法级编译校验。"""
    import ast as _ast

    names = set()
    for text in (filter_text or '', order_by_text or ''):
        for node in _ast.walk(_ast.parse(text, mode='eval')):
            if isinstance(node, _ast.Name) and node.id not in ('rank', 'zscore', 'quantile'):
                names.add(node.id)
    return names


class StrategyService:
    def __init__(self, strategy_repo, backtest_repo):
        self.strategy_repo = strategy_repo
        self.backtest_repo = backtest_repo

    # -- 保存/查询 ------------------------------------------------

    def save_strategy(
        self,
        name: str,
        strategy_config: Dict[str, Any],
        description: str = '',
        source_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if 'engine_config' not in strategy_config or 'params' not in strategy_config:
            raise StrategyError(
                'strategy_config 必须由 build_strategy_config 组装'
                '（缺 engine_config / params）'
            )
        return self.strategy_repo.save_strategy(
            name, strategy_config, description, source_session_id
        )

    # -- 版本历史 / 派生编辑 --------------------------------------

    _HISTORY_RUN_METRICS = (
        'total_return', 'annualized_return', 'sharpe_ratio',
        'max_drawdown', 'win_rate', 'total_trades',
    )

    def strategy_history(self, name: str) -> Dict[str, Any]:
        """全部版本 + 该策略的回测 run（含核心指标），供前端版本演进面板。"""
        versions = [
            s for s in self.strategy_repo.list_strategies(include_history=True)
            if s['name'] == name
        ]
        if not versions:
            raise StrategyError(f'未找到策略: {name}')
        versions.sort(key=lambda s: s['version'], reverse=True)

        runs = [
            r for r in self.backtest_repo.list_runs()
            if (r.get('strategy_config') or {}).get('strategy_name') == name
        ]
        runs.sort(key=lambda r: int(r['id']), reverse=True)
        run_rows = []
        for run in runs[:20]:  # 最近 20 条足够覆盖迭代对比
            metrics = (self.backtest_repo.get_result(int(run['id'])) or {}).get(
                'performance_metrics'
            ) or {}
            cfg = run.get('strategy_config') or {}
            run_rows.append({
                'run_id': int(run['id']),
                'strategy_version': cfg.get('strategy_version'),
                'start_date': run.get('start_date'),
                'end_date': run.get('end_date'),
                'status': (run.get('summary') or {}).get('status'),
                'created_at': run.get('created_at'),
                **{m: metrics.get(m) for m in self._HISTORY_RUN_METRICS},
            })
        return {'name': name, 'versions': versions, 'runs': run_rows}

    def save_derived(
        self,
        name: str,
        base_version: int,
        edits: Optional[Dict[str, Any]] = None,
        description: str = '',
    ) -> Dict[str, Any]:
        """以旧版本为底稿派生新版本（前端「编辑」入口，版本不可变原则不变）。

        edits 支持 top_n / weights / factor_directions / dsl_filter /
        dsl_order_by / start_date / end_date / rebalance_frequency /
        initial_capital / benchmark_index。DSL 底稿改因子参数会重新走
        parse_dsl 校验并刷新 factor_list。
        """
        base = self.strategy_repo.get_strategy(name, version=int(base_version))
        if base is None:
            raise StrategyError(f'未找到策略 {name} v{base_version}')
        old = base['strategy_config']
        old_engine = dict(old.get('engine_config') or {})
        old_params = dict(old.get('params') or {})
        edits = dict(edits or {})

        for key in ('start_date', 'end_date', 'rebalance_frequency'):
            if edits.get(key) is not None:
                old_params[key] = edits[key]
        if edits.get('initial_capital') is not None:
            old_params['initial_capital'] = float(edits['initial_capital'])
        top_n = edits.get('top_n', old_engine.get('top_n', 50))
        benchmark = edits.get('benchmark_index', old_engine.get('benchmark_index'))

        meta = dict((old.get('meta') or {}))
        meta['derived_from'] = {'name': name, 'version': int(base_version)}

        if old_engine.get('selection_method') == 'dsl_rule':
            old_dsl = old_engine.get('dsl') or {}
            # 底稿原有因子直接放行，新引用因子对注册表校验
            known = set(old_engine.get('factor_list') or []) | _factor_registry_ids()
            config = build_strategy_config(
                top_n=top_n,
                benchmark_index=benchmark,
                start_date=str(old_params.get('start_date') or ''),
                end_date=str(old_params.get('end_date') or ''),
                rebalance_frequency=str(old_params.get('rebalance_frequency') or 'monthly'),
                initial_capital=float(old_params.get('initial_capital') or 1000000.0),
                dsl_filter=str(edits.get('dsl_filter', old_dsl.get('filter', ''))),
                dsl_order_by=str(edits.get('dsl_order_by', old_dsl.get('order_by', ''))),
                known_factors=known,
            )
        else:
            config = build_strategy_config(
                factor_ids=list(old_engine.get('factor_list') or []),
                weights=edits.get('weights', old_engine.get('weights')),
                top_n=top_n,
                benchmark_index=benchmark,
                factor_directions=edits.get(
                    'factor_directions', old.get('factor_directions')
                ),
                start_date=str(old_params.get('start_date') or ''),
                end_date=str(old_params.get('end_date') or ''),
                rebalance_frequency=str(old_params.get('rebalance_frequency') or 'monthly'),
                initial_capital=float(old_params.get('initial_capital') or 1000000.0),
            )
        config['meta'] = meta
        return self.save_strategy(name, config, description=description)

    # -- 按名回测 -------------------------------------------------

    def run_strategy(
        self,
        name: str,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """取 latest 版本策略 → overrides 覆盖运行参数/引擎参数 → 后台回测。

        overrides 支持 start_date / end_date / top_n / weights /
        rebalance_frequency / initial_capital。返回 run 记录（含 run_id）。
        """
        strategy = self.strategy_repo.get_strategy(name)
        if strategy is None:
            raise StrategyError(f'未找到策略: {name}（可先保存或核对名称）')
        config = strategy['strategy_config']
        engine_config = dict(config.get('engine_config') or {})
        params = dict(config.get('params') or {})
        overrides = dict(overrides or {})

        # 运行参数覆盖
        for key in ('start_date', 'end_date', 'rebalance_frequency', 'initial_capital'):
            if overrides.get(key) is not None:
                params[key] = overrides[key]
        if overrides.get('top_n') is not None:
            engine_config['top_n'] = int(overrides['top_n'])
        if overrides.get('weights') is not None:
            engine_config['weights'] = overrides['weights']

        start_date = str(params.get('start_date') or '')
        end_date = str(params.get('end_date') or '')
        if not start_date or not end_date:
            raise StrategyError(
                '策略缺少 start_date / end_date（保存时未提供，运行时须通过 overrides 传入）'
            )
        if start_date > end_date:
            raise StrategyError(f'start_date({start_date}) 不能晚于 end_date({end_date})')
        rebalance = str(params.get('rebalance_frequency') or 'monthly')
        capital = float(params.get('initial_capital') or 1000000.0)

        # 溯源：结果 run 的 strategy_config 里回写策略名与版本
        engine_config = dict(engine_config)
        engine_config['strategy_name'] = name
        engine_config['strategy_version'] = strategy['version']

        # 与 _tool_run_backtest 同构：建 run 记录 + 后台线程执行
        from app.tasks.backtest_tasks import (
            mark_run_active,
            reap_orphans_once,
            run_backtest_task,
        )
        try:
            reap_orphans_once()
        except Exception:  # noqa: BLE001 - 清理失败不阻断提交
            logger.warning('清理孤儿回测 run 失败', exc_info=True)

        run = self.backtest_repo.create_run(
            strategy_config=engine_config,
            start_date=start_date,
            end_date=end_date,
            initial_capital=capital,
            rebalance_frequency=rebalance,
        )
        run_id = int(run['id'])
        self.backtest_repo.update_summary(run_id, {'status': 'queued'})
        mark_run_active(run_id)
        threading.Thread(
            target=run_backtest_task,
            args=(run_id, engine_config, start_date, end_date, capital, rebalance),
            name=f'strategy-backtest-{run_id}',
            daemon=True,
        ).start()
        return {
            'run_id': run_id,
            'status': 'queued',
            'strategy_name': name,
            'strategy_version': strategy['version'],
            'strategy_config': engine_config,
            'start_date': start_date,
            'end_date': end_date,
            'rebalance_frequency': rebalance,
            'initial_capital': capital,
        }

    # -- 多 run 对比 ----------------------------------------------

    _COMPARE_METRICS = (
        'total_return', 'annualized_return', 'sharpe_ratio',
        'max_drawdown', 'win_rate', 'calmar_ratio', 'total_trades',
        'alpha', 'beta', 'information_ratio',
    )

    def compare_runs(self, run_ids: List[int]) -> Dict[str, Any]:
        """并排多个回测 run 的核心指标；区间不一致自动标 ⚠️（不可比）。"""
        run_ids = [int(r) for r in (run_ids or [])]
        if not 2 <= len(run_ids) <= 6:
            raise StrategyError('compare 需要提供 2~6 个 run_id')
        rows: List[Dict[str, Any]] = []
        missing: List[int] = []
        for run_id in run_ids:
            run = self.backtest_repo.get_run(run_id)
            result = self.backtest_repo.get_result(run_id)
            if run is None:
                missing.append(run_id)
                continue
            metrics = (result or {}).get('performance_metrics') or {}
            rows.append({
                'run_id': run_id,
                'strategy_name': (run.get('strategy_config') or {}).get('strategy_name'),
                'factor_list': (run.get('strategy_config') or {}).get('factor_list'),
                'start_date': run.get('start_date'),
                'end_date': run.get('end_date'),
                'status': (run.get('summary') or {}).get('status'),
                **{m: metrics.get(m) for m in self._COMPARE_METRICS},
            })
        if missing:
            raise StrategyError(f'未找到回测记录: {missing}')

        ranges = {(r['start_date'], r['end_date']) for r in rows}
        warning = None
        if len(ranges) > 1:
            warning = (
                '各 run 回测区间不一致，收益/风险指标不可直接对比；'
                '迭代调参对比请保持相同 start_date / end_date'
            )
        pending = [r['run_id'] for r in rows if r['status'] not in ('succeeded',)]
        if pending:
            warning = (warning + '；' if warning else '') + (
                f'以下 run 尚未完成（{pending}），其指标为空，建议等待后重新对比'
            )
        return {'runs': rows, 'range_warning': warning}
