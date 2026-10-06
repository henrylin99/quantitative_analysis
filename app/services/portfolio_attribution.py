"""组合因子暴露归因：组合收益回归到因子收益率（风格画像）。

口径：
- 因子收益率：每个交易日截面上，个股收益对标准化因子值的 OLS 回归
  系数（Fama-MacBeth 式逐日回归）；
- 组合收益：持仓权重 × 个股收益的加权和（权重按 weight/target_weight
  归一，缺省等权）；
- 归因：组合日收益序列对因子收益率序列的多元 OLS 回归，beta × 因子
  收益均值 = 该风格对组合收益的年均贡献，配 t 统计量；
- 当前暴露：最新截面持仓股票的因子值加权平均（z-score 口径）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from app.services.data_reader import ParquetDataReader
from app.services.parquet_state_store import (
    FactorRepository, ParquetStateStore, PortfolioRepository,
)


class PortfolioAttributionService:
    """组合收益的因子风格归因"""

    def __init__(self, portfolio_repo: PortfolioRepository = None,
                 factor_repo: FactorRepository = None,
                 data_reader: ParquetDataReader = None,
                 store: ParquetStateStore = None):
        self.store = store or ParquetStateStore()
        self.portfolio_repo = portfolio_repo or PortfolioRepository(self.store)
        self.factor_repo = factor_repo or FactorRepository(self.store)
        self.data_reader = data_reader or ParquetDataReader()

    def attribute(self, portfolio_id: str, factor_ids: List[str] = None,
                  start_date: str = None, end_date: str = None,
                  max_factors: int = 10,
                  min_stocks: int = 30) -> Dict[str, Any]:
        positions = self.portfolio_repo.list_positions(portfolio_id)
        if not positions:
            return {'error': f'组合 {portfolio_id} 无有效持仓'}

        weights = self._position_weights(positions)
        codes = list(weights.index)

        if not start_date or not end_date:
            factor_store = getattr(self.factor_repo, 'store', None) or self.store
            partitions = sorted(factor_store.list_partitions(
                self.factor_repo.TABLE_VALUES, "trade_date"))
            if not partitions:
                return {'error': '因子库为空'}
            end_date = end_date or partitions[-1]
            start_date = start_date or (
                pd.Timestamp(end_date) - pd.DateOffset(years=1)
            ).strftime('%Y-%m-%d')

        factor_ids = [f for f in (factor_ids or []) if f]
        if not factor_ids:
            # 默认用体检 accepted 白名单，否则全因子覆盖数前 N
            try:
                from app.services.factor_screening import FactorScreeningService
                factor_ids = FactorScreeningService(
                    store=self.store, factor_repo=self.factor_repo,
                ).accepted_factors()
            except Exception:
                factor_ids = []
            if not factor_ids:
                factor_ids = self._top_coverage_factors(
                    start_date, end_date, max_factors)
        factor_ids = factor_ids[:max_factors]
        if not factor_ids:
            return {'error': '无可用因子'}

        # 因子截面取全市场（不能只取持仓）：截面标准化与逐日
        # Fama-MacBeth 回归都需要完整截面
        factor_df = self.factor_repo.get_values(
            factor_ids=factor_ids, start_date=start_date,
            end_date=end_date,
        )
        if factor_df.empty:
            return {'error': '持仓区间内无因子数据'}
        factor_df['trade_date'] = factor_df['trade_date'].astype(str)
        value_col = 'factor_value'
        if 'z_score' in factor_df.columns and factor_df['z_score'].notna().any():
            value_col = 'z_score'
        factor_wide = factor_df.pivot_table(
            index=['trade_date', 'ts_code'], columns='factor_id',
            values=value_col,
            aggfunc='first',
        )
        # 剔除高缺失因子列：稀疏因子（如财务类仅 ~1% 覆盖）会让逐日联合
        # dropna 后的截面只剩零星股票，其余因子的日收益系数全部退化为 0
        if not factor_wide.empty:
            sparse_cols = factor_wide.columns[factor_wide.isna().mean() > 0.5]
            if len(sparse_cols):
                logger.warning(f"归因剔除高缺失因子(>50% NaN): {list(sparse_cols)}")
                factor_wide = factor_wide.drop(columns=sparse_cols)
            if factor_wide.empty:
                return {'error': '因子缺失率过高，无法归因'}

        try:
            # 全市场行情：组合收益与逐日因子截面回归都需要完整截面
            prices = self.data_reader.get_return_prices(
                start_date=start_date, end_date=end_date)
        except Exception as e:
            logger.error(f"归因读取行情失败: {e}")
            return {'error': f'读取行情失败: {e}'}
        if prices.empty:
            return {'error': '未找到持仓行情数据'}
        close_wide = prices.pivot_table(
            index=pd.to_datetime(prices['trade_date'], format='mixed'),
            columns='ts_code', values='close', aggfunc='first',
        ).sort_index()
        close_wide.index = close_wide.index.strftime('%Y-%m-%d')
        rets = close_wide.pct_change().iloc[1:]
        aligned_codes = [c for c in codes if c in rets.columns]
        if len(aligned_codes) < 2:
            return {'error': '有效持仓行情不足'}
        w = weights.reindex(aligned_codes).fillna(0.0)
        w = w / w.sum() if w.sum() != 0 else w
        port_ret = rets[aligned_codes].fillna(0.0).mul(w, axis=1).sum(axis=1)

        # 因子收益率：逐日截面 OLS（含截距）
        factor_ret_rows = []
        exposure_rows = []
        # 因子暴露滞后一个交易日：当日收益必须用前一日已知暴露解释。
        # 同期回归下，当日类因子（如 momentum_1d 即当日收益）与被解释变量
        # 相关系数恒为 1，会独占全部解释力、其余因子系数恒为 0
        factor_dates = sorted(factor_wide.index.get_level_values('trade_date').unique())
        prev_factor_date = {}
        for i in range(1, len(factor_dates)):
            prev_factor_date[factor_dates[i]] = factor_dates[i - 1]
        for date, day_ret in rets.iterrows():
            factor_date = prev_factor_date.get(date)
            day_factors = factor_wide.xs(factor_date, level='trade_date', drop_level=True) \
                if factor_date is not None else None
            if day_factors is None or day_factors.empty:
                continue
            joined = pd.concat(
                [day_factors, day_ret.rename('ret')], axis=1,
            ).dropna(subset=['ret'] + list(day_factors.columns))
            joined = joined.dropna()
            if len(joined) < min_stocks:
                continue
            X = joined[list(day_factors.columns)].values
            X = (X - X.mean(axis=0)) / np.where(
                X.std(axis=0) > 0, X.std(axis=0), 1.0)
            y = joined['ret'].values
            A = np.column_stack([np.ones(len(X)), X])
            # 截面 OLS 同样加微岭：白名单因子对共线时纯 OLS 的日因子
            # 收益是一对剧烈对消的巨值，下游组合回归无法解读
            gram = A.T @ A
            scale = float(np.mean(np.diag(gram))) or 1.0
            coef = np.linalg.solve(
                gram + np.eye(len(gram)) * (1e-6 * scale), A.T @ y)
            row = {'trade_date': date}
            row.update({f: float(c) for f, c in
                        zip(day_factors.columns, coef[1:])})
            factor_ret_rows.append(row)
            w_vec = w.reindex(joined.index).fillna(0.0).values
            exposure_rows.append((date, X.T @ w_vec))

        if len(factor_ret_rows) < 20:
            return {'error': '有效归因交易日不足（至少 20 日）'}
        factor_ret = pd.DataFrame(factor_ret_rows).set_index('trade_date')
        factor_ret = factor_ret.dropna(axis=1, how='all').fillna(0.0)
        used = [f for f in factor_ids if f in factor_ret.columns]
        if not used:
            return {'error': '因子与持仓共同覆盖期不足'}

        # 组合收益对因子收益回归
        # 微岭正则：accepted 白名单里常有高共线因子对（|ρ|>0.7），纯 OLS
        # 会给出一对巨大反向 beta（数值上合法、解读上误导），lambda 取
        # 因子收益方差均值的小比例只起稳定作用
        common = port_ret.reindex(factor_ret.index).fillna(0.0)
        A = np.column_stack([np.ones(len(factor_ret)),
                             factor_ret[used].values])
        y = common.values
        gram = A.T @ A
        scale = float(np.mean(np.diag(gram))) or 1.0
        ridge = gram + np.eye(len(gram)) * (1e-6 * scale)
        beta = np.linalg.solve(ridge, A.T @ y)
        resid = y - A @ beta
        dof = max(len(common) - len(used) - 1, 1)
        sigma2 = float(resid @ resid) / dof
        # 与岭解同一 Gram 矩阵求协方差；pinv(原 Gram) 在共线下给 出
        # 病态小 se，t 值虚高
        cov = sigma2 * np.linalg.inv(ridge)
        se = np.sqrt(np.diag(cov))
        t_stats = beta / np.where(se > 0, se, np.nan)

        n_days = len(factor_ret)
        attribution = {}
        for i, f in enumerate(used):
            b = float(beta[i + 1])
            fr_mean = float(factor_ret[f].mean())
            attribution[f] = {
                'beta': b,
                't_stat': float(t_stats[i + 1]) if np.isfinite(t_stats[i + 1]) else None,
                'factor_return_annualized': fr_mean * 252,
                # beta × 因子年化收益 = 该风格贡献的年化收益
                'contribution_annualized': b * fr_mean * 252,
            }
        alpha_annualized = float(beta[0]) * 252
        explained = sum(abs(a['contribution_annualized'])
                        for a in attribution.values())
        total_var = float(common.var()) * 252

        # 当前暴露：最新日期的因子 z 加权
        latest_date = factor_ret.index[-1]
        current_exposure = {}
        day_factors = factor_wide.xs(
            latest_date, level='trade_date', drop_level=True)
        for f in used:
            if f not in day_factors.columns:
                continue
            s_all = day_factors[f].dropna()
            if len(s_all) < 2:
                continue
            # 相对全截面标准化，再按持仓权重加权（仓外为 0）
            std = s_all.std()
            if pd.isna(std) or std == 0:
                continue
            z = (s_all - s_all.mean()) / std
            z = z.reindex(w.index).fillna(0.0)
            current_exposure[f] = float((z * w).sum() / w.sum())

        port_summary = {
            'n_days': n_days,
            'total_return': float((1 + common).prod() - 1),
            'annualized_return': float(
                np.expm1(common.mean() * 252)),
            'annualized_vol': float(common.std(ddof=1) * np.sqrt(252)),
        }

        return {
            'portfolio_id': portfolio_id,
            'n_positions': len(codes),
            'start_date': str(factor_ret.index[0]),
            'end_date': str(factor_ret.index[-1]),
            'factor_ids': used,
            'portfolio_summary': port_summary,
            'alpha_annualized': alpha_annualized,
            'r_squared': float(1 - resid.var() / common.var())
            if common.var() > 0 else None,
            'attribution': attribution,
            'current_exposure': current_exposure,
            'factor_return_series': {
                f: [round(float(v), 8) for v in factor_ret[f]]
                for f in used
            },
            'dates': [str(d) for d in factor_ret.index],
        }

    @staticmethod
    def _position_weights(positions: List[Dict[str, Any]]) -> pd.Series:
        records = []
        for p in positions:
            weight = None
            for key in ('weight', 'target_weight', 'optimal_weight'):
                if p.get(key) is not None:
                    weight = float(p[key])
                    break
            records.append((p['ts_code'], weight))
        series = pd.Series(dict(records), dtype=float)
        if series.isna().all():
            series = pd.Series(1.0, index=series.index)
        series = series.fillna(series.dropna().mean() if series.notna().any() else 1.0)
        return series

    def _top_coverage_factors(self, start_date: str, end_date: str,
                              n: int) -> List[str]:
        try:
            ids = [d['factor_id'] for d in
                   self.factor_repo.list_definitions()]
            if not ids:
                return []
            coverage = self.factor_repo.get_factor_coverage(
                ids, start_date=start_date, end_date=end_date)
        except Exception:
            return []
        counted = sorted(coverage.items(),
                         key=lambda kv: -(kv[1].get('dates') or 0))
        return [fid for fid, _ in counted[:n]]
