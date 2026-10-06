"""因子分析层：IC/IR、分层回测、因子相关性。

只依赖两类存量数据，不做任何在线因子计算：
- factor_values（FactorRepository）：因子历史值
- 后复权行情（ParquetDataReader.get_return_prices）：构造未来收益

核心口径：
- IC：单日截面上因子值与未来 N 日收益的 Spearman 秩相关；
  IC > 0 表示因子值越高未来收益越高
- ICIR = IC 均值 / IC 标准差，衡量预测力的稳定性
- 分层：每个交易日按因子值把股票分成 N 组，统计各组未来 N 日
  平均收益；有效因子应呈现单调分层，多空价差 = 最高组 - 最低组
- 因子相关性：因子间截面秩相关按日平均，用于识别冗余因子
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats

from app.services.data_reader import ParquetDataReader
from app.services.parquet_state_store import FactorRepository, ParquetStateStore

TRADING_DAYS_PER_YEAR = 252


class FactorAnalyzer:
    """因子分析引擎（IC/分层/相关性）"""

    def __init__(self, factor_repo: FactorRepository = None,
                 data_reader: ParquetDataReader = None):
        self.factor_repo = factor_repo or FactorRepository(ParquetStateStore())
        self.data_reader = data_reader or ParquetDataReader()

    # ------------------------------------------------------------------
    # IC / ICIR
    # ------------------------------------------------------------------

    def ic_analysis(self, factor_id: str, start_date: str = None,
                    end_date: str = None, forward_period: int = 1,
                    min_stocks: int = 10) -> Dict[str, Any]:
        """因子 IC 序列与 ICIR 汇总。

        forward_period: 未来收益的持有期（按股票自身的交易日计）。
        因子值在 t 日收盘后可得、未来收益从 t 收盘起算，无前视。
        """
        forward_period = max(1, int(forward_period))
        merged = self._merge_factor_with_forward_return(
            factor_ids=[factor_id], start_date=start_date,
            end_date=end_date, forward_period=forward_period,
        )
        if merged.empty:
            return self._empty_ic_result(factor_id, forward_period,
                                         '未找到因子值或对应行情')

        ic_records: List[Dict[str, Any]] = []
        for trade_date, group in merged.groupby('trade_date'):
            valid = group.dropna(subset=['factor_value', 'forward_return'])
            if len(valid) < min_stocks:
                continue
            ic = float(stats.spearmanr(
                valid['factor_value'], valid['forward_return']
            ).statistic)
            if np.isnan(ic):
                continue
            ic_records.append({
                'date': trade_date.strftime('%Y-%m-%d'),
                'ic': ic,
                'n_stocks': int(len(valid)),
            })

        if not ic_records:
            result = self._empty_ic_result(factor_id, forward_period,
                                           '有效交易日不足（截面股票数过少或缺失未来收益）')
            result['min_stocks'] = min_stocks
            return result

        ics = np.array([record['ic'] for record in ic_records], dtype=float)
        ic_mean = float(ics.mean())
        ic_std = float(ics.std(ddof=1)) if len(ics) > 1 else 0.0
        icir = ic_mean / ic_std if ic_std > 0 else 0.0
        t_stat = (
            ic_mean / ic_std * np.sqrt(len(ics))
            if ic_std > 0 and len(ics) > 1 else 0.0
        )

        return {
            'factor_id': factor_id,
            'forward_period': forward_period,
            'summary': {
                'ic_mean': ic_mean,
                'ic_std': ic_std,
                'ic_ir': icir,
                'ic_positive_ratio': float((ics > 0).mean()),
                't_stat': float(t_stat),
                'n_dates': int(len(ics)),
            },
            'ic_series': ic_records,
        }

    # ------------------------------------------------------------------
    # 分层回测
    # ------------------------------------------------------------------

    def quantile_analysis(self, factor_id: str, start_date: str = None,
                          end_date: str = None, forward_period: int = 1,
                          n_quantiles: int = 5, min_stocks: int = 10) -> Dict[str, Any]:
        """按因子值分层的未来收益分析。

        每个交易日把股票按因子值升序分成 n_quantiles 组（第 1 组因子值
        最低），统计各组未来收益的截面均值再按日平均。多空价差为
        最高组 - 最低组，按 252/period 折算年化。
        """
        n_quantiles = max(2, int(n_quantiles))
        forward_period = max(1, int(forward_period))
        merged = self._merge_factor_with_forward_return(
            factor_ids=[factor_id], start_date=start_date,
            end_date=end_date, forward_period=forward_period,
        )
        if merged.empty:
            return {'error': '未找到因子值或对应行情', 'factor_id': factor_id}

        quantile_returns: Dict[int, List[float]] = {
            q: [] for q in range(1, n_quantiles + 1)
        }
        quantile_sizes: Dict[int, List[int]] = {
            q: [] for q in range(1, n_quantiles + 1)
        }
        spreads: List[float] = []
        n_dates = 0

        for _, group in merged.groupby('trade_date'):
            valid = group.dropna(subset=['factor_value', 'forward_return'])
            if len(valid) < min_stocks:
                continue
            n_dates += 1

            # 用百分位秩分桶：NaN 值已剔除；桶 1 = 因子值最低
            pct_rank = valid['factor_value'].rank(pct=True, method='average')
            bucket = np.minimum(
                (pct_rank * n_quantiles).apply(np.ceil).astype(int),
                n_quantiles,
            )
            date_mean = valid.assign(_bucket=bucket).groupby('_bucket')[
                'forward_return'
            ].agg(['mean', 'size'])

            for q in range(1, n_quantiles + 1):
                if q in date_mean.index:
                    quantile_returns[q].append(float(date_mean.loc[q, 'mean']))
                    quantile_sizes[q].append(int(date_mean.loc[q, 'size']))
            if 1 in date_mean.index and n_quantiles in date_mean.index:
                spreads.append(
                    float(date_mean.loc[n_quantiles, 'mean'])
                    - float(date_mean.loc[1, 'mean'])
                )

        if n_dates == 0:
            return {'error': '有效交易日不足', 'factor_id': factor_id,
                    'min_stocks': min_stocks}

        annualize_factor = TRADING_DAYS_PER_YEAR / forward_period
        quantiles = []
        for q in range(1, n_quantiles + 1):
            means = quantile_returns[q]
            quantiles.append({
                'quantile': q,
                'mean_forward_return': float(np.mean(means)) if means else None,
                'annualized_return': (
                    float(np.mean(means)) * annualize_factor if means else None
                ),
                'avg_stocks': (
                    float(np.mean(quantile_sizes[q])) if quantile_sizes[q] else 0.0
                ),
            })

        return {
            'factor_id': factor_id,
            'forward_period': forward_period,
            'n_quantiles': n_quantiles,
            'n_dates': n_dates,
            'quantiles': quantiles,
            'long_short_spread': (
                float(np.mean(spreads)) if spreads else None
            ),
            'long_short_spread_annualized': (
                float(np.mean(spreads)) * annualize_factor if spreads else None
            ),
        }

    # ------------------------------------------------------------------
    # 分位组合净值回测
    # ------------------------------------------------------------------

    def quantile_portfolio_backtest(self, factor_id: str, start_date: str = None,
                                    end_date: str = None, holding_days: int = 20,
                                    n_quantiles: int = 5, cost_bps: float = 0.0,
                                    min_stocks: int = 50,
                                    cost_bps_list: List[float] = None
                                    ) -> Dict[str, Any]:
        """分位组合净值回测：非重叠调仓的分组净值 + 多空（GN−G1）曲线。

        与 quantile_analysis（单日截面均值统计）互补，这里回答组合层问题：
        因子分组收益按真实调仓流程复利后净值如何、换手多高、扣费后还剩多少。

        口径：
        - 调仓：信号日 t 收盘取因子截面分桶（第 1 组因子值最低），
          t+1 收盘成交，持有 holding_days 个交易日至下一个执行日；
        - 无前视：因子值在 t 收盘后可得，成交在 t+1；
        - 非重叠：信号日按 holding_days 间隔取，末个信号日因无完整
          持有期而剔除（n_periods 为完整期数）；
        - 成本：cost_bps 为单边费率，每次调仓按单边换手率扣双边费用
          （全换手 = 2×cost_bps）；
        - 换手率 = 1 − 与上期成员交集占比（等权满员口径）。
        """
        n_quantiles = max(2, int(n_quantiles))
        holding_days = max(1, int(holding_days))
        cost_bps = max(0.0, float(cost_bps))
        min_stocks = max(2 * n_quantiles, int(min_stocks))

        # 未指定区间时默认最近两年（防全库扫描 OOM，见 _bounded_date_range）
        bounds = self._bounded_date_range(start_date, end_date)
        if bounds is None:
            return {'error': '因子库为空', 'factor_id': factor_id}
        start_date, end_date = bounds

        factor_df = self.factor_repo.get_values(
            factor_ids=[factor_id], start_date=start_date, end_date=end_date,
        )
        if factor_df.empty:
            return {'error': '未找到因子值', 'factor_id': factor_id}
        factor_df = factor_df[['ts_code', 'trade_date', 'factor_value']].dropna(
            subset=['factor_value']
        ).copy()
        factor_df['trade_date'] = pd.to_datetime(
            factor_df['trade_date'], errors='coerce', format='mixed'
        ).dropna()
        if factor_df.empty:
            return {'error': '因子值日期无效', 'factor_id': factor_id}

        factor_wide = factor_df.pivot_table(
            index='trade_date', columns='ts_code', values='factor_value',
            aggfunc='first',
        ).sort_index()

        # 行情面板：从首个信号日到区间末 + 持有期缓冲，只需 close
        all_dates = factor_wide.index
        price_start = all_dates[0].strftime('%Y-%m-%d')
        price_end = (all_dates[-1] + pd.Timedelta(
            days=holding_days * 3 + 10
        )).strftime('%Y-%m-%d')
        try:
            prices = self.data_reader.get_return_prices(
                start_date=price_start, end_date=price_end,
            )
        except Exception as e:
            logger.error(f"分位组合回测读取行情失败: {e}")
            return {'error': f'读取行情失败: {e}', 'factor_id': factor_id}
        if prices.empty:
            return {'error': '未找到行情数据', 'factor_id': factor_id}
        close_wide = prices.pivot_table(
            index=pd.to_datetime(prices['trade_date'], format='mixed'),
            columns='ts_code', values='close', aggfunc='first',
        ).sort_index()
        if close_wide.empty:
            return {'error': '行情面板为空', 'factor_id': factor_id}

        # 信号日 = 因子面板交易日按 holding_days 等间隔抽取
        signal_dates = list(all_dates[::holding_days])

        # 执行日 = 信号日的下一个交易日（行情面板口径）
        price_dates = close_wide.index
        exec_of = {}
        for t in signal_dates:
            later = price_dates[price_dates > t]
            if len(later) == 0:
                continue
            exec_of[t] = later[0]

        # 末个信号日无完整持有期，剔除：需要存在下一个信号日的执行日
        usable = [t for t in signal_dates if t in exec_of]
        periods = []
        for i, t in enumerate(usable):
            if i + 1 >= len(usable) or usable[i + 1] not in exec_of:
                continue
            periods.append((t, exec_of[t], exec_of[usable[i + 1]]))

        if not periods:
            return {'error': '区间内无完整持有期，请扩大日期范围或缩短持有期',
                    'factor_id': factor_id}

        period_records: List[Dict[str, Any]] = []
        prev_members: Dict[int, set] = {}
        group_returns: Dict[int, List[float]] = {q: [] for q in range(1, n_quantiles + 1)}
        # 毛收益与换手按腿分开记录，成本敏感性与分年拆解在此之上重算
        gross_returns: Dict[int, List[float]] = {q: [] for q in range(1, n_quantiles + 1)}
        turnover_records: Dict[int, List[float]] = {q: [] for q in range(1, n_quantiles + 1)}
        exec_years: List[int] = []
        ls_returns: List[float] = []
        ls_gross: List[float] = []
        ls_turnover: List[float] = []

        for t, exec_d, next_exec in periods:
            cross = factor_wide.loc[t].dropna()
            if len(cross) < min_stocks:
                continue
            pct_rank = cross.rank(pct=True, method='average')
            bucket = np.minimum(
                (pct_rank * n_quantiles).apply(np.ceil).astype(int), n_quantiles,
            )
            members = {
                q: set(bucket.index[bucket == q]) for q in range(1, n_quantiles + 1)
            }

            # 个股期间收益：执行日收盘 → 下个执行日收盘；两端缺价则剔除
            entry = close_wide.loc[exec_d]
            exit_ = close_wide.loc[next_exec]
            period_ret: Dict[str, float] = {}
            for code in cross.index:
                p0, p1 = entry.get(code), exit_.get(code)
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    period_ret[code] = float(p1) / float(p0) - 1.0

            row: Dict[str, Any] = {
                'signal_date': t.strftime('%Y-%m-%d'),
                'exec_date': exec_d.strftime('%Y-%m-%d'),
                'next_exec_date': next_exec.strftime('%Y-%m-%d'),
            }
            costs = {}
            for q in range(1, n_quantiles + 1):
                codes = [c for c in members[q] if c in period_ret]
                if not codes:
                    row[f'g{q}_return'] = None
                    costs[q] = 0.0
                    gross_returns[q].append(np.nan)
                    turnover_records[q].append(np.nan)
                    continue
                gross = float(np.mean([period_ret[c] for c in codes]))
                if q in prev_members and prev_members[q]:
                    overlap = len(prev_members[q] & set(codes)) / len(codes)
                    turnover = 1.0 - overlap
                else:
                    turnover = 1.0  # 建仓满换手
                cost = turnover * 2.0 * cost_bps * 1e-4
                row[f'g{q}_return'] = gross - cost
                row[f'g{q}_turnover'] = turnover
                costs[q] = cost
                group_returns[q].append(gross - cost)
                gross_returns[q].append(gross)
                turnover_records[q].append(turnover)
            prev_members = members

            r_hi, r_lo = row.get(f'g{n_quantiles}_return'), row.get('g1_return')
            if r_hi is not None and r_lo is not None:
                row['long_short_return'] = r_hi - r_lo
                ls_returns.append(r_hi - r_lo)
                ls_gross.append(
                    gross_returns[n_quantiles][-1] - gross_returns[1][-1])
                ls_turnover.append(
                    turnover_records[n_quantiles][-1]
                    + turnover_records[1][-1])
            period_records.append(row)
            exec_years.append(exec_d.year)

        if not period_records or not ls_returns:
            return {'error': '有效调仓期不足（截面股票数过少）', 'factor_id': factor_id,
                    'min_stocks': min_stocks}

        def _nav_series(returns: List[float]) -> List[float]:
            nav, cur = [], 1.0
            for r in returns:
                cur *= 1.0 + r
                nav.append(round(cur, 6))
            return nav

        periods_per_year = TRADING_DAYS_PER_YEAR / holding_days
        groups_summary = {}
        for q in range(1, n_quantiles + 1):
            groups_summary[f'g{q}'] = self._period_perf_summary(
                group_returns[q], periods_per_year,
            )
        ls_summary = self._period_perf_summary(ls_returns, periods_per_year)

        # 成本敏感性：净多空 = 毛多空 − 2×cost×(高组换手 + 低组换手)，逐期重算
        cost_grid = [c for c in (cost_bps_list or [])]
        if cost_bps not in cost_grid:
            cost_grid.append(cost_bps)
        ls_gross_arr = np.array(ls_gross, dtype=float)
        ls_turn_arr = np.array(ls_turnover, dtype=float)
        cost_sensitivity = {}
        for cost in sorted(set(float(c) for c in cost_grid)):
            if cost < 0:
                continue
            net = ls_gross_arr - 2.0 * cost * 1e-4 * ls_turn_arr
            summary = self._period_perf_summary(list(net), periods_per_year)
            cost_sensitivity[f'{float(cost):g}'] = summary

        # 分年拆解：按执行日年份分组统计多空（基准费率口径）
        yearly_breakdown = {}
        for year in sorted(set(exec_years)):
            idx = [i for i, y in enumerate(exec_years) if y == year]
            yearly_breakdown[str(year)] = {
                'long_short': self._period_perf_summary(
                    [ls_returns[i] for i in idx], periods_per_year),
                'n_periods': len(idx),
            }

        return {
            'factor_id': factor_id,
            'holding_days': holding_days,
            'n_quantiles': n_quantiles,
            'cost_bps': cost_bps,
            'n_periods': len(period_records),
            'first_signal_date': period_records[0]['signal_date'],
            'last_signal_date': period_records[-1]['signal_date'],
            'periods': period_records,
            'nav': {
                f'g{q}': _nav_series(group_returns[q])
                for q in range(1, n_quantiles + 1)
            },
            'nav_long_short': _nav_series(ls_returns),
            'groups_summary': groups_summary,
            'long_short_summary': ls_summary,
            'cost_sensitivity': cost_sensitivity,
            'yearly_breakdown': yearly_breakdown,
            'avg_turnover': {
                f'g{q}': float(np.mean([
                    p[f'g{q}_turnover'] for p in period_records
                    if p.get(f'g{q}_turnover') is not None
                ])) if any(p.get(f'g{q}_turnover') is not None
                           for p in period_records) else None
                for q in range(1, n_quantiles + 1)
            },
        }

    @staticmethod
    def _period_perf_summary(period_returns: List[float],
                             periods_per_year: float) -> Dict[str, Any]:
        """按期收益序列的常用绩效指标（净值口径，非截面均值口径）。"""
        rets = np.array(period_returns, dtype=float)
        nav = np.cumprod(1.0 + rets)
        total_return = float(nav[-1] - 1.0) if len(nav) else 0.0
        n = len(rets)
        mean, std = float(rets.mean()), float(rets.std(ddof=1)) if n > 1 else 0.0
        annualized_return = float(np.expm1(mean * periods_per_year)) if n else 0.0
        annualized_vol = std * np.sqrt(periods_per_year) if n > 1 else 0.0
        sharpe = mean / std * np.sqrt(periods_per_year) if std > 0 else 0.0
        t_stat = mean / std * np.sqrt(n) if std > 0 and n > 1 else 0.0
        peak = np.maximum.accumulate(nav)
        drawdown = nav / peak - 1.0
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'annualized_vol': float(annualized_vol),
            'sharpe': float(sharpe),
            't_stat': float(t_stat),
            'max_drawdown': float(drawdown.min()) if n else 0.0,
            'win_rate': float((rets > 0).mean()) if n else 0.0,
            'n_periods': int(n),
        }

    # ------------------------------------------------------------------
    # IC 衰减 / 滚动 IC / 分年稳定性
    # ------------------------------------------------------------------

    def ic_decay_analysis(self, factor_id: str, start_date: str = None,
                          end_date: str = None,
                          forward_periods: List[int] = None,
                          rolling_window: int = 20,
                          min_stocks: int = 10) -> Dict[str, Any]:
        """IC vs 前向天数衰减曲线 + 滚动 IC 时序 + 分年稳定性。

        - ic_by_horizon: 每个前向期的逐日 IC 汇总（均值/ICIR/t 值/正率），
          半衰期按 ic(h) = ic0·exp(−k·h) 拟合，直接决定合理持有期；
        - rolling_ic: 基准前向期（列表首个）的滚动窗口均值 IC 序列；
        - yearly_ic: 年份 × 前向期的平均 IC 矩阵，看稳定性。
        """
        forward_periods = sorted({max(1, int(p)) for p in
                                  (forward_periods or [1, 5, 10, 20])})
        rolling_window = max(2, int(rolling_window))

        bounds = self._bounded_date_range(start_date, end_date)
        if bounds is None:
            return {'error': '因子库为空', 'factor_id': factor_id}
        start_date, end_date = bounds

        factor_df = self.factor_repo.get_values(
            factor_ids=[factor_id], start_date=start_date, end_date=end_date,
        )
        if factor_df.empty:
            return {'error': '未找到因子值', 'factor_id': factor_id}
        factor_df = factor_df[['ts_code', 'trade_date', 'factor_value']].dropna(
            subset=['factor_value']
        )
        factor_df['trade_date'] = pd.to_datetime(
            factor_df['trade_date'], errors='coerce', format='mixed')
        factor_df = factor_df.dropna(subset=['trade_date'])
        if factor_df.empty:
            return {'error': '因子值日期无效', 'factor_id': factor_id}
        factor_wide = factor_df.pivot_table(
            index='trade_date', columns='ts_code', values='factor_value',
            aggfunc='first',
        ).sort_index()

        max_h = max(forward_periods)
        price_end = (factor_wide.index[-1]
                     + pd.Timedelta(days=max_h * 3 + 7)).strftime('%Y-%m-%d')
        try:
            prices = self.data_reader.get_return_prices(
                start_date=factor_wide.index[0].strftime('%Y-%m-%d'),
                end_date=price_end,
            )
        except Exception as e:
            logger.error(f"IC 衰减分析读取行情失败: {e}")
            return {'error': f'读取行情失败: {e}', 'factor_id': factor_id}
        if prices.empty:
            return {'error': '未找到行情数据', 'factor_id': factor_id}
        close_wide = prices.pivot_table(
            index=pd.to_datetime(prices['trade_date'], format='mixed'),
            columns='ts_code', values='close', aggfunc='first',
        ).sort_index()

        # 按行情交易日对齐因子截面，避免停牌导致的错位
        factor_wide = factor_wide.reindex(close_wide.index)

        ic_by_horizon: Dict[int, Dict[str, Any]] = {}
        ic_series_by_horizon: Dict[int, List[Dict[str, Any]]] = {}
        yearly_sums: Dict[int, Dict[int, List[float]]] = {
            h: {} for h in forward_periods}

        for h in forward_periods:
            fwd = close_wide.shift(-h) / close_wide - 1.0
            records: List[Dict[str, Any]] = []
            for date, fac in factor_wide.iterrows():
                valid = pd.DataFrame({
                    'f': fac, 'r': fwd.loc[date],
                }).dropna()
                if len(valid) < min_stocks:
                    continue
                ic = float(stats.spearmanr(valid['f'], valid['r']).statistic)
                if np.isnan(ic):
                    continue
                records.append({
                    'date': date.strftime('%Y-%m-%d'), 'ic': ic,
                })
                yearly_sums[h].setdefault(date.year, []).append(ic)
            if not records:
                ic_by_horizon[h] = {'error': '有效交易日不足'}
                ic_series_by_horizon[h] = []
                continue
            ics = np.array([r['ic'] for r in records], dtype=float)
            ic_mean = float(ics.mean())
            ic_std = float(ics.std(ddof=1)) if len(ics) > 1 else 0.0
            ic_by_horizon[h] = {
                'ic_mean': ic_mean,
                'ic_std': ic_std,
                'ic_ir': ic_mean / ic_std if ic_std > 0 else 0.0,
                'ic_positive_ratio': float((ics > 0).mean()),
                't_stat': (ic_mean / ic_std * np.sqrt(len(ics))
                           if ic_std > 0 else 0.0),
                'n_dates': int(len(ics)),
            }
            ic_series_by_horizon[h] = records

        # 半衰期：ic(h) = ic0·exp(−k·h)，取均值序列拟合（需 ≥3 个有效点）
        half_life = None
        valid_points = [(h, ic_by_horizon[h]['ic_mean'])
                        for h in forward_periods
                        if 'ic_mean' in ic_by_horizon[h]]
        if len(valid_points) >= 3:
            hs = np.array([p[0] for p in valid_points], dtype=float)
            ys = np.array([abs(p[1]) for p in valid_points], dtype=float)
            if (ys > 0).all():
                k, _ = np.polyfit(hs, np.log(ys), 1)
                k = -k
                if k > 1e-6:
                    half_life = float(np.log(2) / k)

        base_h = forward_periods[0]
        rolling_ic = []
        base_records = ic_series_by_horizon.get(base_h, [])
        if len(base_records) >= rolling_window:
            values = [r['ic'] for r in base_records]
            rolling = pd.Series(values).rolling(rolling_window).mean()
            for r, m in zip(base_records, rolling):
                if pd.notna(m):
                    rolling_ic.append({'date': r['date'], 'rolling_ic':
                                       round(float(m), 6)})

        yearly_ic = {
            str(year): {str(h): (
                float(np.mean(yearly_sums[h][year]))
                if yearly_sums[h].get(year) else None)
                for h in forward_periods}
            for year in sorted({y for h in forward_periods
                                for y in yearly_sums[h]})
        }

        return {
            'factor_id': factor_id,
            'forward_periods': forward_periods,
            'rolling_window': rolling_window,
            'ic_by_horizon': {str(h): v for h, v in ic_by_horizon.items()},
            'ic_half_life_days': half_life,
            'rolling_ic': rolling_ic,
            'yearly_ic': yearly_ic,
        }

    # ------------------------------------------------------------------
    # 因子相关性
    # ------------------------------------------------------------------

    def correlation_matrix(self, factor_ids: List[str], start_date: str = None,
                           end_date: str = None, trade_date: str = None,
                           min_stocks: int = 10) -> Dict[str, Any]:
        """因子间截面秩相关矩阵（多日平均）。

        用于识别冗余因子：|相关| 持续接近 1 的因子可二选一。
        """
        factor_ids = [f for f in (factor_ids or []) if f]
        if len(factor_ids) < 2:
            return {'error': '相关性分析至少需要两个因子'}

        if trade_date is None:
            # 未指定区间时默认最近两年（防全库扫描 OOM）
            bounds = self._bounded_date_range(start_date, end_date)
            if bounds is None:
                return {'error': '因子库为空', 'factor_ids': factor_ids}
            start_date, end_date = bounds
        df = self.factor_repo.get_values(
            factor_ids=factor_ids, start_date=start_date,
            end_date=end_date, trade_date=trade_date,
        )
        if df.empty:
            return {'error': '未找到因子值', 'factor_ids': factor_ids}

        df = df[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna(
            subset=['factor_value']
        )
        wide = df.pivot_table(
            index=['trade_date', 'ts_code'], columns='factor_id',
            values='factor_value', aggfunc='first',
        )
        wide = wide.reindex(columns=factor_ids)

        corr_sum = pd.DataFrame(
            0.0, index=factor_ids, columns=factor_ids, dtype=float
        )
        corr_count = pd.DataFrame(
            0, index=factor_ids, columns=factor_ids, dtype=int
        )
        n_dates = 0

        for _, day_frame in wide.groupby(level='trade_date'):
            day_frame = day_frame.droplevel('trade_date').dropna(axis=0, how='all')
            # 至少 min_stocks 只股票同时有两个以上因子的日期才计入
            day_frame = day_frame.dropna(axis=0, thresh=2)
            if len(day_frame) < min_stocks:
                continue
            day_corr = day_frame.corr(method='spearman', min_periods=min_stocks)
            n_dates += 1
            for left in factor_ids:
                for right in factor_ids:
                    value = day_corr.loc[left, right]
                    if pd.notna(value):
                        corr_sum.loc[left, right] += float(value)
                        corr_count.loc[left, right] += 1

        if n_dates == 0:
            return {'error': '有效交易日不足', 'factor_ids': factor_ids,
                    'min_stocks': min_stocks}

        matrix = {}
        for left in factor_ids:
            matrix[left] = {
                right: (
                    corr_sum.loc[left, right] / corr_count.loc[left, right]
                    if corr_count.loc[left, right] > 0 else None
                )
                for right in factor_ids
            }

        return {
            'factor_ids': factor_ids,
            'n_dates': n_dates,
            'matrix': matrix,
        }

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _bounded_date_range(self, start_date: Optional[str],
                            end_date: Optional[str]) -> Optional[tuple]:
        """未指定区间时默认最近两年。

        get_values 按分区整读后过滤，不设边界会拼接全历史分区
        （数百个 × 百万行/分区）打爆内存。因子库为空时返回 None。
        """
        if start_date and end_date:
            return start_date, end_date
        store = getattr(self.factor_repo, 'store', None)
        list_partitions = getattr(store, 'list_partitions', None)
        if list_partitions is None:
            # 测试替身等无 store 的仓库：无法推断边界，维持原语义
            return start_date, end_date
        partitions = sorted(
            list_partitions(self.factor_repo.TABLE_VALUES, "trade_date"))
        if not partitions:
            return None
        end_date = end_date or partitions[-1]
        if not start_date:
            start_date = (
                pd.Timestamp(end_date) - pd.DateOffset(years=2)
            ).strftime('%Y-%m-%d')
        return start_date, end_date

    def _merge_factor_with_forward_return(self, factor_ids: List[str],
                                          start_date: Optional[str],
                                          end_date: Optional[str],
                                          forward_period: int) -> pd.DataFrame:
        """因子值关联未来 N 日收益（按各自交易日序列 shift）。

        行情终点向后外推足够多的自然日，保证区间尾部的因子值也能取到
        完整的未来收益；取不到未来收益的日期在后续统计中被剔除。
        """
        # 未指定区间时默认最近两年（防全库扫描 OOM，见 _bounded_date_range）
        bounds = self._bounded_date_range(start_date, end_date)
        if bounds is None:
            return pd.DataFrame()
        start_date, end_date = bounds
        factor_df = self.factor_repo.get_values(
            factor_ids=factor_ids, start_date=start_date, end_date=end_date,
        )
        if factor_df.empty:
            return pd.DataFrame()
        factor_df = factor_df[['ts_code', 'trade_date', 'factor_value']].copy()
        factor_df['trade_date'] = pd.to_datetime(
            factor_df['trade_date'], errors='coerce', format='mixed'
        )
        factor_df = factor_df.dropna(subset=['trade_date'])
        if factor_df.empty:
            return pd.DataFrame()

        last_date = factor_df['trade_date'].max()
        # 外推约 3 倍持有期的自然日 + 一周缓冲，覆盖节假期
        price_end = last_date + pd.Timedelta(days=forward_period * 3 + 7)
        try:
            prices = self.data_reader.get_return_prices(
                start_date=factor_df['trade_date'].min().strftime('%Y-%m-%d'),
                end_date=price_end.strftime('%Y-%m-%d'),
            )
        except Exception as e:
            logger.error(f"因子分析读取行情失败: {e}")
            return pd.DataFrame()
        if prices.empty:
            return pd.DataFrame()

        prices = prices[['ts_code', 'trade_date', 'close']].copy()
        prices['trade_date'] = pd.to_datetime(
            prices['trade_date'], errors='coerce', format='mixed'
        )
        prices = prices.sort_values(['ts_code', 'trade_date'])
        prices['forward_return'] = (
            prices.groupby('ts_code')['close'].shift(-forward_period)
            / prices['close']
            - 1.0
        )

        return factor_df.merge(
            prices[['ts_code', 'trade_date', 'forward_return']],
            on=['ts_code', 'trade_date'], how='inner',
        )

    @staticmethod
    def _empty_ic_result(factor_id: str, forward_period: int,
                         message: str) -> Dict[str, Any]:
        return {
            'factor_id': factor_id,
            'forward_period': forward_period,
            'summary': {
                'ic_mean': None, 'ic_std': None, 'ic_ir': None,
                'ic_positive_ratio': None, 't_stat': None, 'n_dates': 0,
            },
            'ic_series': [],
            'message': message,
        }
