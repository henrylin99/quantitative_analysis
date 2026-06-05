"""
ParquetDataReader — 从本地 Parquet 文件加载日行情数据，替代传统数据库查询。

存储布局（Hive 分区格式）：
    {data_dir}/daily_history/daily/year=YYYY/month=MM/day=DD/data.parquet
    {data_dir}/daily_basic/daily/year=YYYY/month=MM/day=DD/data.parquet
"""

import os
from datetime import datetime, date
from typing import List, Optional

import pandas as pd
from loguru import logger

from app.services.minute_parquet_reader import MinuteParquetReader


class ParquetDataReader:
    """从本地 Parquet 分区文件读取日行情 / 日基本面数据。"""

    # 表名 → 相对子目录
    TABLE_DIRS = {
        "daily": "daily_history/daily",
        "daily_basic": "daily_basic/daily",
        "stk_factor": "stk_factor/daily",
        "moneyflow": "moneyflow/daily",
        "cyq_perf": "cyq_perf/daily",
        "income_statement": "income_statement",
        "balance_sheet": "balance_sheet",
        "cash_flow": "cash_flow",
    }

    # 标准列：过滤 parquet 中可能混入的额外列（None = 不过滤，保留全部列）
    STANDARD_COLUMNS = {
        "daily": [
            "ts_code", "trade_date", "open", "high", "low", "close",
            "pre_close", "change", "pct_chg", "vol", "amount",
        ],
        "daily_basic": [
            "ts_code", "trade_date", "close", "turnover_rate", "turnover_rate_f",
            "volume_ratio", "pe", "pe_ttm", "pb", "ps", "ps_ttm",
            "dv_ratio", "dv_ttm", "total_share", "float_share", "free_share",
            "total_mv", "circ_mv",
        ],
        "stk_factor": [
            "ts_code", "trade_date", "close", "open", "high", "low",
            "pre_close", "change", "pct_change", "vol", "amount",
            "adj_factor", "open_hfq", "open_qfq", "close_hfq", "close_qfq",
            "high_hfq", "high_qfq", "low_hfq", "low_qfq",
            "pre_close_hfq", "pre_close_qfq",
            "macd_dif", "macd_dea", "macd",
            "kdj_k", "kdj_d", "kdj_j",
            "rsi_6", "rsi_12", "rsi_24",
            "boll_upper", "boll_mid", "boll_lower", "cci",
        ],
        "moneyflow": None,
        "cyq_perf": None,
        "income_statement": None,
        "balance_sheet": None,
        "cash_flow": None,
    }

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir
        self._minute_reader: MinuteParquetReader | None = None

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def get_daily(
        self,
        ts_codes: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取日线行情数据。

        Parameters
        ----------
        ts_codes : list[str] | None
            股票代码列表，None 表示全部。
        start_date, end_date : str | None
            "YYYY-MM-DD" 或 "YYYYMMDD" 格式。
        """
        return self._read_table("daily", ts_codes, start_date, end_date)

    def get_daily_basic(
        self,
        ts_codes: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取日基本面数据。"""
        return self._read_table("daily_basic", ts_codes, start_date, end_date)

    def get_stk_factor(
        self,
        ts_codes: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取技术因子数据（MACD/KDJ/RSI/布林带/CCI 等）。"""
        return self._read_table("stk_factor", ts_codes, start_date, end_date)

    def get_moneyflow(
        self,
        ts_codes: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取资金流向数据。"""
        return self._read_table("moneyflow", ts_codes, start_date, end_date)

    def get_cyq_perf(
        self,
        ts_codes: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取筹码分布数据。"""
        return self._read_table("cyq_perf", ts_codes, start_date, end_date)

    def get_income_statement(self, ts_codes: List[str]) -> pd.DataFrame:
        """读取利润表数据（季度分区，按 ts_codes 过滤，按 end_date 倒序）。"""
        df = self._read_table("income_statement", ts_codes, None, None)
        if not df.empty and "end_date" in df.columns:
            df["end_date"] = df["end_date"].astype(str)
            df = df.sort_values(["ts_code", "end_date"], ascending=[True, False])
        return df

    def get_balance_sheet(self, ts_codes: List[str]) -> pd.DataFrame:
        """读取资产负债表数据（季度分区，按 ts_codes 过滤，按 end_date 倒序）。"""
        df = self._read_table("balance_sheet", ts_codes, None, None)
        if not df.empty and "end_date" in df.columns:
            df["end_date"] = df["end_date"].astype(str)
            df = df.sort_values(["ts_code", "end_date"], ascending=[True, False])
        return df

    def get_cash_flow(self, ts_codes: List[str]) -> pd.DataFrame:
        """读取现金流量表数据（季度分区，按 ts_codes 过滤，按 end_date 倒序）。"""
        df = self._read_table("cash_flow", ts_codes, None, None)
        if not df.empty and "end_date" in df.columns:
            df["end_date"] = df["end_date"].astype(str)
            df = df.sort_values(["ts_code", "end_date"], ascending=[True, False])
        return df

    # ------------------------------------------------------------------
    # 单文件表（stock_basic, trade_calendar 等）
    # ------------------------------------------------------------------

    def _read_single(self, filename: str) -> pd.DataFrame:
        """读取单文件 parquet 表。"""
        path = os.path.join(self.data_dir, filename)
        if not os.path.isfile(path):
            logger.warning(f"Parquet 文件不存在: {path}")
            return pd.DataFrame()
        try:
            return pd.read_parquet(path)
        except Exception as e:
            logger.warning(f"读取 parquet 失败 {path}: {e}")
            return pd.DataFrame()

    _stock_basic_cache: Optional[pd.DataFrame] = None

    def get_stock_basic(self, ts_code: Optional[str] = None) -> pd.DataFrame:
        """读取 stock_basic 表。可选按 ts_code 过滤。"""
        if ParquetDataReader._stock_basic_cache is None:
            ParquetDataReader._stock_basic_cache = self._read_single("stock_basic.parquet")
        df = ParquetDataReader._stock_basic_cache
        if df.empty:
            return df
        if ts_code:
            df = df[df["ts_code"] == ts_code]
        return df

    def get_stock_basic_list(
        self,
        industry: Optional[str] = None,
        area: Optional[str] = None,
        search: Optional[str] = None,
    ) -> pd.DataFrame:
        """读取 stock_basic 表，按 industry/area/search 过滤。"""
        df = self.get_stock_basic()
        if df.empty:
            return df
        if industry:
            df = df[df["industry"] == industry]
        if area:
            df = df[df["area"] == area]
        if search:
            kw = f"%{search}%"
            mask = (
                df["ts_code"].str.contains(kw.replace("%", ""), case=False, na=False)
                | df["symbol"].str.contains(kw.replace("%", ""), case=False, na=False)
                | df["name"].str.contains(kw.replace("%", ""), case=False, na=False)
            )
            df = df[mask]
        return df

    def get_industry_list(self) -> List[str]:
        """获取行业列表。"""
        df = self.get_stock_basic()
        if df.empty:
            return []
        return sorted(df["industry"].dropna().unique().tolist())

    def get_area_list(self) -> List[str]:
        """获取地域列表。"""
        df = self.get_stock_basic()
        if df.empty:
            return []
        return sorted(df["area"].dropna().unique().tolist())

    def get_trade_calendar(self) -> pd.DataFrame:
        """读取交易日历。"""
        return self._read_single("stock_trade_calendar.parquet")

    def get_minute_reader(self) -> MinuteParquetReader:
        """获取分钟级 parquet 读取器。"""
        if self._minute_reader is None or self._minute_reader.data_dir != self.data_dir:
            self._minute_reader = MinuteParquetReader(data_dir=self.data_dir)
        return self._minute_reader

    def get_stock_company(self, ts_codes: Optional[List[str]] = None) -> pd.DataFrame:
        """读取公司信息表。"""
        df = self._read_single("stock_company.parquet")
        if df.empty or ts_codes is None:
            return df
        return df[df["ts_code"].isin(set(ts_codes))]

    def get_index_basic(self) -> pd.DataFrame:
        """读取指数基本信息。"""
        return self._read_single("index_basic.parquet")

    _stock_business_cache: Optional[pd.DataFrame] = None

    def get_stock_business(self, ts_code: Optional[str] = None,
                           trade_date: Optional[str] = None) -> pd.DataFrame:
        """读取股票业务大宽表（daily_basic + factor + moneyflow 合并）。"""
        if ParquetDataReader._stock_business_cache is None:
            ParquetDataReader._stock_business_cache = self._read_single("stock_business.parquet")
        df = ParquetDataReader._stock_business_cache
        if df.empty:
            return df
        if ts_code:
            df = df[df["ts_code"] == ts_code]
        if trade_date:
            td = pd.to_datetime(trade_date)
            df_col = pd.to_datetime(df["trade_date"])
            df = df[df_col == td]
        return df

    def get_stock_business_latest_date(self) -> Optional[str]:
        """获取 stock_business 最新交易日期。"""
        df = self.get_stock_business()
        if df.empty or "trade_date" not in df.columns:
            return None
        return pd.to_datetime(df["trade_date"]).max().strftime("%Y-%m-%d")

    def get_ma_data(self, ts_code: str) -> Optional[pd.Series]:
        """读取单只股票的最新均线数据。"""
        df = self._read_single("stock_ma_data.parquet")
        if df.empty:
            return None
        row = df[df["ts_code"] == ts_code]
        if row.empty:
            return None
        return row.iloc[0]

    def get_latest_close(self, ts_code: str) -> Optional[float]:
        """获取指定股票最新收盘价。"""
        latest = self._read_latest_partition("daily")
        if latest is None or latest.empty:
            return None
        row = latest[latest["ts_code"] == ts_code]
        if row.empty:
            return None
        return float(row.iloc[0]["close"])

    def get_latest_daily(self, ts_code: str) -> Optional[pd.Series]:
        """获取指定股票最新日行情（全部字段）。"""
        latest = self._read_latest_partition("daily")
        if latest is None or latest.empty:
            return None
        row = latest[latest["ts_code"] == ts_code]
        if row.empty:
            return None
        return row.iloc[0]

    def get_trade_dates(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[str]:
        """从分区目录名提取交易日列表。

        Returns
        -------
        list[str]
            日期字符串列表，格式 "YYYY-MM-DD"。
        """
        sd = _parse_date(start_date) if start_date else None
        ed = _parse_date(end_date) if end_date else None

        base = os.path.join(self.data_dir, self.TABLE_DIRS["daily"])
        if not os.path.isdir(base):
            logger.warning(f"Parquet 目录不存在: {base}")
            return []

        dates: List[str] = []
        for year_dir in _sorted_dirs(base):
            y = _partition_value(year_dir, "year")
            if y is None:
                continue
            for month_dir in _sorted_dirs(os.path.join(base, year_dir)):
                m = _partition_value(month_dir, "month")
                if m is None:
                    continue
                for day_dir in _sorted_dirs(os.path.join(base, year_dir, month_dir)):
                    d = _partition_value(day_dir, "day")
                    if d is None:
                        continue
                    # 检查 parquet 文件存在
                    if not os.path.isfile(os.path.join(base, year_dir, month_dir, day_dir, "data.parquet")):
                        continue
                    dt = f"{y}-{m}-{d}"
                    if sd and dt < sd:
                        continue
                    if ed and dt > ed:
                        continue
                    dates.append(dt)

        dates.sort()
        return dates

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _read_table(
        self,
        table: str,
        ts_codes: Optional[List[str]],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> pd.DataFrame:
        """通用读表逻辑：扫描分区目录 → concat → 过滤。"""
        sd = _parse_date(start_date) if start_date else None
        ed = _parse_date(end_date) if end_date else None

        base = os.path.join(self.data_dir, self.TABLE_DIRS[table])
        if not os.path.isdir(base):
            logger.warning(f"Parquet 目录不存在: {base}")
            return pd.DataFrame()

        frames = []
        for parquet_path in self._walk_partitions(base, sd, ed):
            try:
                df = pd.read_parquet(parquet_path)
                if not df.empty:
                    frames.append(df)
            except Exception as e:
                logger.warning(f"读取 parquet 失败 {parquet_path}: {e}")

        if not frames:
            return pd.DataFrame()

        result = pd.concat(frames, ignore_index=True)

        # 只保留标准列，过滤掉可能混入的额外列
        std_cols = self.STANDARD_COLUMNS.get(table)
        if std_cols:
            keep = [c for c in std_cols if c in result.columns]
            result = result[keep]

        # 按股票代码过滤
        if ts_codes is not None:
            code_set = set(ts_codes)
            result = result[result["ts_code"].isin(code_set)]

        # 排序
        if "trade_date" in result.columns:
            # 同一批 parquet 可能同时存在 YYYYMMDD 和 YYYY-MM-DD 两种格式，
            # 用 mixed 解析可以兼容历史增量数据，避免把整批历史读空。
            result["trade_date"] = pd.to_datetime(
                result["trade_date"],
                errors="coerce",
                format="mixed",
            )
            result = result.dropna(subset=["trade_date"])
            sort_cols = ["trade_date"]
            if "ts_code" in result.columns:
                sort_cols.append("ts_code")
            result = result.sort_values(sort_cols).reset_index(drop=True)

        return result

    def _read_latest_partition(self, table: str) -> Optional[pd.DataFrame]:
        """读取最新日期分区的 parquet。"""
        base = os.path.join(self.data_dir, self.TABLE_DIRS[table])
        if not os.path.isdir(base):
            return None

        # 找到最新分区
        latest_path = self._find_latest_parquet(base)
        if latest_path is None:
            return None

        try:
            return pd.read_parquet(latest_path)
        except Exception as e:
            logger.warning(f"读取最新分区失败 {latest_path}: {e}")
            return None

    def _walk_partitions(self, base: str, start_date: Optional[str], end_date: Optional[str]):
        """生成在日期范围内的 parquet 文件路径。"""
        for year_dir in _sorted_dirs(base):
            y = _partition_value(year_dir, "year")
            if y is None:
                continue
            for month_dir in _sorted_dirs(os.path.join(base, year_dir)):
                m = _partition_value(month_dir, "month")
                if m is None:
                    continue
                for day_dir in _sorted_dirs(os.path.join(base, year_dir, month_dir)):
                    d = _partition_value(day_dir, "day")
                    if d is None:
                        continue
                    dt = f"{y}-{m}-{d}"
                    if start_date and dt < start_date:
                        continue
                    if end_date and dt > end_date:
                        continue
                    parquet_path = os.path.join(base, year_dir, month_dir, day_dir, "data.parquet")
                    if os.path.isfile(parquet_path):
                        yield parquet_path

    def _find_latest_parquet(self, base: str) -> Optional[str]:
        """在 Hive 分区目录中找到最新日期的 parquet 文件。"""
        year_dirs = _sorted_dirs(base)
        if not year_dirs:
            return None

        for year_dir in reversed(year_dirs):
            year_path = os.path.join(base, year_dir)
            month_dirs = _sorted_dirs(year_path)
            if not month_dirs:
                continue

            for month_dir in reversed(month_dirs):
                month_path = os.path.join(year_path, month_dir)
                day_dirs = _sorted_dirs(month_path)
                if not day_dirs:
                    continue

                for day_dir in reversed(day_dirs):
                    parquet_path = os.path.join(month_path, day_dir, "data.parquet")
                    if os.path.isfile(parquet_path):
                        return parquet_path

        return None


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------


def _parse_date(date_str: str) -> str:
    """将各种日期格式统一为 YYYY-MM-DD。"""
    if not date_str:
        return date_str
    # 已经是 YYYY-MM-DD
    if len(date_str) == 10 and date_str[4] == "-":
        return date_str
    # YYYYMMDD → YYYY-MM-DD
    if len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    # 尝试 pandas 解析
    try:
        return pd.to_datetime(date_str).strftime("%Y-%m-%d")
    except Exception:
        return date_str


def _sorted_dirs(path: str) -> List[str]:
    """返回 path 下名称符合 *=* 模式的子目录，按名称排序。"""
    if not os.path.isdir(path):
        return []
    return sorted(
        d for d in os.listdir(path)
        if os.path.isdir(os.path.join(path, d)) and "=" in d
    )


def _partition_value(dir_name: str, key: str) -> Optional[str]:
    """从 Hive 分区目录名提取值，如 year=2024 → '2024'。"""
    prefix = f"{key}="
    if dir_name.startswith(prefix):
        val = dir_name[len(prefix):]
        # 补零：month=6 → 06, day=3 → 03
        if key in ("month", "day") and len(val) == 1:
            val = f"0{val}"
        return val
    return None
