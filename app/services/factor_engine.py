import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import re
from scipy import stats
from loguru import logger

from app.services.factor_expression_engine import FactorExpressionEngine
from app.services.data_reader import ParquetDataReader
from app.services.parquet_state_store import FactorRepository, ParquetStateStore


def _get_data_reader() -> ParquetDataReader:
    """延迟创建 ParquetDataReader 单例。"""
    if not hasattr(_get_data_reader, '_instance'):
        _get_data_reader._instance = ParquetDataReader()
    return _get_data_reader._instance


class FactorEngine:
    """因子计算引擎"""

    def __init__(self, state_store: ParquetStateStore = None):
        self.factor_definitions = {}
        self.builtin_factors = {}
        self.expression_engine = FactorExpressionEngine()
        self.data_reader = _get_data_reader()
        self.state_store = state_store or ParquetStateStore()
        self.factor_repo = FactorRepository(self.state_store)
        self._open_trade_dates_cache = None
        self._init_builtin_factors()
        self.load_factor_definitions()
    
    def _init_builtin_factors(self):
        """初始化内置因子"""
        self.builtin_factors = {
            # 技术面因子
            'momentum_1d': self._momentum_factor,
            'momentum_5d': self._momentum_factor,
            'momentum_20d': self._momentum_factor,
            'volatility_20d': self._volatility_factor,
            'volume_ratio_20d': self._volume_ratio_factor,
            'price_to_ma20': self._price_to_ma_factor,
            
            # 基本面因子
            'pe_percentile': self._pe_percentile_factor,
            'pb_percentile': self._pb_percentile_factor,
            'ps_percentile': self._ps_percentile_factor,
            'roe_ttm': self._roe_factor,
            'roa_ttm': self._roa_factor,
            'revenue_growth': self._revenue_growth_factor,
            'profit_growth': self._profit_growth_factor,
            
            # 资金面因子
            'money_flow_strength': self._money_flow_strength_factor,
            'big_order_ratio': self._big_order_ratio_factor,
            'money_flow_momentum': self._money_flow_momentum_factor,
            
            # 筹码面因子
            'chip_concentration': self._chip_concentration_factor,
            'winner_rate_change': self._winner_rate_change_factor,
        }
    
    def load_factor_definitions(self):
        """加载因子定义"""
        try:
            definitions = self.factor_repo.list_definitions(include_inactive=False)
            self.factor_definitions = {
                definition["factor_id"]: definition
                for definition in definitions
            }
            logger.info(f"加载了 {len(self.factor_definitions)} 个自定义因子定义")
        except Exception as e:
            logger.error(f"加载因子定义失败: {e}")
    
    def register_factor(self, factor_id: str, factor_name: str, formula: str, 
                       factor_type: str, description: str = None, params: dict = None):
        """注册自定义因子"""
        try:
            self.factor_repo.upsert_definition(
                {
                    "factor_id": factor_id,
                    "factor_name": factor_name,
                    "factor_formula": formula,
                    "factor_type": factor_type,
                    "description": description,
                    "params": params or {},
                    "is_active": True,
                }
            )
            self.load_factor_definitions()
            logger.info(f"成功注册因子: {factor_id}")
            return True
        except Exception as e:
            logger.error(f"注册因子失败: {factor_id}, 错误: {e}")
            return False

    def get_custom_factor_capabilities(self) -> Dict[str, Any]:
        """返回自定义因子表达式白名单能力，用于前端展示和接口契约。"""
        return {
            "allowed_columns": sorted(self.expression_engine.allowed_columns),
            "allowed_series_methods": sorted(self.expression_engine.allowed_series_methods),
            "allowed_window_methods": sorted(self.expression_engine.allowed_window_methods),
            "allowed_functions": sorted(self.expression_engine.allowed_functions.keys()),
            "examples": [
                "close.pct_change(5)",
                "abs(close - open)",
                "close.rolling(20).mean() - close",
                "vol.rolling(10).std()",
            ],
        }

    def get_builtin_factor_validation_samples(self) -> List[Dict[str, Any]]:
        """返回核心内置因子的样例级验收说明。"""
        return [
            {
                "factor_id": "momentum_5d",
                "factor_name": "5日动量",
                "required_fields": ["close"],
                "calculation_rule": "close.pct_change(5)，即当前收盘价相对5个交易日前收盘价的涨跌幅。",
                "sample_expectation": "若 close=[10,11,12,13,14,15]，最后一个样例值应为 15/10-1=0.5。",
            },
            {
                "factor_id": "volatility_20d",
                "factor_name": "20日波动率",
                "required_fields": ["close"],
                "calculation_rule": "先计算 daily_return=close.pct_change()，再取 rolling(20).std()。",
                "sample_expectation": "至少需要21个收盘价样本，最后一个值应等于最近20个日收益率的标准差。",
            },
            {
                "factor_id": "volume_ratio_20d",
                "factor_name": "20日量比",
                "required_fields": ["vol"],
                "calculation_rule": "volume_ratio = 当日成交量 / 最近20日成交量均值。",
                "sample_expectation": "若最后20日均量为 11.5、当日量为 21，则样例值应为 21/11.5。",
            },
            {
                "factor_id": "price_to_ma20",
                "factor_name": "价格相对20日均线",
                "required_fields": ["close"],
                "calculation_rule": "price_to_ma = close / close.rolling(20).mean() - 1。",
                "sample_expectation": "若最近20日均价为 11.5、当日收盘价为 21，则样例值应为 21/11.5-1。",
            },
            {
                "factor_id": "money_flow_strength",
                "factor_name": "资金流向强度",
                "required_fields": [
                    "buy_sm_amount",
                    "buy_md_amount",
                    "buy_lg_amount",
                    "buy_elg_amount",
                    "sell_lg_amount",
                    "sell_elg_amount",
                ],
                "calculation_rule": "((buy_lg_amount+buy_elg_amount)-(sell_lg_amount+sell_elg_amount)) / (buy_sm_amount+buy_md_amount+buy_lg_amount+buy_elg_amount)。",
                "sample_expectation": "若大单净流入为 625、分母为 1000，则样例值应为 0.625。",
            },
        ]

    def validate_custom_factor_formula(self, formula: str) -> Dict[str, Any]:
        """校验自定义因子公式是否符合表达式白名单。"""
        sample_df = pd.DataFrame(
            {
                "open": [10, 11, 12, 13, 14],
                "high": [11, 12, 13, 14, 15],
                "low": [9, 10, 11, 12, 13],
                "close": [10, 11, 12, 13, 14],
                "pre_close": [9, 10, 11, 12, 13],
                "change_c": [1, 1, 1, 1, 1],
                "pct_chg": [0.1, 0.1, 0.09, 0.08, 0.07],
                "vol": [100, 110, 120, 130, 140],
                "amount": [1000, 1100, 1200, 1300, 1400],
            }
        )

        try:
            self.expression_engine.evaluate((formula or "").strip(), sample_df)
            return {"valid": True, "error": None}
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    def calculate_factor(self, factor_id: str, ts_codes: List[str], 
                        start_date: str, end_date: str) -> pd.DataFrame:
        """计算指定因子值"""
        try:
            result = pd.DataFrame()
            
            # 检查是否为内置因子
            if factor_id in self.builtin_factors:
                result = self._calculate_builtin_factor(factor_id, ts_codes, start_date, end_date)
            
            # 检查是否为自定义因子
            elif factor_id in self.factor_definitions:
                result = self._calculate_custom_factor(factor_id, ts_codes, start_date, end_date)
            
            else:
                logger.warning(f"未找到因子定义: {factor_id}")
                return pd.DataFrame()
            
            # 计算百分位排名和Z分数
            if not result.empty:
                result = self._calculate_factor_stats(result, start_date)
                logger.info(f"成功计算因子 {factor_id}: {len(result)} 条记录")
            
            return result
            
        except Exception as e:
            logger.error(f"计算因子失败: {factor_id}, 错误: {e}")
            return pd.DataFrame()
    
    def _calculate_builtin_factor(self, factor_id: str, ts_codes: List[str], 
                                 start_date: str, end_date: str) -> pd.DataFrame:
        """计算内置因子"""
        factor_func = self.builtin_factors[factor_id]
        
        # 根据因子类型获取所需数据
        data = self._get_factor_data(factor_id, ts_codes, start_date, end_date)
        
        # 计算因子值
        result = factor_func(data, factor_id)

        # 统一按请求区间过滤：基本面因子现在逐期落库全部历史快照，
        # 不兜底过滤的话每次全量计算都会重复写入区间外的历史行
        if not result.empty and "trade_date" in result.columns:
            start_dt = pd.to_datetime(start_date, errors="coerce")
            end_dt = pd.to_datetime(end_date, errors="coerce")
            td = pd.to_datetime(result["trade_date"], errors="coerce")
            mask = td.notna()
            if pd.notna(start_dt):
                mask &= td >= start_dt
            if pd.notna(end_dt):
                mask &= td <= end_dt
            result = result[mask]

        return result
    
    def _get_factor_data(self, factor_id: str, ts_codes: List[str], 
                        start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """获取计算因子所需的数据"""
        data = {}

        # 扩展日期范围以获取足够的历史数据
        extended_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=252)).strftime('%Y-%m-%d')

        try:
            # 基础行情数据
            # 收益率类因子必须用后复权价：不复权 close 在除权除息日有假缺口，
            # 10送10 会被算成 -50% 动量。价格比值类（price_to_ma）对比值无影响，一并复权保持口径统一。
            if any(x in factor_id for x in ['momentum', 'volatility', 'volume', 'price']):
                history_data = self.data_reader.get_return_prices(
                    ts_codes=ts_codes, start_date=extended_start, end_date=end_date
                )
                data['history'] = history_data
                logger.info(f"获取历史数据: {len(history_data)} 条记录")

            # 基本面数据
            if any(x in factor_id for x in ['pe', 'pb', 'ps']):
                basic_data = self.data_reader.get_daily_basic(
                    ts_codes=ts_codes, start_date=start_date, end_date=end_date
                )
                data['basic'] = basic_data

            # 技术因子数据
            if 'ma' in factor_id:
                factor_data = self.data_reader.get_stk_factor(
                    ts_codes=ts_codes, start_date=start_date, end_date=end_date
                )
                data['factor'] = factor_data

            # 资金流向数据
            if 'money' in factor_id:
                money_data = self.data_reader.get_moneyflow(
                    ts_codes=ts_codes, start_date=extended_start, end_date=end_date
                )
                data['moneyflow'] = money_data

            # 筹码数据
            if 'chip' in factor_id or 'winner' in factor_id:
                cyq_data = self.data_reader.get_cyq_perf(
                    ts_codes=ts_codes, start_date=extended_start, end_date=end_date
                )
                data['cyq'] = cyq_data

            # 财务数据
            if any(x in factor_id for x in ['roe', 'roa', 'revenue', 'profit']):
                income_data = self.data_reader.get_income_statement(ts_codes)
                data['income'] = income_data

                balance_data = self.data_reader.get_balance_sheet(ts_codes)
                data['balance'] = balance_data
            
        except Exception as e:
            logger.error(f"获取因子数据失败: {e}")
        
        return data
    
    # ==================== 内置因子计算函数 ====================
    
    def _momentum_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """动量因子：计算N日收益率"""
        if 'history' not in data or data['history'].empty:
            return pd.DataFrame()
        
        # 提取周期参数
        period = int(factor_id.split('_')[1].replace('d', ''))
        
        df = data['history'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data[f'return_{period}d'] = stock_data['close'].pct_change(period)
            
            # 只保留指定日期范围的数据
            result_list.append(stock_data[['ts_code', 'trade_date', f'return_{period}d']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={f'return_{period}d': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _volatility_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """波动率因子：计算N日收益率标准差"""
        if 'history' not in data or data['history'].empty:
            return pd.DataFrame()
        
        period = int(factor_id.split('_')[1].replace('d', ''))
        
        df = data['history'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data['daily_return'] = stock_data['close'].pct_change()
            stock_data[f'volatility_{period}d'] = stock_data['daily_return'].rolling(period).std()
            
            result_list.append(stock_data[['ts_code', 'trade_date', f'volatility_{period}d']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={f'volatility_{period}d': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _volume_ratio_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """成交量比率因子"""
        if 'history' not in data or data['history'].empty:
            return pd.DataFrame()
        
        period = int(factor_id.split('_')[2].replace('d', ''))
        
        df = data['history'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data['vol_ma'] = stock_data['vol'].rolling(period).mean()
            stock_data['volume_ratio'] = stock_data['vol'] / stock_data['vol_ma']
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'volume_ratio']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'volume_ratio': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _price_to_ma_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """价格相对均线因子"""
        if 'history' not in data or data['history'].empty:
            return pd.DataFrame()
        
        period = int(factor_id.split('ma')[1])
        
        df = data['history'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data[f'ma{period}'] = stock_data['close'].rolling(period).mean()
            stock_data['price_to_ma'] = stock_data['close'] / stock_data[f'ma{period}'] - 1
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'price_to_ma']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'price_to_ma': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _pe_percentile_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """PE历史分位数因子"""
        if 'basic' not in data or data['basic'].empty:
            return pd.DataFrame()
        
        df = data['basic'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data = stock_data[stock_data['pe_ttm'].notna() & (stock_data['pe_ttm'] > 0)]
            
            if len(stock_data) > 20:  # 至少需要20个数据点
                stock_data['pe_percentile'] = stock_data['pe_ttm'].rolling(252, min_periods=20).apply(
                    lambda x: stats.percentileofscore(x, x.iloc[-1]) / 100
                )
                result_list.append(stock_data[['ts_code', 'trade_date', 'pe_percentile']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'pe_percentile': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _pb_percentile_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """PB历史分位数因子"""
        if 'basic' not in data or data['basic'].empty:
            return pd.DataFrame()
        
        df = data['basic'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data = stock_data[stock_data['pb'].notna() & (stock_data['pb'] > 0)]
            
            if len(stock_data) > 20:
                stock_data['pb_percentile'] = stock_data['pb'].rolling(252, min_periods=20).apply(
                    lambda x: stats.percentileofscore(x, x.iloc[-1]) / 100
                )
                result_list.append(stock_data[['ts_code', 'trade_date', 'pb_percentile']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'pb_percentile': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _ps_percentile_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """PS历史分位数因子"""
        if 'basic' not in data or data['basic'].empty:
            return pd.DataFrame()
        
        df = data['basic'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            stock_data = stock_data[stock_data['ps_ttm'].notna() & (stock_data['ps_ttm'] > 0)]
            
            if len(stock_data) > 20:
                stock_data['ps_percentile'] = stock_data['ps_ttm'].rolling(252, min_periods=20).apply(
                    lambda x: stats.percentileofscore(x, x.iloc[-1]) / 100
                )
                result_list.append(stock_data[['ts_code', 'trade_date', 'ps_percentile']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'ps_percentile': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _point_in_time_stamp(self, *report_rows) -> Optional[str]:
        """财务因子的打点日期：取所用报告的公告日（ann_date/f_ann_date）中最晚的一个。

        报告期 end_date（如年报的 12-31）比实际公告日早数月，直接用 end_date
        打点会让回测提前"看到"业绩（未来函数），因此必须用公告日；
        同一报表的 ann_date 与 f_ann_date 不一致时取孰晚（更保守），
        公告日缺失时退回 end_date。
        """
        def _field(row, col):
            # 兼容 dict（原始行）与 namedtuple（itertuples 切片窗口）
            if hasattr(row, 'get'):
                return row.get(col)
            return getattr(row, col, None)

        stamps = []
        for row in report_rows:
            if row is None:
                continue
            candidates = []
            for col in ('f_ann_date', 'ann_date'):
                val = _field(row, col)
                ts = pd.to_datetime(val, errors="coerce", format="mixed") if val is not None else pd.NaT
                if val is not None and pd.notna(ts) and str(val).strip():
                    candidates.append(ts)
            if candidates:
                stamps.append(max(candidates))
            else:
                end_val = _field(row, 'end_date')
                end_ts = pd.to_datetime(end_val, errors="coerce", format="mixed") if end_val is not None else pd.NaT
                if end_val is not None and pd.notna(end_ts) and str(end_val).strip():
                    stamps.append(end_ts)
        if not stamps:
            return None
        # 统一输出 YYYY-MM-DD，避免混合格式字符串参与后续比较
        return max(stamps).strftime("%Y-%m-%d")

    def _snap_to_trade_date(self, date_text: str) -> Optional[str]:
        """把公告日向后对齐到第一个交易日。

        财报公告经常落在周末/节假日，而因子查询按 trade_date 精确匹配，
        不对齐会导致这些快照永远查不到。
        """
        try:
            ts = pd.to_datetime(date_text)
        except (TypeError, ValueError):
            return None
        if pd.isna(ts):
            return None

        if self._open_trade_dates_cache is None:
            try:
                cal = self.data_reader.get_trade_calendar()
                is_open = pd.to_numeric(cal.get("is_open"), errors="coerce") == 1
                dates = pd.to_datetime(
                    cal.loc[is_open, "cal_date"].astype(str), format="%Y%m%d", errors="coerce"
                ).dropna()
                self._open_trade_dates_cache = np.sort(dates.unique())
            except Exception as e:
                logger.warning(f"读取交易日历失败，公告日不对齐: {e}")
                self._open_trade_dates_cache = np.array([], dtype="datetime64[ns]")

        arr = self._open_trade_dates_cache
        if arr.size == 0:
            return ts.strftime("%Y-%m-%d")

        # 公告日落在日历覆盖范围之外时退回原始日期：
        # 本地交易日历只覆盖近年，历史公告日若强行 searchsorted
        # 会被对齐到日历第一天（如 2016 年公告被推到 2024 年），严重失真
        idx = int(np.searchsorted(arr, np.datetime64(ts)))
        if idx >= arr.size or ts < pd.Timestamp(arr[0]):
            return ts.strftime("%Y-%m-%d")
        return pd.Timestamp(arr[idx]).strftime("%Y-%m-%d")

    def _prepare_quarterly_reports(self, df: pd.DataFrame, value_cols: List[str]) -> pd.DataFrame:
        """整理季度报表：按报告期升序去重，数值列转 numeric。

        - 本地 parquet 的日期是 YYYYMMDD 与 YYYY-MM-DD 混存，必须用 format='mixed'
          解析，默认格式推断会把第二种格式静默变成 NaT
        - report_type=2 是单季度表、4 是调整表，与累计口径混算会污染 TTM，
          有该列时只保留 report_type=1（合并报表累计值）
        """
        cols = ["ts_code", "end_date"] + [c for c in value_cols if c in df.columns]
        extra = [c for c in ("f_ann_date", "ann_date") if c in df.columns]
        if "report_type" in df.columns:
            extra.append("report_type")
        out = df[list(dict.fromkeys(cols + extra))].copy()
        if "report_type" in out.columns:
            out = out[out["report_type"].astype(str) == "1"]
        out["end_date"] = pd.to_datetime(out["end_date"], errors="coerce", format="mixed")
        out = out.dropna(subset=["end_date"])
        # 同一报表期存在多版本（修正公告）时按最新公告日取舍，
        # 避免依赖 parquet 原始行序这种任意因素
        ann_sort_cols = [
            c for c in ("f_ann_date", "ann_date")
            if c in out.columns
        ]
        if ann_sort_cols:
            for col in ann_sort_cols:
                out[col + "_sort"] = pd.to_datetime(out[col], errors="coerce", format="mixed")
            out = out.sort_values(
                ["ts_code", "end_date"] + [c + "_sort" for c in ann_sort_cols],
                na_position="first",
            ).reset_index(drop=True)
            out = out.drop(columns=[c + "_sort" for c in ann_sort_cols])
        else:
            out = out.sort_values(["ts_code", "end_date"]).reset_index(drop=True)
        out = out.drop_duplicates(subset=["ts_code", "end_date"], keep="last")
        for col in [c for c in value_cols if c in out.columns]:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        return out.sort_values(["ts_code", "end_date"]).reset_index(drop=True)

    def _snapshot_stamp(self, rows: List[Any]) -> Optional[str]:
        """取所用报表公告日的孰晚值，并对齐到交易日。"""
        stamps = [self._point_in_time_stamp(r) for r in rows]
        stamps = [s for s in stamps if s]
        if not stamps:
            return None
        return self._snap_to_trade_date(max(stamps))

    def _ttm_level_factor(self, data: Dict[str, pd.DataFrame], factor_id: str,
                          income_col: str, balance_col: str) -> pd.DataFrame:
        """ROE/ROA 类 TTM 水平因子：逐季度生成 point-in-time 快照。

        旧实现只对每股最新一期落库一条记录，导致历史任意日期都查不到
        基本面因子，历史选股实际退化成纯技术面。这里改为每期公告后
        生成一条快照，trade_date 取所用报表公告日（对齐到交易日）。
        """
        if data.get("income") is None or data["income"].empty:
            return pd.DataFrame()
        income_df = self._prepare_quarterly_reports(data["income"], [income_col])
        if income_df.empty or income_col not in income_df.columns:
            return pd.DataFrame()

        balance_df = None
        if data.get("balance") is not None and not data["balance"].empty:
            balance_df = self._prepare_quarterly_reports(data["balance"], [balance_col])

        results = []
        for ts_code, inc in income_df.groupby("ts_code", sort=False):
            bal = None
            if balance_df is not None and not balance_df.empty:
                bal = balance_df[balance_df["ts_code"] == ts_code].reset_index(drop=True)
                if bal.empty:
                    continue

            for i in range(3, len(inc)):
                window = inc.iloc[i - 3:i + 1]
                if window[income_col].isna().any():
                    continue  # 任一季度缺失则该期 TTM 不成立
                ttm = float(window[income_col].sum())

                cur_end = inc.iloc[i]["end_date"]
                if bal is None or len(bal) == 0:
                    continue
                b_window = bal[bal["end_date"] <= cur_end].tail(2)
                if len(b_window) < 2 or b_window[balance_col].isna().any():
                    continue
                avg_denom = float(b_window[balance_col].mean())
                if avg_denom <= 0:
                    continue

                stamp = self._snapshot_stamp(list(window.itertuples()) + list(b_window.itertuples()))
                if stamp is None:
                    continue

                results.append({
                    "ts_code": ts_code,
                    "trade_date": stamp,
                    "factor_value": ttm / avg_denom,
                })

        if not results:
            return pd.DataFrame()
        result = pd.DataFrame(results)
        # 年报与一季报同日公告时同一 trade_date 会产生两条快照，
        # 保留后者（报告期更新、信息集更完整）
        result = result.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
        result["factor_id"] = factor_id
        return result[["ts_code", "trade_date", "factor_id", "factor_value"]]

    def _yoy_ttm_growth_factor(self, data: Dict[str, pd.DataFrame], factor_id: str,
                               income_col: str) -> pd.DataFrame:
        """同比增长类因子：TTM vs 去年同期 TTM，逐期 point-in-time 快照。"""
        if data.get("income") is None or data["income"].empty:
            return pd.DataFrame()
        income_df = self._prepare_quarterly_reports(data["income"], [income_col])
        if income_df.empty or income_col not in income_df.columns:
            return pd.DataFrame()

        results = []
        for ts_code, inc in income_df.groupby("ts_code", sort=False):
            for i in range(7, len(inc)):
                current = inc.iloc[i - 3:i + 1]
                previous = inc.iloc[i - 7:i - 3]
                if current[income_col].isna().any() or previous[income_col].isna().any():
                    continue
                prev_ttm = float(previous[income_col].sum())
                if prev_ttm <= 0:
                    continue
                growth = (float(current[income_col].sum()) - prev_ttm) / prev_ttm

                stamp = self._snapshot_stamp(list(current.itertuples()))
                if stamp is None:
                    continue

                results.append({
                    "ts_code": ts_code,
                    "trade_date": stamp,
                    "factor_value": growth,
                })

        if not results:
            return pd.DataFrame()
        result = pd.DataFrame(results)
        # 年报与一季报同日公告时同一 trade_date 会产生两条快照，
        # 保留后者（报告期更新、信息集更完整）
        result = result.drop_duplicates(subset=["ts_code", "trade_date"], keep="last")
        result["factor_id"] = factor_id
        return result[["ts_code", "trade_date", "factor_id", "factor_value"]]

    def _roe_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """ROE因子（TTM，按公告日逐期快照）"""
        return self._ttm_level_factor(data, factor_id, "n_income_attr_p", "total_hldr_eqy_exc_min_int")

    def _roa_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """ROA因子（TTM，按公告日逐期快照）"""
        return self._ttm_level_factor(data, factor_id, "n_income_attr_p", "total_assets")

    def _revenue_growth_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """营收增长率因子（TTM同比，按公告日逐期快照）"""
        return self._yoy_ttm_growth_factor(data, factor_id, "revenue")

    def _profit_growth_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """利润增长率因子（TTM同比，按公告日逐期快照）"""
        return self._yoy_ttm_growth_factor(data, factor_id, "n_income_attr_p")

    def _money_flow_strength_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """资金流向强度因子"""
        if 'moneyflow' not in data or data['moneyflow'].empty:
            return pd.DataFrame()
        
        df = data['moneyflow'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            
            # 计算大单净流入强度
            stock_data['big_net_amount'] = (stock_data['buy_lg_amount'] + stock_data['buy_elg_amount']) - \
                                         (stock_data['sell_lg_amount'] + stock_data['sell_elg_amount'])
            
            # 计算总成交额
            stock_data['total_amount'] = (stock_data['buy_sm_amount'] + stock_data['buy_md_amount'] + 
                                        stock_data['buy_lg_amount'] + stock_data['buy_elg_amount'])
            
            # 计算资金流向强度
            stock_data['money_flow_strength'] = stock_data['big_net_amount'] / stock_data['total_amount']
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'money_flow_strength']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'money_flow_strength': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _big_order_ratio_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """大单占比因子"""
        if 'moneyflow' not in data or data['moneyflow'].empty:
            return pd.DataFrame()
        
        df = data['moneyflow'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            
            # 计算大单总额
            stock_data['big_amount'] = stock_data['buy_lg_amount'] + stock_data['sell_lg_amount'] + \
                                     stock_data['buy_elg_amount'] + stock_data['sell_elg_amount']
            
            # 计算总成交额
            stock_data['total_amount'] = (stock_data['buy_sm_amount'] + stock_data['sell_sm_amount'] +
                                        stock_data['buy_md_amount'] + stock_data['sell_md_amount'] +
                                        stock_data['buy_lg_amount'] + stock_data['sell_lg_amount'] +
                                        stock_data['buy_elg_amount'] + stock_data['sell_elg_amount'])
            
            # 计算大单占比
            stock_data['big_order_ratio'] = stock_data['big_amount'] / stock_data['total_amount']
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'big_order_ratio']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'big_order_ratio': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _money_flow_momentum_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """资金流向动量因子"""
        if 'moneyflow' not in data or data['moneyflow'].empty:
            return pd.DataFrame()
        
        df = data['moneyflow'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            
            # 计算5日资金流向动量
            stock_data['net_flow_5d'] = stock_data['net_mf_amount'].rolling(5).sum()
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'net_flow_5d']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'net_flow_5d': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _chip_concentration_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """筹码集中度因子"""
        if 'cyq' not in data or data['cyq'].empty:
            return pd.DataFrame()
        
        df = data['cyq'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            
            # 计算筹码集中度：90%筹码的价格区间相对中位数的比例
            stock_data['chip_concentration'] = (stock_data['cost_95pct'] - stock_data['cost_5pct']) / stock_data['cost_50pct']
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'chip_concentration']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'chip_concentration': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _winner_rate_change_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """胜率变化因子"""
        if 'cyq' not in data or data['cyq'].empty:
            return pd.DataFrame()
        
        df = data['cyq'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        result_list = []
        for ts_code in df['ts_code'].unique():
            stock_data = df[df['ts_code'] == ts_code].sort_values('trade_date')
            
            # 计算胜率5日变化
            stock_data['winner_rate_change'] = stock_data['winner_rate'].diff(5)
            
            result_list.append(stock_data[['ts_code', 'trade_date', 'winner_rate_change']])
        
        if result_list:
            result = pd.concat(result_list, ignore_index=True)
            result = result.rename(columns={'winner_rate_change': 'factor_value'})
            result['factor_id'] = factor_id
            return result[['ts_code', 'trade_date', 'factor_id', 'factor_value']].dropna()
        
        return pd.DataFrame()
    
    def _filter_universe_asof(self, basic_df: pd.DataFrame, trade_date: str) -> List[str]:
        """按历史时点过滤股票池，消除幸存者偏差与次新股污染。

        - 剔除 trade_date 之后才上市的股票（次新股上市初期波动特殊）
        - 剔除 trade_date 之前已退市的股票（依赖 stock_basic 中的 delist_date，
          需重新下载包含 L/D/P 全部状态的 stock_basic 数据后生效）
        """
        if basic_df.empty or "ts_code" not in basic_df.columns:
            return []
        try:
            td = pd.to_datetime(trade_date)
        except (TypeError, ValueError):
            return basic_df["ts_code"].tolist()

        mask = pd.Series(True, index=basic_df.index)
        if "list_date" in basic_df.columns:
            list_dates = pd.to_datetime(basic_df["list_date"], errors="coerce")
            mask &= list_dates.notna() & (list_dates <= td)
        if "delist_date" in basic_df.columns:
            delist_dates = pd.to_datetime(basic_df["delist_date"], errors="coerce")
            # delist_date 缺失视为未退市
            mask &= ~(delist_dates.notna() & (delist_dates <= td))
        return basic_df.loc[mask, "ts_code"].tolist()

    def calculate_all_factors(self, trade_date: str, ts_codes: List[str] = None) -> pd.DataFrame:
        """计算所有因子的当日值"""
        try:
            if ts_codes is None:
                # 获取所有活跃股票，并按回看时点过滤（退市股/未来上市股不参与）
                basic_df = self.data_reader.get_stock_basic()
                ts_codes = self._filter_universe_asof(basic_df, trade_date)
            
            all_results = []
            
            # 计算内置因子
            for factor_id in self.builtin_factors.keys():
                try:
                    result = self.calculate_factor(factor_id, ts_codes, trade_date, trade_date)
                    if not result.empty:
                        all_results.append(result)
                except Exception as e:
                    logger.error(f"计算内置因子失败: {factor_id}, 错误: {e}")
            
            # 计算自定义因子
            for factor_id in self.factor_definitions.keys():
                try:
                    result = self.calculate_factor(factor_id, ts_codes, trade_date, trade_date)
                    if not result.empty:
                        all_results.append(result)
                except Exception as e:
                    logger.error(f"计算自定义因子失败: {factor_id}, 错误: {e}")
            
            if all_results:
                final_result = pd.concat(all_results, ignore_index=True)
                
                # 计算百分位排名和Z分数
                final_result = self._calculate_factor_stats(final_result, trade_date)
                
                return final_result
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"计算所有因子失败: {e}")
            return pd.DataFrame()
    
    def _calculate_factor_stats(self, df: pd.DataFrame, trade_date: str = None) -> pd.DataFrame:
        """计算因子的百分位排名和Z分数（按因子+交易日的截面）。

        横截面统计必须限定在单一 trade_date 内：跨日期池化会让历史某天的
        z-score/rank 混入未来日期的分布（未来函数）。trade_date 参数保留以
        兼容旧调用方，实际分组以数据自身的 trade_date 列为准。
        """
        try:
            if df.empty:
                return df

            result = df.copy()
            # 列始终存在，避免不同批次的 schema 漂移
            result['percentile_rank'] = np.nan
            result['z_score'] = np.nan

            group_cols = ['factor_id', 'trade_date']
            result['percentile_rank'] = result.groupby(group_cols)['factor_value'].rank(pct=True) * 100
            group_std = result.groupby(group_cols)['factor_value'].transform('std')
            group_mean = result.groupby(group_cols)['factor_value'].transform('mean')
            result['z_score'] = np.where(
                group_std.fillna(0) > 0,
                (result['factor_value'] - group_mean) / group_std.replace(0, np.nan),
                0.0,
            )

            return result

        except Exception as e:
            logger.error(f"计算因子统计量失败: {e}")
            return df
    
    def save_factor_values(self, df: pd.DataFrame) -> bool:
        """保存因子值到数据库"""
        try:
            if df.empty:
                return True
            written = self.factor_repo.save_values(df)
            logger.info(f"成功保存 {written} 条因子值记录")
            return True
            
        except Exception as e:
            logger.error(f"保存因子值失败: {e}")
            return False
    
    def get_factor_exposure(self, factor_id: str, trade_date: str) -> pd.DataFrame:
        """获取因子暴露度"""
        try:
            result = self.factor_repo.get_values(factor_ids=[factor_id], trade_date=trade_date)
            if not result.empty and "z_score" in result.columns:
                result = result.sort_values("z_score", ascending=False).reset_index(drop=True)
            return result

        except Exception as e:
            logger.error(f"获取因子暴露度失败: {factor_id}, {trade_date}, 错误: {e}")
            return pd.DataFrame()
    
    def _calculate_custom_factor(self, factor_id: str, ts_codes: List[str], 
                                start_date: str, end_date: str) -> pd.DataFrame:
        """计算自定义因子（表达式白名单）"""
        try:
            if factor_id not in self.factor_definitions:
                return pd.DataFrame()
            if not ts_codes:
                return pd.DataFrame()

            definition = self.factor_definitions[factor_id]
            formula = (definition.get("factor_formula") or "").strip()
            if not formula:
                logger.warning(f"自定义因子未配置公式: {factor_id}")
                return pd.DataFrame()

            extended_start = (
                datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=252)
            ).strftime("%Y-%m-%d")

            history_df = self.data_reader.get_daily(
                ts_codes=ts_codes, start_date=extended_start, end_date=end_date
            )
            if history_df.empty:
                return pd.DataFrame()

            history_df["trade_date"] = pd.to_datetime(history_df["trade_date"])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)

            result_list = []
            for ts_code, stock_df in history_df.groupby("ts_code", sort=False):
                stock_df = stock_df.sort_values("trade_date").reset_index(drop=True)
                evaluated_df = self.expression_engine.evaluate(formula, stock_df)
                evaluated_df = evaluated_df[
                    (evaluated_df["trade_date"] >= start_dt)
                    & (evaluated_df["trade_date"] <= end_dt)
                ]

                if evaluated_df.empty:
                    continue

                factor_df = evaluated_df[["ts_code", "trade_date", "factor_value"]].copy()
                factor_df["factor_id"] = factor_id
                result_list.append(factor_df)

            if not result_list:
                return pd.DataFrame()

            return pd.concat(result_list, ignore_index=True).dropna(subset=["factor_value"])

        except Exception as e:
            logger.error(f"计算自定义因子失败: {factor_id}, 错误: {e}")
            return pd.DataFrame()
    
    def get_factor_list(self, factor_type: str = None, is_active: bool = True) -> List[Dict[str, Any]]:
        """获取因子列表"""
        try:
            factor_list = []
            
            # 添加内置因子
            for factor_id, func in self.builtin_factors.items():
                # 根据因子ID推断因子类型
                if any(x in factor_id for x in ['momentum', 'volatility', 'volume', 'price', 'ma']):
                    ftype = 'technical'
                elif any(x in factor_id for x in ['pe', 'pb', 'ps', 'roe', 'roa', 'revenue', 'profit']):
                    ftype = 'fundamental'
                elif any(x in factor_id for x in ['money', 'flow']):
                    ftype = 'money_flow'
                elif any(x in factor_id for x in ['chip', 'winner']):
                    ftype = 'chip'
                else:
                    ftype = 'other'
                
                if factor_type is None or ftype == factor_type:
                    factor_list.append({
                        'factor_id': factor_id,
                        'factor_name': factor_id.replace('_', ' ').title(),
                        'factor_type': ftype,
                        'is_builtin': True,
                        'is_active': True,
                        'description': f"内置{ftype}因子"
                    })
            
            # 添加自定义因子
            definitions = self.factor_repo.list_definitions(include_inactive=not is_active)
            for definition in definitions:
                if factor_type is None or definition["factor_type"] == factor_type:
                    if not is_active or definition.get("is_active", True):
                        factor_list.append({
                            'factor_id': definition["factor_id"],
                            'factor_name': definition["factor_name"],
                            'factor_type': definition["factor_type"],
                            'is_builtin': False,
                            'is_active': definition.get("is_active", True),
                            'description': definition.get("description"),
                            'formula': definition.get("factor_formula"),
                            'params': definition.get("params"),
                            'created_at': definition.get("created_at"),
                            'updated_at': definition.get("updated_at"),
                        })
            
            return factor_list
            
        except Exception as e:
            logger.error(f"获取因子列表失败: {e}")
            return []
    
    def create_factor_definition(self, factor_id: str, factor_name: str, 
                               factor_formula: str, factor_type: str,
                               description: str = None, params: dict = None) -> bool:
        """创建因子定义（别名方法，兼容API调用）"""
        return self.register_factor(factor_id, factor_name, factor_formula, 
                                   factor_type, description, params) 
