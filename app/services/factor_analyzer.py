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

    def _merge_factor_with_forward_return(self, factor_ids: List[str],
                                          start_date: Optional[str],
                                          end_date: Optional[str],
                                          forward_period: int) -> pd.DataFrame:
        """因子值关联未来 N 日收益（按各自交易日序列 shift）。

        行情终点向后外推足够多的自然日，保证区间尾部的因子值也能取到
        完整的未来收益；取不到未来收益的日期在后续统计中被剔除。
        """
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
