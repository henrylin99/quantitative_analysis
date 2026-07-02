from pathlib import Path

import pandas as pd
from flask import current_app, render_template, request
from app.main import main_bp
from app.services.stock_service import StockService
from startup_runtime import build_health_report, inspect_parquet_data_assets

@main_bp.route('/')
def index():
    """首页"""
    return render_template('index.html')

@main_bp.route('/stocks')
def stocks():
    """股票列表页面"""
    return render_template('stocks.html')

@main_bp.route('/stock/<ts_code>')
def stock_detail(ts_code):
    """股票详情页面"""
    return render_template('stock_detail.html', ts_code=ts_code)

@main_bp.route('/analysis')
def analysis():
    """分析页面"""
    return render_template('analysis.html')

@main_bp.route('/screen')
def screen():
    """选股筛选页面"""
    return render_template('screen.html')

@main_bp.route('/backtest')
def backtest():
    """策略回测页面"""
    return render_template('backtest.html')


@main_bp.route('/trial/market-brief')
def market_brief():
    """每日市场简报生成器"""
    data_path = Path(__file__).resolve().parents[2] / 'data' / 'data.parquet'

    try:
        if not data_path.exists():
            raise FileNotFoundError(f'数据文件不存在: {data_path}')

        df = pd.read_parquet(data_path)
        required_cols = [
            'ts_code', 'name', 'industry', 'trade_date', 'pct_chg', 'amount',
            'pattern_first_limit', 'pattern_multi_limit', 'pattern_bullish_engulfing',
            'net_mf_amount', 'consec_up_days', 'limit_status',
        ]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f'缺少必要字段: {", ".join(missing_cols)}')

        df = df.copy()
        df = df[df['industry'].notna()].copy()
        df['trade_date'] = df['trade_date'].astype(str)
        latest_trade_date = df['trade_date'].max()
        day_df = df[df['trade_date'] == latest_trade_date].copy()
        if day_df.empty:
            raise ValueError(f'交易日 {latest_trade_date} 没有可用市场数据')

        numeric_cols = ['pct_chg', 'amount', 'pattern_first_limit', 'pattern_multi_limit',
                        'pattern_bullish_engulfing', 'net_mf_amount', 'consec_up_days']
        for col in numeric_cols:
            day_df[col] = pd.to_numeric(day_df[col], errors='coerce').fillna(0.0)

        day_df['is_up'] = day_df['pct_chg'] > 0
        day_df['is_down'] = day_df['pct_chg'] < 0
        day_df['is_limit_up'] = day_df['limit_status'].astype(str).eq('U')
        day_df['is_limit_down'] = day_df['limit_status'].astype(str).eq('D')

        market_summary = {
            'trade_date': latest_trade_date,
            'stock_count': int(len(day_df)),
            'advance_count': int(day_df['is_up'].sum()),
            'decline_count': int(day_df['is_down'].sum()),
            'flat_count': int((day_df['pct_chg'] == 0).sum()),
            'limit_up_count': int(day_df['is_limit_up'].sum()),
            'limit_down_count': int(day_df['is_limit_down'].sum()),
            'turnover_total': float(day_df['amount'].sum()),
        }

        top_amount = (
            day_df.sort_values('amount', ascending=False)
            .head(10)[['ts_code', 'name', 'industry', 'amount', 'pct_chg', 'net_mf_amount']]
            .copy()
        )

        industry_df = (
            day_df.groupby('industry', dropna=False)
            .agg(
                stock_count=('ts_code', 'count'),
                advance_count=('is_up', 'sum'),
                decline_count=('is_down', 'sum'),
                avg_pct_chg=('pct_chg', 'mean'),
                total_amount=('amount', 'sum'),
                net_mf_amount=('net_mf_amount', 'sum'),
            )
            .reset_index()
        )
        industry_df = industry_df.sort_values('avg_pct_chg', ascending=False).reset_index(drop=True)
        industry_top = industry_df.head(10)
        industry_bottom = industry_df.sort_values('avg_pct_chg', ascending=True).head(10)

        limit_up_count = int(day_df['is_limit_up'].sum())
        limit_down_count = int(day_df['is_limit_down'].sum())
        first_limit_count = int(day_df['pattern_first_limit'].sum())
        multi_limit_count = int(day_df['pattern_multi_limit'].sum())
        bullish_engulfing_count = int(day_df['pattern_bullish_engulfing'].sum())
        consec_up_2p_count = int((day_df['consec_up_days'] >= 2).sum())
        consec_up_3p_count = int((day_df['consec_up_days'] >= 3).sum())
        consec_up_5p_count = int((day_df['consec_up_days'] >= 5).sum())

        top_mf = (
            day_df.sort_values('net_mf_amount', ascending=False)
            .head(5)[['ts_code', 'name', 'industry', 'net_mf_amount', 'pct_chg']]
            .copy()
        )

        total_advance_decline = market_summary['advance_count'] + market_summary['decline_count']
        advance_rate = (market_summary['advance_count'] / total_advance_decline * 100) if total_advance_decline else 0
        decline_rate = (market_summary['decline_count'] / total_advance_decline * 100) if total_advance_decline else 0

        lines = []
        lines.append(f"每日市场简报 | {latest_trade_date}")
        lines.append("")
        lines.append("一、全市场概览")
        lines.append(
            f"今日全市场共 {market_summary['stock_count']} 只股票参与统计，"
            f"上涨 {market_summary['advance_count']} 只，下跌 {market_summary['decline_count']} 只，平盘 {market_summary['flat_count']} 只。"
        )
        lines.append(
            f"涨跌家数占比为：上涨 {advance_rate:.1f}% ，下跌 {decline_rate:.1f}% 。"
        )
        lines.append(
            f"涨停 {limit_up_count} 只，跌停 {limit_down_count} 只。"
        )
        lines.append(
            f"全市场成交额合计 {market_summary['turnover_total'] / 10000:.2f} 亿。"
        )

        lines.append("")
        lines.append("二、成交额 TOP10")
        for idx, row in enumerate(top_amount.to_dict(orient='records'), 1):
            lines.append(
                f"{idx}. {row['name']}（{row['ts_code']}，{row['industry']}）"
                f"成交额 {row['amount'] / 10000:.2f} 亿，涨跌幅 {row['pct_chg']:.2f}%，"
                f"主力净流入 {row['net_mf_amount'] / 10000:.2f} 亿。"
            )

        lines.append("")
        lines.append("三、行业涨跌排名")
        lines.append("涨幅靠前行业：")
        for idx, row in enumerate(industry_top.to_dict(orient='records'), 1):
            lines.append(
                f"{idx}. {row['industry']}：平均涨跌幅 {row['avg_pct_chg']:.2f}%，"
                f"上涨 {int(row['advance_count'])} 只，下跌 {int(row['decline_count'])} 只，"
                f"成交额 {row['total_amount'] / 10000:.2f} 亿。"
            )
        lines.append("跌幅靠前行业：")
        for idx, row in enumerate(industry_bottom.to_dict(orient='records'), 1):
            lines.append(
                f"{idx}. {row['industry']}：平均涨跌幅 {row['avg_pct_chg']:.2f}%，"
                f"上涨 {int(row['advance_count'])} 只，下跌 {int(row['decline_count'])} 只，"
                f"成交额 {row['total_amount'] / 10000:.2f} 亿。"
            )

        lines.append("")
        lines.append("四、主力净流入 TOP5")
        for idx, row in enumerate(top_mf.to_dict(orient='records'), 1):
            lines.append(
                f"{idx}. {row['name']}（{row['ts_code']}，{row['industry']}）"
                f"主力净流入 {row['net_mf_amount'] / 10000:.2f} 亿，涨跌幅 {row['pct_chg']:.2f}%。"
            )

        lines.append("")
        lines.append("五、特殊形态统计")
        lines.append(f"首板数：{first_limit_count} 只。")
        lines.append(f"连板数：{multi_limit_count} 只。")
        lines.append(f"阳包阴数：{bullish_engulfing_count} 只。")
        lines.append(
            f"连续上涨统计：2 连及以上 {consec_up_2p_count} 只，3 连及以上 {consec_up_3p_count} 只，5 连及以上 {consec_up_5p_count} 只。"
        )
        lines.append(
            f"今日涨停 {limit_up_count} 只，跌停 {limit_down_count} 只。"
        )

        brief_text = "\n".join(lines)

        return render_template(
            'market_brief.html',
            summary=market_summary,
            brief_lines=lines,
            brief_text=brief_text,
            top_amount=top_amount.where(top_amount.notna(), None).to_dict(orient='records'),
            industry_top=industry_top.where(industry_top.notna(), None).to_dict(orient='records'),
            industry_bottom=industry_bottom.where(industry_bottom.notna(), None).to_dict(orient='records'),
            top_mf=top_mf.where(top_mf.notna(), None).to_dict(orient='records'),
            special_stats={
                'first_limit_count': first_limit_count,
                'multi_limit_count': multi_limit_count,
                'bullish_engulfing_count': bullish_engulfing_count,
                'consec_up_2p_count': consec_up_2p_count,
                'consec_up_3p_count': consec_up_3p_count,
                'consec_up_5p_count': consec_up_5p_count,
                'limit_up_count': limit_up_count,
                'limit_down_count': limit_down_count,
            },
        )
    except Exception as exc:
        return render_template(
            'market_brief.html',
            summary={
                'trade_date': '',
                'stock_count': 0,
                'advance_count': 0,
                'decline_count': 0,
                'flat_count': 0,
                'limit_up_count': 0,
                'limit_down_count': 0,
                'turnover_total': 0.0,
            },
            brief_lines=[],
            brief_text='',
            top_amount=[],
            industry_top=[],
            industry_bottom=[],
            top_mf=[],
            special_stats={
                'first_limit_count': 0,
                'multi_limit_count': 0,
                'bullish_engulfing_count': 0,
                'consec_up_2p_count': 0,
                'consec_up_3p_count': 0,
                'consec_up_5p_count': 0,
                'limit_up_count': 0,
                'limit_down_count': 0,
            },
            error=str(exc),
        )


