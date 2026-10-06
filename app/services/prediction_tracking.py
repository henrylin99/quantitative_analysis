"""预测信号持续跟踪：把 ml_predictions 的沉淀变成滚动质量曲线。

口径：
- 逐日预测 IC：每个预测日截面上预测值与未来 N 日实际收益的 Spearman 相关
- top-N 实现收益：按预测值取 top-N / bottom-N 等权组合的前向收益，
  对照全截面等权基准
- 信号衰减：预测 IC 随 horizon（1/5/10d）的变化
- 多模型一致性：同日不同模型预测截面之间的秩相关均值
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats

from app.services.data_reader import ParquetDataReader
from app.services.parquet_state_store import ModelRepository


class PredictionTrackingService:
    """模型预测信号质量的滚动跟踪"""

    def __init__(self, model_repo: ModelRepository = None,
                 data_reader: ParquetDataReader = None):
        from app.services.parquet_state_store import ParquetStateStore
        self.model_repo = model_repo or ModelRepository(ParquetStateStore())
        self.data_reader = data_reader or ParquetDataReader()

    @staticmethod
    def _target_period(target_type: str) -> int:
        try:
            return int(str(target_type).split('_')[1].replace('d', ''))
        except (IndexError, ValueError):
            return 5

    def track(self, model_ids: List[str] = None, start_date: str = None,
              end_date: str = None, horizons: List[int] = None,
              top_n: int = 50, min_stocks: int = 30) -> Dict[str, Any]:
        """多模型预测质量跟踪报告。"""
        horizons = sorted({max(1, int(h)) for h in (horizons or [1, 5, 10])})
        top_n = max(1, int(top_n))

        all_models = [m['model_id'] for m in
                      self.model_repo.list_definitions()]
        model_ids = [m for m in (model_ids or all_models) if m]
        if not model_ids:
            return {'error': '没有可跟踪的模型'}

        preds = self.model_repo.get_predictions()
        if preds.empty:
            return {'error': '暂无预测数据'}
        preds = preds[preds['model_id'].isin(model_ids)]
        if start_date:
            preds = preds[preds['trade_date'].astype(str) >= start_date]
        if end_date:
            preds = preds[preds['trade_date'].astype(str) <= end_date]
        if preds.empty:
            return {'error': '指定区间内无预测数据'}

        # 行情：覆盖预测区间 + 最大 horizon 缓冲
        pmin, pmax = (preds['trade_date'].astype(str).min(),
                      preds['trade_date'].astype(str).max())
        price_end = (pd.Timestamp(pmax)
                     + pd.Timedelta(days=max(horizons) * 3 + 7)
                     ).strftime('%Y-%m-%d')
        try:
            prices = self.data_reader.get_return_prices(
                start_date=pmin, end_date=price_end)
        except Exception as e:
            logger.error(f"预测跟踪读取行情失败: {e}")
            return {'error': f'读取行情失败: {e}'}
        if prices.empty:
            return {'error': '未找到行情数据'}
        close_wide = prices.pivot_table(
            index=pd.to_datetime(prices['trade_date'], format='mixed'),
            columns='ts_code', values='close', aggfunc='first',
        ).sort_index()
        close_wide.index = close_wide.index.strftime('%Y-%m-%d')

        fwd = {h: close_wide.shift(-h) / close_wide - 1.0 for h in horizons}

        per_model: Dict[str, Dict[str, Any]] = {}
        for mid in model_ids:
            sub = preds[preds['model_id'] == mid]
            if sub.empty:
                per_model[mid] = {'error': '区间内无预测'}
                continue
            model_def = self.model_repo.get_definition(mid)
            base_h = self._target_period(
                model_def['target_type']) if model_def else horizons[0]
            per_model[mid] = self._track_one(
                sub, fwd, horizons, base_h if base_h in horizons
                else horizons[-1], top_n, min_stocks)

        consistency = self._model_consistency(preds, model_ids, min_stocks)

        return {
            'model_ids': model_ids,
            'start_date': pmin,
            'end_date': pmax,
            'horizons': horizons,
            'top_n': top_n,
            'models': per_model,
            'model_consistency': consistency,
        }

    def _track_one(self, sub: pd.DataFrame,
                   fwd: Dict[int, pd.DataFrame], horizons: List[int],
                   base_h: int, top_n: int,
                   min_stocks: int) -> Dict[str, Any]:
        ic_series = []
        top_series = []
        ic_by_horizon = {}
        for h in horizons:
            ics = []
            for date, group in sub.groupby('trade_date'):
                date_str = str(date)[:10]
                aligned = pd.DataFrame({
                    'p': group.set_index('ts_code')['predicted_return'],
                    'r': fwd[h].loc[date_str]
                    if date_str in fwd[h].index else None,
                }).dropna()
                if len(aligned) < min_stocks:
                    continue
                ic = stats.spearmanr(
                    aligned['p'], aligned['r']).statistic
                if not np.isnan(ic):
                    ics.append((date_str, float(ic)))
                if h == base_h:
                    ranked = aligned.sort_values('p', ascending=False)
                    top = ranked.head(top_n)['r'].mean()
                    bottom = ranked.tail(top_n)['r'].mean()
                    universe = aligned['r'].mean()
                    top_series.append({
                        'date': str(date),
                        'top_return': float(top),
                        'bottom_return': float(bottom),
                        'universe_return': float(universe),
                        'spread': float(top - bottom),
                    })
            arr = np.array([v for _, v in ics])
            ic_by_horizon[str(h)] = {
                'ic_mean': float(arr.mean()) if len(arr) else None,
                'ic_ir': (float(arr.mean() / arr.std(ddof=1))
                          if len(arr) > 1 and arr.std(ddof=1) > 0 else None),
                'ic_positive_ratio': float((arr > 0).mean()) if len(arr) else None,
                'n_dates': int(len(arr)),
            }
            if h == base_h:
                ic_series = [{'date': d, 'ic': v} for d, v in ics]

        spreads = np.array([t['spread'] for t in top_series])
        top_rets = np.array([t['top_return'] for t in top_series])
        universe_rets = np.array([t['universe_return'] for t in top_series])
        excess = top_rets - universe_rets if len(top_rets) else np.array([])
        summary = {
            'base_horizon': base_h,
            'n_dates': len(top_series),
            'spread_mean': float(spreads.mean()) if len(spreads) else None,
            'spread_win_rate': (float((spreads > 0).mean())
                                if len(spreads) else None),
            'top_excess_mean': float(excess.mean()) if len(excess) else None,
            'top_excess_ir': (float(excess.mean() / excess.std(ddof=1))
                              if len(excess) > 1
                              and excess.std(ddof=1) > 0 else None),
        }
        return {
            'ic_series': ic_series,
            'top_n_series': top_series,
            'ic_by_horizon': ic_by_horizon,
            'summary': summary,
        }

    def _model_consistency(self, preds: pd.DataFrame, model_ids: List[str],
                           min_stocks: int) -> Dict[str, Any]:
        """同日不同模型预测截面之间的秩相关（模型间一致性）。"""
        per_day: Dict[str, Dict[str, pd.Series]] = {}
        for mid in model_ids:
            sub = preds[preds['model_id'] == mid]
            if sub.empty:
                continue
            for date, group in sub.groupby('trade_date'):
                per_day.setdefault(str(date), {})[mid] = (
                    group.set_index('ts_code')['predicted_return'])
        pairs: Dict[str, List[float]] = {}
        series = []
        for date, models in sorted(per_day.items()):
            ids = sorted(models)
            day_corrs = []
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    pair = pd.concat([models[ids[i]], models[ids[j]]],
                                     axis=1, join='inner').dropna()
                    if len(pair) < min_stocks:
                        continue
                    c = pair.corr(method='spearman').iloc[0, 1]
                    if pd.notna(c):
                        key = f'{ids[i]}|{ids[j]}'
                        pairs.setdefault(key, []).append(float(c))
                        day_corrs.append(float(c))
            if day_corrs:
                series.append({'date': date,
                               'mean_corr': float(np.mean(day_corrs))})
        return {
            'series': series,
            'by_pair': {
                k: {'mean': float(np.mean(v)), 'n_dates': len(v)}
                for k, v in pairs.items()
            },
        }
