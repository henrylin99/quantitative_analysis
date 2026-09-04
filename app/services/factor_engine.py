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
                                 start_date: str, end_date: str,
                                 data_cache: Dict[str, pd.DataFrame] = None) -> pd.DataFrame:
        """计算内置因子"""
        factor_func = self.builtin_factors[factor_id]

        # 按声明获取数据源（可跨因子共享缓存，避免同一窗口重复读表）
        data = self._get_factor_data(factor_id, ts_codes, start_date, end_date,
                                     data_cache=data_cache)
        
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
    
    # 内置因子 → 数据源声明。键为 _get_factor_data 返回 dict 的键；
    # needs_history=True 的源把起始日外推一年，供滚动窗口预热。
    # 声明式而非因子 id 子串匹配：子串路由既脆弱（id 命名碰巧含
    # 关键词就读错表）又浪费（price_to_ma20 曾因含 'ma' 白读一张表）
    BUILTIN_FACTOR_SOURCES = {
        'momentum_1d': ['return_prices'],
        'momentum_5d': ['return_prices'],
        'momentum_20d': ['return_prices'],
        'volatility_20d': ['return_prices'],
        'volume_ratio_20d': ['return_prices'],
        'price_to_ma20': ['return_prices'],
        'pe_percentile': ['daily_basic'],
        'pb_percentile': ['daily_basic'],
        'ps_percentile': ['daily_basic'],
        'roe_ttm': ['income', 'balance'],
        'roa_ttm': ['income', 'balance'],
        'revenue_growth': ['income'],
        'profit_growth': ['income'],
        'money_flow_strength': ['moneyflow'],
        'big_order_ratio': ['moneyflow'],
        'money_flow_momentum': ['moneyflow'],
        'chip_concentration': ['cyq'],
        'winner_rate_change': ['cyq'],
    }

    # 数据源 → (reader 方法名, 是否需要一年预热窗, 是否按 ts_codes 全量读取)
    DATA_SOURCE_LOADERS = {
        'return_prices': ('get_return_prices', True, False),
        # daily_basic 供 pe/pb/ps_percentile 做 252 日滚动分位，必须带预热窗，
        # 否则单日截面下每股只有 1 个观测，因子恒为空
        'daily_basic': ('get_daily_basic', True, False),
        'moneyflow': ('get_moneyflow', True, False),
        'cyq': ('get_cyq_perf', True, False),
        'income': ('get_income_statement', False, True),
        'balance': ('get_balance_sheet', False, True),
    }

    def _get_factor_data(self, factor_id: str, ts_codes: List[str],
                        start_date: str, end_date: str,
                        data_cache: Dict[str, pd.DataFrame] = None) -> Dict[str, pd.DataFrame]:
        """按声明获取因子计算所需的数据。

        data_cache: 跨因子共享的数据缓存（calculate_all_factors 传入），
        同一调用窗口内多个因子共用一次数据读取。
        """
        sources = self.BUILTIN_FACTOR_SOURCES.get(factor_id)
        if sources is None:
            logger.warning(f"内置因子未声明数据源: {factor_id}")
            return {}

        extended_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=252)).strftime('%Y-%m-%d')
        data: Dict[str, pd.DataFrame] = {}

        for source in sources:
            if data_cache is not None and source in data_cache:
                data[source] = data_cache[source]
                continue
            method_name, needs_history, codes_only = self.DATA_SOURCE_LOADERS[source]
            window_start = extended_start if needs_history else start_date
            try:
                if codes_only:
                    loaded = getattr(self.data_reader, method_name)(ts_codes)
                else:
                    loaded = getattr(self.data_reader, method_name)(
                        ts_codes=ts_codes, start_date=window_start, end_date=end_date
                    )
            except Exception as e:
                logger.error(f"获取因子数据失败 source={source}: {e}")
                continue
            data[source] = loaded
            if data_cache is not None:
                data_cache[source] = loaded

        return data
    
    # ==================== 内置因子计算函数 ====================
    
    @staticmethod
    def _finalize_factor_result(df: pd.DataFrame, value_col: str,
                                factor_id: str) -> pd.DataFrame:
        """统一因子输出 schema：ts_code, trade_date, factor_id, factor_value"""
        result = df.rename(columns={value_col: "factor_value"})
        result["factor_id"] = factor_id
        # 资金流/筹码类因子的分母可能为 0，除零产生 inf；inf 入库会把
        # 当日截面 z_score 的 mean 拉成 inf，全截面统计作废，统一按缺失处理
        if pd.api.types.is_numeric_dtype(result["factor_value"]):
            result["factor_value"] = result["factor_value"].replace(
                [np.inf, -np.inf], np.nan
            )
        return result[["ts_code", "trade_date", "factor_id", "factor_value"]].dropna(
            subset=["factor_value"]
        )

    @staticmethod
    def _sorted_by_code_and_date(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df.sort_values(["ts_code", "trade_date"])

    def _momentum_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """动量因子：N日收益率"""
        if 'return_prices' not in data or data['return_prices'].empty:
            return pd.DataFrame()

        period = int(factor_id.split('_')[1].replace('d', ''))
        df = self._sorted_by_code_and_date(data['return_prices'])
        df['factor_value'] = df.groupby('ts_code')['close'].pct_change(period)
        return self._finalize_factor_result(df, 'factor_value', factor_id)

    def _volatility_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """波动率因子：N日收益率标准差"""
        if 'return_prices' not in data or data['return_prices'].empty:
            return pd.DataFrame()

        period = int(factor_id.split('_')[1].replace('d', ''))
        df = self._sorted_by_code_and_date(data['return_prices'])
        df['daily_return'] = df.groupby('ts_code')['close'].pct_change()
        df['factor_value'] = df.groupby('ts_code')['daily_return'].transform(
            lambda s: s.rolling(period).std()
        )
        return self._finalize_factor_result(df, 'factor_value', factor_id)

    def _volume_ratio_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """成交量比率因子"""
        if 'return_prices' not in data or data['return_prices'].empty:
            return pd.DataFrame()

        period = int(factor_id.split('_')[2].replace('d', ''))
        df = self._sorted_by_code_and_date(data['return_prices'])
        df['vol_ma'] = df.groupby('ts_code')['vol'].transform(
            lambda s: s.rolling(period).mean()
        )
        df['factor_value'] = df['vol'] / df['vol_ma']
        return self._finalize_factor_result(df, 'factor_value', factor_id)

    def _price_to_ma_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """价格相对均线因子"""
        if 'return_prices' not in data or data['return_prices'].empty:
            return pd.DataFrame()

        period = int(factor_id.split('ma')[1])
        df = self._sorted_by_code_and_date(data['return_prices'])
        df['ma'] = df.groupby('ts_code')['close'].transform(
            lambda s: s.rolling(period).mean()
        )
        df['factor_value'] = df['close'] / df['ma'] - 1
        return self._finalize_factor_result(df, 'factor_value', factor_id)

    def _valuation_percentile_factor(self, data: Dict[str, pd.DataFrame],
                                     factor_id: str, value_col: str) -> pd.DataFrame:
        """估值历史分位数因子（PE/PB/PS 共用实现）。

        每只股票至少需要 20 个有效数据点；滚动窗口 252 日、min_periods=20。
        """
        if 'daily_basic' not in data or data['daily_basic'].empty:
            return pd.DataFrame()

        df = data['daily_basic'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df[value_col] = pd.to_numeric(df[value_col], errors='coerce')
        df = df[df[value_col].notna() & (df[value_col] > 0)]
        if df.empty:
            return pd.DataFrame()

        valid_counts = df.groupby('ts_code')[value_col].transform('size')
        df = df[valid_counts > 20]
        if df.empty:
            return pd.DataFrame()

        df = df.sort_values(['ts_code', 'trade_date'])
        df['factor_value'] = df.groupby('ts_code')[value_col].transform(
            lambda s: s.rolling(252, min_periods=20).apply(
                lambda x: stats.percentileofscore(x, x.iloc[-1]) / 100
            )
        )
        return self._finalize_factor_result(df, 'factor_value', factor_id)

    def _pe_percentile_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """PE历史分位数因子"""
        return self._valuation_percentile_factor(data, factor_id, 'pe_ttm')

    def _pb_percentile_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """PB历史分位数因子"""
        return self._valuation_percentile_factor(data, factor_id, 'pb')

    def _ps_percentile_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """PS历史分位数因子"""
        return self._valuation_percentile_factor(data, factor_id, 'ps_ttm')

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
        """资金流向强度因子：大单净流入 / 总成交额"""
        if 'moneyflow' not in data or data['moneyflow'].empty:
            return pd.DataFrame()

        df = data['moneyflow'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        big_net = (df['buy_lg_amount'] + df['buy_elg_amount']) \
            - (df['sell_lg_amount'] + df['sell_elg_amount'])
        total = (df['buy_sm_amount'] + df['buy_md_amount']
                 + df['buy_lg_amount'] + df['buy_elg_amount'])
        df['factor_value'] = big_net / total
        return self._finalize_factor_result(df, 'factor_value', factor_id)

    def _big_order_ratio_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """大单占比因子：大单成交额 / 全口径成交额"""
        if 'moneyflow' not in data or data['moneyflow'].empty:
            return pd.DataFrame()

        df = data['moneyflow'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        big = (df['buy_lg_amount'] + df['sell_lg_amount']
               + df['buy_elg_amount'] + df['sell_elg_amount'])
        total = (df['buy_sm_amount'] + df['sell_sm_amount']
                 + df['buy_md_amount'] + df['sell_md_amount']
                 + big)
        df['factor_value'] = big / total
        return self._finalize_factor_result(df, 'factor_value', factor_id)

    def _money_flow_momentum_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """资金流向动量因子：5日净流入之和"""
        if 'moneyflow' not in data or data['moneyflow'].empty:
            return pd.DataFrame()

        df = self._sorted_by_code_and_date(data['moneyflow'])
        df['factor_value'] = df.groupby('ts_code')['net_mf_amount'].transform(
            lambda s: s.rolling(5).sum()
        )
        return self._finalize_factor_result(df, 'factor_value', factor_id)

    def _chip_concentration_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """筹码集中度因子：90%筹码价格区间相对中位数的比例"""
        if 'cyq' not in data or data['cyq'].empty:
            return pd.DataFrame()

        df = data['cyq'].copy()
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['factor_value'] = (df['cost_95pct'] - df['cost_5pct']) / df['cost_50pct']
        return self._finalize_factor_result(df, 'factor_value', factor_id)

    def _winner_rate_change_factor(self, data: Dict[str, pd.DataFrame], factor_id: str) -> pd.DataFrame:
        """胜率变化因子：5日胜率差分"""
        if 'cyq' not in data or data['cyq'].empty:
            return pd.DataFrame()

        df = self._sorted_by_code_and_date(data['cyq'])
        df['factor_value'] = df.groupby('ts_code')['winner_rate'].diff(5)
        return self._finalize_factor_result(df, 'factor_value', factor_id)

    def filter_universe_asof(self, basic_df: pd.DataFrame, trade_date: str) -> List[str]:
        """按历史时点过滤股票池，消除幸存者偏差与次新股污染。

        所有"按 trade_date 计算全市场因子"的入口都必须先过这道过滤：
        直接喂当前 stock_basic 全量代码，会把当时尚未上市的股票算进
        历史截面，污染 z-score 与分位。对外公开，供 API 层复用。

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
                ts_codes = self.filter_universe_asof(basic_df, trade_date)
            
            all_results = []
            # 同一调用窗口内多个因子共享数据读取：
            # momentum/volatility/volume/price_to_ma 六个因子共用一次
            # return_prices 读取，不再各自全表扫描
            data_cache: Dict[str, pd.DataFrame] = {}

            # 计算内置因子
            for factor_id in self.builtin_factors.keys():
                try:
                    result = self._calculate_builtin_factor(
                        factor_id, ts_codes, trade_date, trade_date,
                        data_cache=data_cache,
                    )
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

            # 与内置动量类因子同一复权口径：close.pct_change(20) 这类
            # 表达式必须基于后复权价，否则除权除息日会出现假缺口。
            # OHLC 全部传入保证同一表达式内的价格列口径一致
            history_df = self.data_reader.get_return_prices(
                ts_codes=ts_codes, start_date=extended_start, end_date=end_date,
                price_fields=["open", "high", "low", "close", "pre_close"],
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