@main_bp.route('/trial/financial-health')
def financial_health():
    """财务健康度评分卡"""
    data_path = Path(__file__).resolve().parents[2] / 'data' / 'data.parquet'

    try:
        if not data_path.exists():
            raise FileNotFoundError(f'数据文件不存在: {data_path}')

        df = pd.read_parquet(data_path)
        required_cols = [
            'ts_code', 'name', 'industry', 'trade_date',
            'fin_gross_margin', 'fin_net_margin', 'fin_n_cashflow_act',
            'fin_debt_ratio', 'fin_n_income_attr_p', 'fin_total_hldr_eqy',
        ]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f'缺少必要字段: {", ".join(missing_cols)}')

        df = df.copy().dropna(subset=['ts_code', 'name'])
        df = df[df['industry'].notna()].copy()
        df['trade_date'] = df['trade_date'].astype(str)
        latest_trade_date = df['trade_date'].max()
        day_df = df[df['trade_date'] == latest_trade_date].copy()
        if day_df.empty:
            raise ValueError(f'交易日 {latest_trade_date} 没有可用财务数据')

        numeric_cols = [
            'fin_gross_margin', 'fin_net_margin', 'fin_n_cashflow_act',
            'fin_debt_ratio', 'fin_n_income_attr_p', 'fin_total_hldr_eqy',
        ]
        for col in numeric_cols:
            day_df[col] = pd.to_numeric(day_df[col], errors='coerce')

        min_equity_threshold = 1e7
        day_df['score_gross_margin'] = (day_df['fin_gross_margin'] > 30).astype(int)
        day_df['score_net_margin'] = (day_df['fin_net_margin'] > 10).astype(int)
        day_df['score_cashflow'] = (day_df['fin_n_cashflow_act'] > 0).astype(int)
        day_df['score_debt_ratio'] = (day_df['fin_debt_ratio'] < 0.6).astype(int)
        valid_equity = day_df['fin_total_hldr_eqy'].notna() & (day_df['fin_total_hldr_eqy'] > min_equity_threshold)
        roe = day_df['fin_n_income_attr_p'] / day_df['fin_total_hldr_eqy']
        day_df['roe_ratio'] = roe.where(valid_equity)
        day_df['score_roe'] = day_df['roe_ratio'].gt(0.10).fillna(False).astype(int)
        day_df['health_score'] = (
            day_df['score_gross_margin']
            + day_df['score_net_margin']
            + day_df['score_cashflow']
            + day_df['score_debt_ratio']
            + day_df['score_roe']
        )

        scored = day_df[[
            'ts_code', 'name', 'industry',
            'fin_gross_margin', 'fin_net_margin', 'fin_n_cashflow_act',
            'fin_debt_ratio', 'fin_n_income_attr_p', 'fin_total_hldr_eqy',
            'roe_ratio', 'score_gross_margin', 'score_net_margin',
            'score_cashflow', 'score_debt_ratio', 'score_roe', 'health_score',
        ]].copy()
        scored = scored.sort_values(
            ['health_score', 'fin_gross_margin', 'fin_net_margin', 'fin_n_cashflow_act'],
            ascending=[False, False, False, False],
        ).reset_index(drop=True)

        score_bins = scored['health_score'].value_counts().reindex(range(6), fill_value=0).sort_index()
        score_distribution = [
            {'score': score, 'count': int(count), 'label': f'{score} 分'}
            for score, count in score_bins.items()
        ]

        summary = {
            'trade_date': latest_trade_date,
            'stock_count': int(len(scored)),
            'avg_score': float(scored['health_score'].mean()) if not scored.empty else 0.0,
            'max_score': int(scored['health_score'].max()) if not scored.empty else 0,
            'min_score': int(scored['health_score'].min()) if not scored.empty else 0,
            'full_score_count': int((scored['health_score'] == 5).sum()),
            'qualified_count': int((scored['health_score'] >= 3).sum()),
        }

        top_rows = scored.head(50)

        return render_template(
            'financial_health.html',
            summary=summary,
            score_distribution=score_distribution,
            scored_rows=top_rows.where(top_rows.notna(), None).to_dict(orient='records'),
            min_equity_threshold=min_equity_threshold,
        )
    except Exception as exc:
        return render_template(
            'financial_health.html',
            summary={
                'trade_date': '',
                'stock_count': 0,
                'avg_score': 0.0,
                'max_score': 0,
                'min_score': 0,
                'full_score_count': 0,
                'qualified_count': 0,
            },
            score_distribution=[{'score': i, 'count': 0, 'label': f'{i} 分'} for i in range(6)],
            scored_rows=[],
            min_equity_threshold=1e7,
            error=str(exc),
        )


