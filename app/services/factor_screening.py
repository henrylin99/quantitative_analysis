"""因子体检（批量扫描 + 生命周期）与数据质量监控。

体检口径（每个因子独立评估）：
- IC 质量：采样截面上因子值与未来 N 日收益的 Spearman IC 均值/ICIR/t 值/正率
- 单调性：分桶组序与组均收益的秩相关（按日平均，1=完美单调）
- 换手代理：相邻采样截面因子秩相关均值（越低换手越高）
- 覆盖率：平均每截面有效股票数
- 共线性：采样截面 z-score 因子间 |相关| 最大值及最相关伙伴

生命周期：pending → evaluated → accepted / rejected，评估结论入库
factor_screenings 表，accepted 白名单可直接喂 ML 特征选择。

数据质量监控：按分区扫描每因子覆盖数/均值/方差时序，检测覆盖率骤降、
因子缺席与漂移；配合行情交易日历做分区完整性校验。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats

from app.services.data_reader import ParquetDataReader
from app.services.factor_analyzer import FactorAnalyzer
from app.services.parquet_state_store import (
    FactorRepository, ParquetStateStore,
)

SCREENING_STATUSES = ('pending', 'evaluated', 'accepted', 'rejected')


class FactorScreeningService:
    """因子库批量体检与生命周期管理"""

    TABLE_SCREENINGS = "factor_screenings"

    def __init__(self, store: ParquetStateStore = None,
                 analyzer: FactorAnalyzer = None,
                 factor_repo: FactorRepository = None):
        self.store = store or ParquetStateStore()
        self.analyzer = analyzer or FactorAnalyzer(factor_repo=factor_repo)
        self.factor_repo = factor_repo or self.analyzer.factor_repo

    # ------------------------------------------------------------------
    # 批量体检
    # ------------------------------------------------------------------

    def screen_factors(self, factor_ids: List[str] = None,
                       start_date: str = None, end_date: str = None,
                       forward_period: int = 5, n_quantiles: int = 5,
                       sample_stride: int = 5, min_stocks: int = 50,
                       chunk_size: int = 10,
                       save: bool = True) -> Dict[str, Any]:
        """一键批量体检：IC/单调性/换手/覆盖率/共线性。

        factor_ids 为空时扫描全部活跃因子。采样截面按 sample_stride
        抽取以控制内存与耗时；结果默认入库（状态 evaluated）。
        """
        forward_period = max(1, int(forward_period))
        sample_stride = max(1, int(sample_stride))
        min_stocks = max(2 * n_quantiles, int(min_stocks))

        bounds = self.analyzer._bounded_date_range(start_date, end_date)
        if bounds is None:
            return {'error': '因子库为空'}
        start_date, end_date = bounds

        factor_ids = [f for f in (factor_ids or []) if f]
        if not factor_ids:
            factor_ids = [d['factor_id'] for d in
                          self.factor_repo.list_definitions()]

        sampled_dates = self._sampled_dates(start_date, end_date, sample_stride)
        if not sampled_dates:
            return {'error': '采样区间内无因子数据'}

        metrics: Dict[str, Dict[str, Any]] = {}
        # 分块加载：get_values 按分区整读后过滤，块过大有内存风险
        for i in range(0, len(factor_ids), chunk_size):
            chunk = factor_ids[i:i + chunk_size]
            chunk_metrics = self._screen_chunk(
                chunk, start_date, end_date, sampled_dates, forward_period,
                n_quantiles, min_stocks,
            )
            metrics.update(chunk_metrics)

        live = {f: m for f, m in metrics.items() if 'error' not in m}
        collinearity = self._collinearity(live, start_date, end_date,
                                          sampled_dates, min_stocks)
        for fid, m in metrics.items():
            if 'error' in m:
                continue
            info = collinearity.get(fid)
            m['max_abs_corr'] = info['max_abs_corr'] if info else None
            m['most_correlated'] = info['partner'] if info else None

        report = {
            'screened_at': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
            'start_date': start_date,
            'end_date': end_date,
            'forward_period': forward_period,
            'n_quantiles': n_quantiles,
            'sample_stride': sample_stride,
            'n_factors': len(metrics),
            'factors': metrics,
        }
        if save:
            self._save_report(report)
        return report

    def _sampled_dates(self, start_date: str, end_date: str,
                       stride: int) -> List[str]:
        # 分区目录挂在因子库的 store 上，不是体检表的 store
        factor_store = getattr(self.factor_repo, 'store', None) or self.store
        partitions = factor_store.list_partitions(
            self.factor_repo.TABLE_VALUES, "trade_date")
        selected = [p for p in partitions if start_date <= p <= end_date]
        return selected[::stride]

    def _screen_chunk(self, factor_ids: List[str], start_date: str,
                      end_date: str, sampled_dates: List[str],
                      forward_period: int, n_quantiles: int,
                      min_stocks: int) -> Dict[str, Dict[str, Any]]:
        df = self.factor_repo.get_values(
            factor_ids=factor_ids, start_date=start_date, end_date=end_date,
        )
        result: Dict[str, Dict[str, Any]] = {}
        if df.empty:
            return {f: {'error': '未找到因子值'} for f in factor_ids}
        df = df[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna(
            subset=['factor_value'])
        df = df[df['trade_date'].astype(str).isin(sampled_dates)]
        if df.empty:
            return {f: {'error': '采样截面无数据'} for f in factor_ids}

        price_end = (pd.Timestamp(sampled_dates[-1])
                     + pd.Timedelta(days=forward_period * 3 + 7)
                     ).strftime('%Y-%m-%d')
        try:
            prices = self.analyzer.data_reader.get_return_prices(
                start_date=sampled_dates[0], end_date=price_end)
        except Exception as e:
            logger.error(f"因子体检读取行情失败: {e}")
            return {f: {'error': f'读取行情失败: {e}'} for f in factor_ids}
        if prices.empty:
            return {f: {'error': '未找到行情数据'} for f in factor_ids}
        close_wide = prices.pivot_table(
            index=pd.to_datetime(prices['trade_date'], format='mixed'),
            columns='ts_code', values='close', aggfunc='first',
        ).sort_index()
        fwd = close_wide.shift(-forward_period) / close_wide - 1.0
        fwd.index = fwd.index.strftime('%Y-%m-%d')

        for fid in factor_ids:
            sub = df[df['factor_id'] == fid]
            if sub.empty:
                result[fid] = {'error': '采样截面无数据'}
                continue
            wide = sub.pivot_table(
                index='trade_date', columns='ts_code',
                values='factor_value', aggfunc='first',
            ).sort_index()
            wide.index = wide.index.astype(str)

            ics, monos, sizes = [], [], []
            ranks_by_date = {}
            for date, row in wide.iterrows():
                aligned = pd.DataFrame({
                    'f': row, 'r': fwd.loc[date] if date in fwd.index else None,
                }).dropna()
                ranks_by_date[date] = aligned['f'].rank()
                sizes.append(int(len(aligned)))
                if len(aligned) < min_stocks:
                    continue
                ic = stats.spearmanr(
                    aligned['f'], aligned['r']).statistic
                if not np.isnan(ic):
                    ics.append(float(ic))
                # 单调性：分桶组序 × 组均收益的秩相关
                pct_rank = aligned['f'].rank(pct=True, method='average')
                bucket = np.minimum(
                    (pct_rank * n_quantiles).apply(np.ceil).astype(int),
                    n_quantiles)
                grp = aligned.assign(_b=bucket).groupby('_b')['r'].mean()
                if len(grp) >= 2:
                    mono = stats.spearmanr(grp.index, grp.values).statistic
                    if not np.isnan(mono):
                        monos.append(float(mono))

            if not ics:
                result[fid] = {'error': '有效截面不足（股票数过少）'}
                continue

            ics_arr = np.array(ics)
            ic_mean = float(ics_arr.mean())
            ic_std = float(ics_arr.std(ddof=1)) if len(ics_arr) > 1 else 0.0
            # 换手代理：相邻采样截面秩相关的均值（低 → 高换手）
            dates_sorted = sorted(ranks_by_date)
            rank_corrs = []
            for a, b in zip(dates_sorted, dates_sorted[1:]):
                pair = pd.concat([ranks_by_date[a], ranks_by_date[b]],
                                 axis=1, join='inner').dropna()
                if len(pair) >= min_stocks:
                    c = pair.corr(method='spearman').iloc[0, 1]
                    if pd.notna(c):
                        rank_corrs.append(float(c))
            avg_rank_autocorr = (
                float(np.mean(rank_corrs)) if rank_corrs else None)

            result[fid] = {
                'ic_mean': ic_mean,
                'ic_ir': ic_mean / ic_std if ic_std > 0 else 0.0,
                'ic_positive_ratio': float((ics_arr > 0).mean()),
                't_stat': (ic_mean / ic_std * np.sqrt(len(ics_arr))
                           if ic_std > 0 else 0.0),
                'monotonicity': float(np.mean(monos)) if monos else None,
                'rank_autocorr': avg_rank_autocorr,
                'avg_coverage': float(np.mean(sizes)) if sizes else 0.0,
                'n_sections': len(ics),
            }
        return result

    def _collinearity(self, metrics: Dict[str, Dict[str, Any]],
                      start_date: str, end_date: str,
                      sampled_dates: List[str],
                      min_stocks: int) -> Dict[str, Dict[str, Any]]:
        """采样截面 z-score 因子间平均相关，只看 |ρ| 最高的伙伴。"""
        factor_ids = list(metrics.keys())
        if len(factor_ids) < 2:
            return {}
        df = self.factor_repo.get_values(
            factor_ids=factor_ids, start_date=start_date, end_date=end_date,
        )
        if df.empty:
            return {}
        df = df[df['trade_date'].astype(str).isin(sampled_dates)]
        wide = df.pivot_table(
            index=['trade_date', 'ts_code'], columns='factor_id',
            values='factor_value', aggfunc='first',
        )
        corr_sum = wide.corr(method='spearman', min_periods=min_stocks)
        result = {}
        for fid in factor_ids:
            if fid not in corr_sum.columns:
                result[fid] = {'max_abs_corr': None, 'partner': None}
                continue
            row = corr_sum[fid].drop(labels=[fid]).dropna()
            if row.empty:
                result[fid] = {'max_abs_corr': None, 'partner': None}
                continue
            partner = row.abs().idxmax()
            result[fid] = {
                'max_abs_corr': round(float(row.abs().max()), 4),
                'partner': str(partner),
            }
        return result

    # ------------------------------------------------------------------
    # 生命周期管理
    # ------------------------------------------------------------------

    def _save_report(self, report: Dict[str, Any]) -> None:
        rows = []
        for fid, m in report['factors'].items():
            rows.append({
                'factor_id': fid,
                'screened_at': report['screened_at'],
                'start_date': report['start_date'],
                'end_date': report['end_date'],
                'forward_period': report['forward_period'],
                'metrics': m,
                'status': ('evaluated' if 'error' not in m else 'rejected'),
                'note': m.get('error', ''),
            })
        new = pd.DataFrame(rows)
        with self.store.locked(self.TABLE_SCREENINGS):
            old = self.store.read_frame(self.TABLE_SCREENINGS)
            if not old.empty:
                # 同因子旧记录保留历史，新纪录追加
                combined = pd.concat([old, new], ignore_index=True)
            else:
                combined = new
            self.store.write_frame(self.TABLE_SCREENINGS, combined)

    def list_screenings(self, status: str = None,
                        factor_id: str = None) -> List[Dict[str, Any]]:
        df = self.store.read_frame(self.TABLE_SCREENINGS)
        if df.empty:
            return []
        if status:
            df = df[df['status'] == status]
        if factor_id:
            df = df[df['factor_id'] == factor_id]
        records = []
        for _, row in df.iterrows():
            rec = row.to_dict()
            rec['metrics'] = row['metrics'] if isinstance(
                row['metrics'], dict) else {}
            records.append(rec)
        # 每因子只留最新一条
        records.sort(key=lambda r: str(r.get('screened_at', '')), reverse=True)
        latest: Dict[str, Dict[str, Any]] = {}
        for rec in records:
            latest.setdefault(rec['factor_id'], rec)
        return list(latest.values())

    def set_status(self, factor_id: str, status: str,
                   note: str = '') -> Dict[str, Any]:
        if status not in SCREENING_STATUSES:
            return {'error': f'非法状态 {status}，可选：'
                            f'{", ".join(SCREENING_STATUSES)}'}
        with self.store.locked(self.TABLE_SCREENINGS):
            df = self.store.read_frame(self.TABLE_SCREENINGS)
            if df.empty or (df['factor_id'] == factor_id).sum() == 0:
                return {'error': f'因子 {factor_id} 尚无体检记录，'
                                '请先运行批量体检'}
            idx = df[df['factor_id'] == factor_id].index[-1]
            df.loc[idx, 'status'] = status
            if note:
                df.loc[idx, 'note'] = note
            self.store.write_frame(self.TABLE_SCREENINGS, df)
        return {'factor_id': factor_id, 'status': status}

    def accepted_factors(self) -> List[str]:
        return [r['factor_id'] for r in
                self.list_screenings(status='accepted')]

    # ------------------------------------------------------------------
    # 共线性去冗余（训练前特征预选）
    # ------------------------------------------------------------------

    def select_low_collinearity(self, factor_ids: List[str],
                               threshold: float = 0.7,
                               start_date: str = None, end_date: str = None,
                               sample_stride: int = 5,
                               min_stocks: int = 30) -> Dict[str, Any]:
        """贪心去冗余：按输入顺序保留，与已保留因子 |ρ|≥threshold 的剔除。

        返回 kept / dropped（含被谁替代），直接用作模型 factor_list。
        """
        factor_ids = [f for f in (factor_ids or []) if f]
        if len(factor_ids) < 2:
            return {'kept': factor_ids, 'dropped': [], 'threshold': threshold}

        bounds = self.analyzer._bounded_date_range(start_date, end_date)
        if bounds is None:
            return {'error': '因子库为空'}
        start_date, end_date = bounds
        sampled = self._sampled_dates(start_date, end_date, sample_stride)
        if not sampled:
            return {'error': '采样区间内无因子数据'}

        df = self.factor_repo.get_values(
            factor_ids=factor_ids, start_date=start_date, end_date=end_date)
        if df.empty:
            return {'error': '未找到因子值'}
        df = df[df['trade_date'].astype(str).isin(sampled)]
        wide = df.pivot_table(
            index=['trade_date', 'ts_code'], columns='factor_id',
            values='factor_value', aggfunc='first',
        )
        corr = wide.corr(method='spearman', min_periods=min_stocks)

        kept: List[str] = []
        dropped: List[Dict[str, Any]] = []
        for fid in factor_ids:
            if fid not in corr.columns:
                dropped.append({'factor_id': fid, 'reason': '无数据'})
                continue
            conflict = None
            for k in kept:
                c = corr.loc[fid, k]
                if pd.notna(c) and abs(float(c)) >= threshold:
                    conflict = (k, float(c))
                    break
            if conflict is None:
                kept.append(fid)
            else:
                dropped.append({
                    'factor_id': fid,
                    'correlated_with': conflict[0],
                    'abs_corr': round(abs(conflict[1]), 4),
                })
        return {
            'kept': kept,
            'dropped': dropped,
            'threshold': threshold,
            'n_sections': len(sampled),
        }


class FactorQualityMonitor:
    """因子数据质量监控：覆盖/均值/方差时序 + 漂移与分区完整性校验"""

    def __init__(self, store: ParquetStateStore = None,
                 factor_repo: FactorRepository = None,
                 data_reader: ParquetDataReader = None):
        self.store = store or ParquetStateStore()
        self.factor_repo = factor_repo or FactorRepository(self.store)
        self.data_reader = data_reader or ParquetDataReader()

    def quality_report(self, last_n_partitions: int = 60,
                       coverage_drop_ratio: float = 0.5,
                       std_jump_ratio: float = 3.0,
                       drift_z_threshold: float = 3.0) -> Dict[str, Any]:
        """扫描最近 N 个分区，产出质量时序与报警。

        报警类型：
        - coverage_drop：最新截面覆盖数较历史中位数骤降（默认 >50%）
        - coverage_low：最新截面覆盖数绝对值过低（<100 只）
        - factor_missing：上一分区存在、最新分区缺席的因子
        - std_jump / drift：最新均值/标准差相对历史 z-score 超阈
        - partition_gap：分区日期与行情交易日历缺口（含非交易日杂散分区）
        """
        partitions = sorted(self.store.list_partitions(
            self.factor_repo.TABLE_VALUES, "trade_date"))
        if not partitions:
            return {'error': '因子库为空'}
        scanned = partitions[-last_n_partitions:]

        stats_rows: List[Dict[str, Any]] = []
        for p in scanned:
            df = self.store.read_partition(
                self.factor_repo.TABLE_VALUES, "trade_date", p)
            if df.empty:
                stats_rows.append({'partition': p, 'empty': True})
                continue
            grouped = df.groupby('factor_id')['factor_value']
            per_factor = pd.DataFrame({
                'count': grouped.count(),
                'mean': grouped.mean(),
                'std': grouped.std(),
            })
            for fid, row in per_factor.iterrows():
                stats_rows.append({
                    'partition': p, 'factor_id': fid,
                    'count': int(row['count']),
                    'mean': float(row['mean']) if pd.notna(row['mean']) else None,
                    'std': float(row['std']) if pd.notna(row['std']) else None,
                })

        stats_df = pd.DataFrame(
            [r for r in stats_rows if not r.get('empty')])
        if stats_df.empty:
            return {'error': '扫描区间内无因子数据'}

        alerts: List[Dict[str, Any]] = []
        history = stats_df[stats_df['partition'] < scanned[-1]]
        latest_p = scanned[-1]
        latest = stats_df[stats_df['partition'] == latest_p]

        coverage_median = history.groupby('factor_id')['count'].median()
        mean_stats = history.groupby('factor_id')['mean'].agg(['mean', 'std'])
        std_stats = history.groupby('factor_id')['std'].agg(['mean', 'std'])

        for _, row in latest.iterrows():
            fid = row['factor_id']
            med = coverage_median.get(fid)
            if med and med > 0 and row['count'] < med * (1 - coverage_drop_ratio):
                alerts.append({
                    'type': 'coverage_drop', 'factor_id': fid,
                    'partition': latest_p,
                    'detail': f"覆盖 {row['count']} 只，历史中位数 {med:.0f}",
                })
            if row['count'] < 100:
                alerts.append({
                    'type': 'coverage_low', 'factor_id': fid,
                    'partition': latest_p,
                    'detail': f"覆盖仅 {row['count']} 只",
                })
            for col, ref, alert_type in (
                ('mean', mean_stats, 'drift'),
                ('std', std_stats, 'std_jump'),
            ):
                ref_row = ref.loc[fid] if fid in ref.index else None
                value = row.get(col)
                if (ref_row is not None and value is not None
                        and pd.notna(value) and pd.notna(ref_row['std'])
                        and ref_row['std'] > 0):
                    z = abs(value - ref_row['mean']) / ref_row['std']
                    threshold = (std_jump_ratio if alert_type == 'std_jump'
                                 else drift_z_threshold)
                    if z > threshold:
                        alerts.append({
                            'type': alert_type, 'factor_id': fid,
                            'partition': latest_p,
                            'detail': f"{col}={value:.6g}，"
                                      f"历史均值 {ref_row['mean']:.6g}，"
                                      f"z={z:.2f}",
                        })

        prev_p = scanned[-2] if len(scanned) >= 2 else None
        if prev_p:
            prev = set(stats_df[stats_df['partition'] == prev_p]['factor_id'])
            curr = set(latest['factor_id'])
            for fid in sorted(prev - curr):
                alerts.append({
                    'type': 'factor_missing', 'factor_id': fid,
                    'partition': latest_p,
                    'detail': f"上一分区 {prev_p} 存在、本分区缺席",
                })

        gaps = self._partition_gaps(scanned)

        pivot_count = stats_df.pivot_table(
            index='partition', columns='factor_id', values='count',
            aggfunc='first',
        )
        coverage_trend = {
            'partitions': list(pivot_count.index),
            'n_factors': int(pivot_count.shape[1]),
            'coverage_median': [
                float(v) for v in pivot_count.median(axis=1)
            ],
        }

        return {
            'scanned_partitions': len(scanned),
            'first_partition': scanned[0],
            'last_partition': latest_p,
            'coverage_trend': coverage_trend,
            'alerts': alerts,
            'n_alerts': len(alerts),
            'partition_gaps': gaps,
        }

    def _partition_gaps(self, scanned: List[str]) -> List[Dict[str, Any]]:
        """分区完整性：对照行情交易日历找缺口与多余的非交易日分区。"""
        if len(scanned) < 2:
            return []
        try:
            prices = self.data_reader.get_return_prices(
                start_date=scanned[0], end_date=scanned[-1])
        except Exception as e:
            logger.warning(f"质量监控读取行情日历失败: {e}")
            return []
        if prices.empty:
            return []
        calendar = set(pd.to_datetime(
            prices['trade_date'], format='mixed').dt.strftime('%Y-%m-%d'))
        have = set(scanned)
        missing = sorted(calendar - have)
        extra = sorted(d for d in have - calendar)
        gaps: List[Dict[str, Any]] = []
        if missing:
            gaps.append({'type': 'missing_partitions',
                         'detail': f"交易日缺分区 {len(missing)} 天",
                         'dates': missing[:30]})
        if extra:
            gaps.append({'type': 'non_trading_day_partitions',
                         'detail': f"非交易日杂散分区 {len(extra)} 天",
                         'dates': extra[:30]})
        return gaps
