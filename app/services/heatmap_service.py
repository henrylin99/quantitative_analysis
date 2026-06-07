"""板块热力图数据服务 — 读取 data/data.parquet 并按行业聚合。"""
import os
import pandas as pd
import numpy as np
from loguru import logger


class HeatmapService:
    """板块热力图数据聚合服务。"""

    def __init__(self):
        self._data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data', 'data.parquet'
        )

    def get_heatmap_data(self):
        """读取 parquet，返回 (sectors_json, stocks_json)。

        Returns:
            tuple: (list[dict], list[dict])
                - sectors: 板块聚合数据，按 total_mv 降序
                - stocks: 全量个股数据（已过滤停牌）
        """
        df = pd.read_parquet(self._data_path)
        trade_date = str(df['trade_date'].iloc[0])

        # 过滤停牌/退市
        df = df[df['close'] > 0].copy()

        # 板块聚合
        sectors = []
        for industry, group in df.groupby('industry'):
            total_mv_sum = group['total_mv'].sum()
            if total_mv_sum == 0:
                continue
            avg_pct_chg = np.average(group['pct_chg'], weights=group['total_mv'])
            sectors.append({
                'name': industry,
                'avg_pct_chg': round(avg_pct_chg, 2),
                'total_mv': round(total_mv_sum, 2),
                'stock_count': len(group),
                'up_count': int((group['pct_chg'] > 0).sum()),
                'down_count': int((group['pct_chg'] < 0).sum()),
                'net_mf_amount': round(group['net_mf_amount'].sum(), 2),
                'trade_date': trade_date,
            })

        sectors.sort(key=lambda x: x['total_mv'], reverse=True)

        # 个股明细
        stock_cols = ['ts_code', 'name', 'industry', 'pct_chg', 'close',
                      'total_mv', 'net_mf_amount', 'turnover_rate']
        stocks_df = df[stock_cols].sort_values('pct_chg', ascending=False)
        stocks = stocks_df.where(stocks_df.notna(), None).to_dict(orient='records')

        return sectors, stocks