@main_bp.route('/trial/stock-radar', methods=['GET'])
def stock_radar():
    """个股对比雷达图"""
    data_path = Path(__file__).resolve().parents[2] / 'data' / 'data.parquet'

    try:
        if not data_path.exists():
            raise FileNotFoundError(f'数据文件不存在: {data_path}')

        raw_codes = request.args.get('ts_codes', '').strip()
        ts_codes = [code.strip().upper() for code in raw_codes.split(',') if code.strip()]
        if len(ts_codes) < 2 or len(ts_codes) > 4:
            raise ValueError('请提供 2 到 4 只股票代码，使用英文逗号分隔')

        # 保持输入顺序并去重
        seen = set()
        ts_codes = [code for code in ts_codes if not (code in seen or seen.add(code))]

        df = pd.read_parquet(data_path)
        required_cols = [
            'ts_code', 'name', 'industry', 'trade_date',
            'pe_ttm', 'pb', 'fin_revenue', 'fin_n_income',
            'rsi_6', 'macd', 'turnover_rate', 'net_mf_amount', 'volume_ratio',
        ]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f'缺少必要字段: {", ".join(missing_cols)}')

        df = df.copy()
        df['trade_date'] = df['trade_date'].astype(str)
        latest_trade_date = df['trade_date'].max()
        day_df = df[df['trade_date'] == latest_trade_date].copy()
        if day_df.empty:
            raise ValueError(f'交易日 {latest_trade_date} 没有可用对比数据')

        day_df = day_df[day_df['ts_code'].astype(str).isin(ts_codes)].copy()
        if day_df.empty:
            raise ValueError('未找到输入股票代码对应的数据')

        found_codes = set(day_df['ts_code'].astype(str).tolist())
        missing_input = [code for code in ts_codes if code not in found_codes]
        if missing_input:
            raise ValueError(f'以下股票代码未找到最新交易日数据: {", ".join(missing_input)}')

        day_df = day_df.copy()
        numeric_cols = [
            'pe_ttm', 'pb', 'fin_revenue', 'fin_n_income',
            'rsi_6', 'macd', 'turnover_rate', 'net_mf_amount', 'volume_ratio',
        ]
        for col in numeric_cols:
            day_df[col] = pd.to_numeric(day_df[col], errors='coerce')

        def min_max(series, reverse=False):
            s = pd.to_numeric(series, errors='coerce')
            valid = s.dropna()
            if valid.empty:
                return pd.Series([None] * len(s), index=s.index)
            min_v = valid.min()
            max_v = valid.max()
            if pd.isna(min_v) or pd.isna(max_v):
                return pd.Series([None] * len(s), index=s.index)
            if max_v == min_v:
                result = pd.Series([0.5] * len(s), index=s.index)
            else:
                result = (s - min_v) / (max_v - min_v)
            if reverse:
                result = 1 - result
            return result.clip(0, 1)

        def z_score(series):
            s = pd.to_numeric(series, errors='coerce')
            valid = s.dropna()
            if valid.empty:
                return pd.Series([None] * len(s), index=s.index)
            mean_v = valid.mean()
            std_v = valid.std(ddof=0)
            if not std_v or pd.isna(std_v):
                return pd.Series([0.5] * len(s), index=s.index)
            normalized = (s - mean_v) / std_v
            return (normalized.clip(-3, 3) + 3) / 6

        # 维度内统一标准化
        day_df['pe_score'] = min_max(day_df['pe_ttm'], reverse=True)
        day_df['pb_score'] = min_max(day_df['pb'], reverse=True)
        day_df['revenue_score'] = min_max(day_df['fin_revenue'])
        day_df['profit_score'] = min_max(day_df['fin_n_income'])
        day_df['rsi_score'] = min_max(day_df['rsi_6'])
        day_df['macd_score'] = z_score(day_df['macd'])
        day_df['turnover_score'] = min_max(day_df['turnover_rate'])
        day_df['mf_score'] = min_max(day_df['net_mf_amount'])
        day_df['volume_score'] = min_max(day_df['volume_ratio'])

        day_df['valuation_score'] = day_df[['pe_score', 'pb_score']].mean(axis=1, skipna=True)
        day_df['growth_score'] = day_df[['revenue_score', 'profit_score']].mean(axis=1, skipna=True)
        day_df['technical_score'] = day_df[['rsi_score', 'macd_score', 'turnover_score']].mean(axis=1, skipna=True)
        day_df['moneyflow_score'] = day_df[['mf_score', 'volume_score']].mean(axis=1, skipna=True)

        dimension_rows = []
        radar_series = []
        for _, row in day_df.iterrows():
            stock_name = row['name']
            dimension_rows.append({
                'ts_code': row['ts_code'],
                'name': stock_name,
                'industry': row['industry'],
                'pe_ttm': row['pe_ttm'],
                'pb': row['pb'],
                'fin_revenue': row['fin_revenue'],
                'fin_n_income': row['fin_n_income'],
                'rsi_6': row['rsi_6'],
                'macd': row['macd'],
                'turnover_rate': row['turnover_rate'],
                'net_mf_amount': row['net_mf_amount'],
                'volume_ratio': row['volume_ratio'],
                'valuation_score': float(row['valuation_score']) if pd.notna(row['valuation_score']) else None,
                'growth_score': float(row['growth_score']) if pd.notna(row['growth_score']) else None,
                'technical_score': float(row['technical_score']) if pd.notna(row['technical_score']) else None,
                'moneyflow_score': float(row['moneyflow_score']) if pd.notna(row['moneyflow_score']) else None,
            })
            radar_series.append({
                'name': stock_name,
                'ts_code': row['ts_code'],
                'industry': row['industry'],
                'value': [
                    float(row['valuation_score']) if pd.notna(row['valuation_score']) else 0,
                    float(row['growth_score']) if pd.notna(row['growth_score']) else 0,
                    float(row['technical_score']) if pd.notna(row['technical_score']) else 0,
                    float(row['moneyflow_score']) if pd.notna(row['moneyflow_score']) else 0,
                ],
            })

        radar_axes = [
            {'name': '估值', 'max': 1},
            {'name': '成长', 'max': 1},
            {'name': '技术', 'max': 1},
            {'name': '资金', 'max': 1},
        ]

        return render_template(
            'stock_radar.html',
            summary={
                'trade_date': latest_trade_date,
                'stock_count': int(len(day_df)),
                'input_codes': ts_codes,
            },
            radar_axes=radar_axes,
            radar_series=radar_series,
            stock_rows=dimension_rows,
            input_codes_text=','.join(ts_codes),
        )
    except Exception as exc:
        return render_template(
            'stock_radar.html',
            summary={
                'trade_date': '',
                'stock_count': 0,
                'input_codes': [],
            },
            radar_axes=[
                {'name': '估值', 'max': 1},
                {'name': '成长', 'max': 1},
                {'name': '技术', 'max': 1},
                {'name': '资金', 'max': 1},
            ],
            radar_series=[],
            stock_rows=[],
            input_codes_text=request.args.get('ts_codes', ''),
            error=str(exc),
        )


@main_bp.route('/trial/stock-panorama', methods=['GET'])
def stock_panorama():
    """个股全景展示"""
    data_path = Path(__file__).resolve().parents[2] / 'data' / 'data.parquet'

    try:
        if not data_path.exists():
            raise FileNotFoundError(f'数据文件不存在: {data_path}')

        ts_code = request.args.get('ts_code', '').strip().upper()
        if not ts_code:
            raise ValueError('请提供股票代码 ts_code')

        df = pd.read_parquet(data_path)
        required_cols = [
            'ts_code', 'name', 'industry', 'area', 'trade_date',
            'close', 'pct_chg', 'change', 'amount', 'vol', 'turnover_rate',
            'pe_ttm', 'pb', 'ps_ttm', 'dv_ttm',
            'fin_revenue', 'fin_n_income', 'fin_n_cashflow_act', 'fin_gross_margin', 'fin_net_margin', 'fin_debt_ratio',
            'rsi_6', 'rsi_12', 'rsi_24', 'macd', 'macd_dif', 'macd_dea',
            'net_mf_amount', 'volume_ratio',
            'pattern_first_limit', 'pattern_multi_limit', 'pattern_bullish_engulfing', 'consec_up_days',
            'limit_status', 'is_lhb', 'winner_rate', 'cost_50pct', 'price_to_cost',
            'l_buy', 'l_sell', 'lhb_net_amount', 'lhb_net_rate', 'seal_strength',
            'inst_accumulation_score_10', 'value_momentum', 'f_ret_20d', 'f_volatility_20d',
        ]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f'缺少必要字段: {", ".join(missing_cols)}')

        df = df.copy()
        df['trade_date'] = df['trade_date'].astype(str)
        latest_trade_date = df['trade_date'].max()
        day_df = df[df['trade_date'] == latest_trade_date].copy()
        if day_df.empty:
            raise ValueError(f'交易日 {latest_trade_date} 没有可用个股数据')

        stock_df = day_df[day_df['ts_code'].astype(str).eq(ts_code)].copy()
        if stock_df.empty:
            raise ValueError(f'未找到股票代码 {ts_code} 的最新交易日数据')

        numeric_cols = [col for col in required_cols if col not in {'ts_code', 'name', 'industry', 'area', 'trade_date', 'limit_status', 'is_lhb'}]
        for col in numeric_cols:
            stock_df[col] = pd.to_numeric(stock_df[col], errors='coerce')
        row = stock_df.iloc[0]

        def fmt_number(value, digits=2):
            if value is None or pd.isna(value):
                return None
            return round(float(value), digits)

        def fmt_percent(value, digits=2):
            if value is None or pd.isna(value):
                return None
            return round(float(value), digits)

        def safe_ratio(numerator, denominator, min_denominator=1e7):
            num = pd.to_numeric(pd.Series([numerator]), errors='coerce').iloc[0]
            den = pd.to_numeric(pd.Series([denominator]), errors='coerce').iloc[0]
            if pd.isna(num) or pd.isna(den) or den == 0 or abs(float(den)) < min_denominator:
                return None
            return float(num) / float(den)

        financial_panel = [
            {'label': '营收', 'value': fmt_number(row['fin_revenue'])},
            {'label': '净利', 'value': fmt_number(row['fin_n_income'])},
            {'label': '经营现金流', 'value': fmt_number(row['fin_n_cashflow_act'])},
            {'label': '毛利率', 'value': fmt_percent(row['fin_gross_margin'])},
            {'label': '净利率', 'value': fmt_percent(row['fin_net_margin'])},
            {'label': '资产负债率', 'value': fmt_percent(row['fin_debt_ratio'] * 100) if pd.notna(row['fin_debt_ratio']) else None},
            {'label': '净利/营收', 'value': fmt_percent(safe_ratio(row['fin_n_income'], row['fin_revenue'], min_denominator=0))},
        ]

        technical_panel = [
            {'label': 'RSI 6', 'value': fmt_number(row['rsi_6'])},
            {'label': 'RSI 12', 'value': fmt_number(row['rsi_12'])},
            {'label': 'RSI 24', 'value': fmt_number(row['rsi_24'])},
            {'label': 'MACD', 'value': fmt_number(row['macd'])},
            {'label': 'DIF', 'value': fmt_number(row['macd_dif'])},
            {'label': 'DEA', 'value': fmt_number(row['macd_dea'])},
            {'label': '换手率', 'value': fmt_percent(row['turnover_rate'])},
            {'label': '量比', 'value': fmt_number(row['volume_ratio'])},
            {'label': '20日收益', 'value': fmt_percent(row['f_ret_20d'])},
            {'label': '20日波动', 'value': fmt_percent(row['f_volatility_20d'])},
        ]

        moneyflow_panel = [
            {'label': '主力净流入', 'value': fmt_number(row['net_mf_amount'])},
            {'label': '大单买入', 'value': fmt_number(row['l_buy'])},
            {'label': '大单卖出', 'value': fmt_number(row['l_sell'])},
            {'label': '龙虎榜净额', 'value': fmt_number(row['lhb_net_amount'])},
            {'label': '龙虎榜净率', 'value': fmt_percent(row['lhb_net_rate'])},
            {'label': '封单强度', 'value': fmt_number(row['seal_strength'])},
            {'label': '机构吸筹', 'value': fmt_number(row['inst_accumulation_score_10'])},
            {'label': '价值动量', 'value': fmt_number(row['value_momentum'])},
        ]

        status_panel = [
            {'label': '涨跌幅', 'value': fmt_percent(row['pct_chg'])},
            {'label': '涨跌额', 'value': fmt_number(row['change'])},
            {'label': '成交额', 'value': fmt_number(row['amount'])},
            {'label': '成交量', 'value': fmt_number(row['vol'])},
            {'label': '涨停状态', 'value': row['limit_status'] or '--'},
            {'label': '是否龙虎榜', 'value': '是' if str(row['is_lhb']) in {'1', 'True', 'true'} else '否'},
            {'label': '筹码成本50%', 'value': fmt_number(row['cost_50pct'])},
            {'label': '价格/成本', 'value': fmt_number(row['price_to_cost'])},
        ]

        special_flags = {
            'pattern_first_limit': int(pd.to_numeric(pd.Series([row['pattern_first_limit']]), errors='coerce').fillna(0).iloc[0]),
            'pattern_multi_limit': int(pd.to_numeric(pd.Series([row['pattern_multi_limit']]), errors='coerce').fillna(0).iloc[0]),
            'pattern_bullish_engulfing': int(pd.to_numeric(pd.Series([row['pattern_bullish_engulfing']]), errors='coerce').fillna(0).iloc[0]),
            'consec_up_days': int(pd.to_numeric(pd.Series([row['consec_up_days']]), errors='coerce').fillna(0).iloc[0]),
        }

        overview = {
            'ts_code': row['ts_code'],
            'name': row['name'],
            'industry': row['industry'],
            'area': row['area'],
            'trade_date': latest_trade_date,
            'close': fmt_number(row['close']),
            'pct_chg': fmt_percent(row['pct_chg']),
            'amount': fmt_number(row['amount']),
            'pe_ttm': fmt_number(row['pe_ttm']),
            'pb': fmt_number(row['pb']),
            'ps_ttm': fmt_number(row['ps_ttm']),
            'dv_ttm': fmt_number(row['dv_ttm']),
        }

        def market_percentile(series, value, reverse=False, clip_upper=None):
            s = pd.to_numeric(series, errors='coerce').dropna()
            v = pd.to_numeric(pd.Series([value]), errors='coerce').iloc[0]
            if s.empty or pd.isna(v):
                return 0.0
            if clip_upper is not None:
                v = min(v, clip_upper)
            min_v = s.min()
            max_v = s.max()
            if max_v == min_v:
                return 0.5
            score = (v - min_v) / (max_v - min_v)
            score = float(max(0.0, min(1.0, score)))
            return 1 - score if reverse else score

        fin_revenue_q = day_df['fin_revenue'].quantile(0.75)
        fin_n_income_q = day_df['fin_n_income'].quantile(0.75)
        macd_scale = max(abs(day_df['macd'].quantile(0.95)), 1)
        mf_scale = max(abs(day_df['net_mf_amount'].quantile(0.95)), 1)
        vol_scale = max(day_df['volume_ratio'].quantile(0.95), 1)

        radar_chart = {
            'labels': ['估值', '成长', '技术', '资金'],
            'values': [
                float(pd.Series([
                    market_percentile(day_df['pe_ttm'], row['pe_ttm'], reverse=True),
                    market_percentile(day_df['pb'], row['pb'], reverse=True),
                ]).mean()),
                float(pd.Series([
                    market_percentile(day_df['fin_revenue'], row['fin_revenue']),
                    market_percentile(day_df['fin_n_income'], row['fin_n_income']),
                ]).mean()),
                float(pd.Series([
                    market_percentile(day_df['rsi_6'], row['rsi_6']),
                    market_percentile(day_df['macd'], row['macd']),
                    market_percentile(day_df['turnover_rate'], row['turnover_rate']),
                ]).mean()),
                float(pd.Series([
                    market_percentile(day_df['net_mf_amount'], row['net_mf_amount']),
                    market_percentile(day_df['volume_ratio'], row['volume_ratio']),
                ]).mean()),
            ],
        }

        return render_template(
            'stock_panorama.html',
            overview=overview,
            financial_panel=financial_panel,
            technical_panel=technical_panel,
            moneyflow_panel=moneyflow_panel,
            status_panel=status_panel,
            detail_rows=financial_panel + technical_panel + moneyflow_panel + status_panel,
            special_flags=special_flags,
            radar_chart=radar_chart,
            input_code=ts_code,
            latest_trade_date=latest_trade_date,
        )
    except Exception as exc:
        return render_template(
            'stock_panorama.html',
            overview=None,
            financial_panel=[],
            technical_panel=[],
            moneyflow_panel=[],
            status_panel=[],
            detail_rows=[],
            special_flags={},
            radar_chart={'labels': ['估值', '成长', '技术', '资金'], 'values': [0, 0, 0, 0]},
            input_code=request.args.get('ts_code', ''),
            latest_trade_date='',
            error=str(exc),
        )


@main_bp.route('/trial/moneyflow')
def moneyflow_stats():
    """主力资金流入流出统计页面"""
    data_path = Path(__file__).resolve().parents[2] / 'data' / 'data.parquet'

    try:
        if not data_path.exists():
            raise FileNotFoundError(f'数据文件不存在: {data_path}')

        df = pd.read_parquet(data_path)
        required_cols = [
            'ts_code', 'name', 'industry', 'trade_date', 'net_mf_amount',
            'buy_lg_amount', 'sell_lg_amount', 'buy_elg_amount', 'sell_elg_amount',
        ]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f'缺少必要字段: {", ".join(missing_cols)}')

        df = df.copy()
        df = df[df['industry'].notna()].copy()
        df['trade_date'] = df['trade_date'].astype(str)
        latest_trade_date = df['trade_date'].max()
        day_df = df[df['trade_date'] == latest_trade_date].copy()
        day_df = day_df[day_df['net_mf_amount'].notna()].copy()

        if day_df.empty:
            raise ValueError(f'交易日 {latest_trade_date} 没有可用资金流数据')

        numeric_cols = [
            'net_mf_amount',
            'buy_lg_amount',
            'sell_lg_amount',
            'buy_elg_amount',
            'sell_elg_amount',
        ]
        for col in numeric_cols:
            day_df[col] = pd.to_numeric(day_df[col], errors='coerce').fillna(0.0)

        day_df['lg_net_amount'] = day_df['buy_lg_amount'] - day_df['sell_lg_amount']
        day_df['elg_net_amount'] = day_df['buy_elg_amount'] - day_df['sell_elg_amount']

        top_inflow = (
            day_df.sort_values('net_mf_amount', ascending=False)
            .head(20)[['ts_code', 'name', 'industry', 'net_mf_amount', 'lg_net_amount', 'elg_net_amount']]
            .copy()
        )
        bottom_outflow = (
            day_df.sort_values('net_mf_amount', ascending=True)
            .head(20)[['ts_code', 'name', 'industry', 'net_mf_amount', 'lg_net_amount', 'elg_net_amount']]
            .copy()
        )

        industry_df = (
            day_df.groupby('industry', dropna=False)
            .agg(
                stock_count=('ts_code', 'count'),
                net_mf_amount=('net_mf_amount', 'sum'),
                lg_buy_amount=('buy_lg_amount', 'sum'),
                lg_sell_amount=('sell_lg_amount', 'sum'),
                elg_buy_amount=('buy_elg_amount', 'sum'),
                elg_sell_amount=('sell_elg_amount', 'sum'),
            )
            .reset_index()
        )
        industry_df['lg_net_amount'] = industry_df['lg_buy_amount'] - industry_df['lg_sell_amount']
        industry_df['elg_net_amount'] = industry_df['elg_buy_amount'] - industry_df['elg_sell_amount']
        industry_df = industry_df.sort_values('net_mf_amount', ascending=False).reset_index(drop=True)

        summary = {
            'trade_date': latest_trade_date,
            'stock_count': int(len(day_df)),
            'industry_count': int(industry_df['industry'].nunique()),
            'total_net_mf_amount': float(day_df['net_mf_amount'].sum()),
            'positive_stock_count': int((day_df['net_mf_amount'] > 0).sum()),
            'negative_stock_count': int((day_df['net_mf_amount'] < 0).sum()),
        }

        return render_template(
            'moneyflow_stats.html',
            summary=summary,
            top_inflow=top_inflow.where(top_inflow.notna(), None).to_dict(orient='records'),
            bottom_outflow=bottom_outflow.where(bottom_outflow.notna(), None).to_dict(orient='records'),
            industry_rows=industry_df.where(industry_df.notna(), None).to_dict(orient='records'),
        )
    except Exception as exc:
        return render_template(
            'moneyflow_stats.html',
            summary={
                'trade_date': '',
                'stock_count': 0,
                'industry_count': 0,
                'total_net_mf_amount': 0.0,
                'positive_stock_count': 0,
                'negative_stock_count': 0,
            },
            top_inflow=[],
            bottom_outflow=[],
            industry_rows=[],
            error=str(exc),
        )


def inspect_data_management_status():
    connected, existing_tables, non_empty_tables = inspect_parquet_data_assets()

    return build_health_report(
        current_app.config,
        connected=connected,
        existing_tables=existing_tables,
        non_empty_tables=non_empty_tables,
    )


@main_bp.route('/data-management')
def data_management():
    """数据管理页面"""
    return render_template(
        'data_management/index.html',
        initialization_status=inspect_data_management_status(),
    )

@main_bp.route('/test-simple-chart')
def test_simple_chart():
    """简单图表测试页面"""
    with open('test_simple_chart.html', 'r', encoding='utf-8') as f:
        return f.read()

@main_bp.route('/api-test')
def api_test():
    """API测试页面"""
    return render_template('api_test.html')





 
