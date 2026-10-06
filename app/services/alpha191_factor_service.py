"""
Alpha191 内置因子服务 — 基于「日期 × 股票」宽面板的向量化因子计算。

参考实现：20260213 项目 backend/app/factors/alpha191_new.py。公式与算子在
alpha191_formulas.py 中整体平移（191 个因子），本服务负责：
  1. 用本项目数据（ParquetDataReader）装配宽面板（不复权日线 + daily_basic
     + vwap + 可选基准指数）；
  2. 单因子 / 批量因子计算编排（面板只加载一次）；
  3. 结果清洗（±inf→NaN）并落 factor_values 长表 schema。

用法（服务层）:
    from app.services.alpha191_factor_service import Alpha191FactorService
    df = Alpha191FactorService().calculate("alpha_001", "2026-09-01", "2026-09-22")

用法（CLI）:
    python scripts/compute_alpha191.py --start 2026-09-01 --end 2026-09-22
"""
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from app.services.alpha191_formulas import Alpha191Calculator, Alpha191Panel
from app.services.data_reader import ParquetDataReader

# ---------------------------------------------------------------------------
# 因子清单与计算约束
# ---------------------------------------------------------------------------

# 调用会抛 NotImplementedError 或依赖未来数据的因子（与参考实现 SKIP_FACTORS 同步）
SKIP_FACTORS: Dict[str, str] = {
    "alpha_030": "需要 Fama-French 三因子数据（MKT/SMB/HML）",
    "alpha_143": "公式含递归 SELF 状态，参考实现即未实现",
}

# 需要基准指数（benchmark_open/close）的因子；指数数据缺失/不覆盖区间时
# 这些因子结果为空，批量计算自动跳过
BENCHMARK_FACTORS = {"alpha_075", "alpha_149", "alpha_181", "alpha_182"}

# A 股市场基准：本项目指数库按 ts_code 分区，沪深300 落在 399300.SZ
BENCHMARK_INDEX_MAP = {"000300.SH": "399300.SZ"}

# 面板预热窗（自然日）。Alpha191 公式最长滚动窗 252 交易日，
# 与参考编排引擎一致取 400 自然日（≈270 交易日）。
WARMUP_DAYS = 400

_ALPHA_METHODS = sorted(
    n for n in dir(Alpha191Calculator) if n.startswith("alpha_")
)


def _build_registry() -> Dict[str, Dict]:
    registry: Dict[str, Dict] = {}
    for name in _ALPHA_METHODS:
        num = int(name.split("_")[1])
        entry = {
            "name": f"Alpha#{num:03d}",
            "description": f"国泰君安 Alpha191 技术因子 #{num}",
            "category": "alpha191",
            "warmup_days": WARMUP_DAYS,
            "needs_basic": True,
            "needs_benchmark": name in BENCHMARK_FACTORS,
        }
        registry[name] = entry
    # alpha_001 保留更友好的中文说明
    registry["alpha_001"].update({
        "name": "Alpha#001 量价背离",
        "formula": "-CORR(RANK(DELTA(LOG(VOLUME),1)), RANK((CLOSE-OPEN)/OPEN), 6)",
        "description": "对数成交量一阶差分的截面排名与日内收益截面排名的"
                       "6日滚动相关取负——放量上涨（量价同向）得分低，"
                       "量价背离的股票得分高。",
    })
    for name, reason in SKIP_FACTORS.items():
        registry[name]["skip_reason"] = reason
    return registry


ALPHA191_FACTORS: Dict[str, Dict] = _build_registry()


def computable_factors() -> List[str]:
    """当前可批量计算的因子（剔除 skip 清单）。"""
    return [n for n in _ALPHA_METHODS if n not in SKIP_FACTORS]


def _get_data_reader() -> ParquetDataReader:
    """延迟创建 ParquetDataReader 单例（与 factor_engine 同模式）。"""
    if not hasattr(_get_data_reader, "_instance"):
        _get_data_reader._instance = ParquetDataReader()
    return _get_data_reader._instance


class Alpha191FactorService:
    """Alpha191 因子计算服务（全市场宽面板向量化）。"""

    def __init__(self, data_reader: ParquetDataReader = None):
        self.data_reader = data_reader or _get_data_reader()
        self.calculator = Alpha191Calculator()

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    @staticmethod
    def list_factors() -> List[Dict]:
        return [{"factor_id": fid, **meta} for fid, meta in ALPHA191_FACTORS.items()]

    def calculate(self, factor_id: str, start_date: str, end_date: str,
                  ts_codes: Optional[List[str]] = None) -> pd.DataFrame:
        """计算单个因子，返回标准长表 schema:
        ts_code, trade_date, factor_id, factor_value。

        start_date/end_date 支持 YYYY-MM-DD 或 YYYYMMDD。结果仅包含
        [start_date, end_date] 区间内的交易日（预热窗数据只用于滚动
        计算，不返回）。
        """
        results = self.calculate_many([factor_id], start_date, end_date,
                                      ts_codes=ts_codes)
        return results.get(factor_id, pd.DataFrame(
            columns=["ts_code", "trade_date", "factor_id", "factor_value"]))

    def calculate_many(self, factor_ids: List[str], start_date: str, end_date: str,
                       ts_codes: Optional[List[str]] = None,
                       on_result: Optional[Callable[[str, pd.DataFrame], None]] = None,
                       collect_results: bool = True,
                       ) -> Dict[str, Any]:
        """批量计算多个因子：面板只加载一次，逐因子计算并回调。

        on_result(factor_id, long_df) 在每个因子算完即调用（边算边落库，
        避免上百个因子结果同时驻留内存）。
        collect_results=True（默认）返回 {factor_id: long_df}；大区间批量
        落库场景传 collect_results=False，返回 {factor_id: 行数}——
        全年区间 × 185 因子的长表全量驻留内存可达数十 GB。
        失败因子记录到日志，不中断批次。
        """
        start_norm = pd.to_datetime(start_date).strftime("%Y-%m-%d")
        end_norm = pd.to_datetime(end_date).strftime("%Y-%m-%d")
        warmup_start = (
            pd.to_datetime(start_norm) - pd.Timedelta(days=WARMUP_DAYS)
        ).strftime("%Y-%m-%d")

        panel = self._load_panel(warmup_start, end_norm)
        if panel is None or panel.close.empty:
            logger.warning(f"Alpha191 面板为空，跳过 {len(factor_ids)} 个因子: "
                           f"{warmup_start} → {end_norm}")
            return {}

        results: Dict[str, Any] = {}
        series_mode_ids: List[str] = []
        output_dates = [
            d for d in panel.close.index
            if start_norm <= d.strftime("%Y-%m-%d") <= end_norm
        ]
        for factor_id in factor_ids:
            if factor_id in SKIP_FACTORS:
                logger.info(f"跳过 {factor_id}: {SKIP_FACTORS[factor_id]}")
                continue
            # 基准因子需要基准数据覆盖整段面板：NaN 参与比较得 False，
            # 会让 alpha_182 这类条件计数因子静默产出全 0 假值
            if ALPHA191_FACTORS[factor_id].get("needs_benchmark"):
                if panel.benchmark_close is None:
                    logger.warning(f"跳过 {factor_id}: 无基准指数数据")
                    continue
                if panel.benchmark_close.isna().any():
                    logger.warning(f"跳过 {factor_id}: 基准指数数据未覆盖"
                                   f"完整面板区间 {warmup_start}→{end_norm}")
                    continue
            try:
                wide: pd.DataFrame = getattr(self.calculator, factor_id)(panel)
            except NotImplementedError as exc:
                logger.warning(f"{factor_id} 未实现: {exc}")
                continue
            except Exception as exc:
                logger.error(f"Alpha191 因子计算失败: {factor_id}, 错误: {exc}")
                continue

            if isinstance(wide, pd.Series):
                # Series 模式：方法只算 panel.close.index[-1] 单日截面，
                # 需逐日切片重算（切片截到 T，无前视），参考编排引擎同款
                series_mode_ids.append(factor_id)
                continue

            long_df = self._finalize_factor(wide, factor_id, start_norm,
                                            end_norm, ts_codes)
            if long_df is None:
                continue
            results[factor_id] = long_df if collect_results else int(len(long_df))
            if on_result is not None:
                on_result(factor_id, long_df)

        for factor_id in series_mode_ids:
            long_df = self._compute_series_mode(factor_id, panel, output_dates,
                                                ts_codes)
            if long_df is None or long_df.empty:
                logger.warning(f"{factor_id}: 区间内无有效值（series 模式）")
                continue
            results[factor_id] = long_df if collect_results else int(len(long_df))
            if on_result is not None:
                on_result(factor_id, long_df)
        return results

    def _finalize_factor(self, wide: pd.DataFrame, factor_id: str,
                         start_norm: str, end_norm: str,
                         ts_codes: Optional[List[str]]):
        """±inf 清洗 → 长表 → 区间/股票过滤。无有效值返回 None。"""
        # 除零/对数非正边界会产生 ±inf，统一置 NaN 后再落库，
        # 否则 inf 会污染下游 z_score / percentile 统计
        wide = wide.replace([np.inf, -np.inf], np.nan)
        long_df = self._to_long(wide, factor_id)
        # 预热窗数据只参与滚动计算，不进入结果
        long_df = long_df[
            (long_df["trade_date"] >= start_norm)
            & (long_df["trade_date"] <= end_norm)
        ]
        if ts_codes:
            long_df = long_df[long_df["ts_code"].isin(set(ts_codes))]
        long_df = long_df.reset_index(drop=True)
        if long_df.empty:
            logger.warning(f"{factor_id}: 区间内无有效值")
            return None
        return long_df

    def _compute_series_mode(self, factor_id: str, panel: Alpha191Panel,
                             output_dates, ts_codes: Optional[List[str]]):
        """Series 模式因子：逐交易日切片计算单日截面。"""
        func = getattr(self.calculator, factor_id)
        frames = []
        for T in output_dates:
            sub = self._slice_panel(panel, T)
            try:
                out = func(sub)
            except Exception as exc:
                logger.error(f"{factor_id} series 模式 {T} 计算失败: {exc}")
                continue
            trade_date = T.strftime("%Y-%m-%d")
            if isinstance(out, pd.Series):
                frame = out.rename("factor_value").reset_index()
                frame.columns = ["ts_code", "factor_value"]
            else:  # 兜底：取最后一行
                frame = out.iloc[[-1]].stack().rename("factor_value").reset_index()
                frame = frame.iloc[:, 1:3]
                frame.columns = ["ts_code", "factor_value"]
            frame["trade_date"] = trade_date
            frame["factor_id"] = factor_id
            frames.append(frame)
        if not frames:
            return None
        long_df = pd.concat(frames, ignore_index=True)
        long_df["factor_value"] = pd.to_numeric(
            long_df["factor_value"], errors="coerce"
        ).replace([np.inf, -np.inf], np.nan)
        long_df = long_df.dropna(subset=["factor_value"])
        if ts_codes:
            long_df = long_df[long_df["ts_code"].isin(set(ts_codes))]
        return long_df[["ts_code", "trade_date", "factor_id", "factor_value"]]

    @staticmethod
    def _slice_panel(panel: Alpha191Panel, T) -> Alpha191Panel:
        """返回所有时间字段截到 <= T 的面板副本（防前视）。"""

        def _slice(df):
            return df.loc[:T] if df is not None else None

        return Alpha191Panel(
            open=_slice(panel.open),
            high=_slice(panel.high),
            low=_slice(panel.low),
            close=_slice(panel.close),
            pre_close=_slice(panel.pre_close),
            volume=_slice(panel.volume),
            amount=_slice(panel.amount),
            vwap=_slice(panel.vwap),
            turnover_rate=_slice(panel.turnover_rate),
            volume_ratio=_slice(panel.volume_ratio),
            total_mv=_slice(panel.total_mv),
            circ_mv=_slice(panel.circ_mv),
            benchmark_open=_slice(panel.benchmark_open),
            benchmark_close=_slice(panel.benchmark_close),
        )

    # ------------------------------------------------------------------
    # 面板加载
    # ------------------------------------------------------------------

    def _load_panel(self, start_date: str, end_date: str) -> Optional[Alpha191Panel]:
        """加载全市场宽面板（不复权日线 + daily_basic + 基准指数）。

        刻意不走 get_return_prices 的后复权路径：stk_factor 同步滞后时，
        长窗口下个股复权覆盖率 ≥50% 会触发"丢弃缺失复权价行"的分支，
        近期交易日被静默裁掉，截面残缺。Alpha191 公式以日内比率、量、
        截面排名为主，对复权不敏感；用不复权日线保证覆盖完整与序列
        内部一致。多日收益类因子的暴露（若有）应在公式评审时单独评估。
        """
        daily = self.data_reader.get_daily(
            ts_codes=None, start_date=start_date, end_date=end_date
        )
        if daily is None or daily.empty:
            return None

        daily["trade_date"] = pd.to_datetime(daily["trade_date"], errors="coerce")
        daily = daily.dropna(subset=["trade_date"])

        # vwap 口径与参考实现一致：amount(千元)*1000 / (vol(手)*100股)，
        # 量无效时回退 close
        daily["vwap"] = daily["close"]
        valid_volume = daily["vol"].notna() & (daily["vol"] != 0)
        daily.loc[valid_volume, "vwap"] = (
            daily.loc[valid_volume, "amount"] * 1000
            / (daily.loc[valid_volume, "vol"] * 100)
        )

        def to_wide(column: str) -> pd.DataFrame:
            return daily.pivot(
                index="trade_date", columns="ts_code", values=column
            ).sort_index()

        basic = self._load_basic(start_date, end_date)

        def basic_wide(column: str) -> Optional[pd.DataFrame]:
            if basic is None or basic.empty or column not in basic.columns:
                return None
            return basic.pivot(
                index="trade_date", columns="ts_code", values=column
            ).sort_index()

        benchmark_open, benchmark_close = self._load_benchmark_wide(
            panel_dates=to_wide("close").index
        )

        return Alpha191Panel(
            open=to_wide("open"),
            high=to_wide("high"),
            low=to_wide("low"),
            close=to_wide("close"),
            pre_close=to_wide("pre_close"),
            volume=to_wide("vol"),
            amount=to_wide("amount"),
            vwap=to_wide("vwap"),
            turnover_rate=basic_wide("turnover_rate"),
            volume_ratio=basic_wide("volume_ratio"),
            total_mv=basic_wide("total_mv"),
            circ_mv=basic_wide("circ_mv"),
            benchmark_open=benchmark_open,
            benchmark_close=benchmark_close,
        )

    def _load_basic(self, start_date: str, end_date: str) -> pd.DataFrame:
        try:
            basic = self.data_reader.get_daily_basic(
                ts_codes=None, start_date=start_date, end_date=end_date
            )
            if not basic.empty:
                basic["trade_date"] = pd.to_datetime(basic["trade_date"], errors="coerce")
            return basic
        except Exception as e:
            logger.warning(f"读取 daily_basic 失败，相关面板列为 None: {e}")
            return pd.DataFrame()

    def _load_benchmark_wide(self, panel_dates: pd.Index,
                             benchmark_code: str = "000300.SH"):
        """加载基准指数 open/close 宽序列（对齐面板日期）。

        本项目指数库存放在 data/index_daily/stock/ts_code=XX/data.parquet；
        A 股沪深300 的本地代码是 399300.SZ。数据缺失或区间不覆盖时返回
        (None, None)，基准因子结果自然为空。
        """
        local_code = BENCHMARK_INDEX_MAP.get(benchmark_code, benchmark_code)
        try:
            import glob
            import os

            pattern = os.path.join(
                self.data_reader.data_dir, "index_daily", "stock",
                f"ts_code={local_code}", "**", "*.parquet",
            )
            files = sorted(glob.glob(pattern, recursive=True))
            if not files:
                logger.warning(f"未找到基准指数数据 {local_code}，"
                               f"基准因子 {sorted(BENCHMARK_FACTORS)} 将为空")
                return None, None
            # 各分区文件 ts_code 列类型可能不一致（large_string vs
            # dictionary），逐文件读入后统一转 str 再合并
            frames = []
            for path in files:
                frame = pd.read_parquet(path)
                frame["ts_code"] = frame["ts_code"].astype(str)
                frames.append(frame)
            index_df = pd.concat(frames, ignore_index=True)
            index_df["trade_date"] = pd.to_datetime(
                index_df["trade_date"], errors="coerce", format="mixed"
            )
            index_df = index_df.dropna(subset=["trade_date"]).drop_duplicates(
                subset=["trade_date"], keep="last"
            ).sort_values("trade_date").set_index("trade_date")
            aligned_open = index_df["open"].reindex(panel_dates)
            aligned_close = index_df["close"].reindex(panel_dates)
            return aligned_open, aligned_close
        except Exception as e:
            logger.warning(f"加载基准指数 {local_code} 失败: {e}")
            return None, None

    @staticmethod
    def _to_long(wide: pd.DataFrame, factor_id: str) -> pd.DataFrame:
        """宽面板 → 标准长表。落库前统一清洗 ±inf（零方差滚动窗会产出
        inf，入库会污染下游 z_score 统计），与参考实现的源头清洗同口径。

        同时计算截面 percentile_rank / z_score（按 trade_date 分组，与
        FactorEngine._calculate_factor_stats 同口径）：打分链
        （stock_scoring）优先消费 z_score，缺失标准化列的因子实际进
        不了打分体系，这里源头补齐而不是靠事后回填。"""
        wide = wide.replace([np.inf, -np.inf], np.nan)
        long_df = wide.stack().rename("factor_value").reset_index()
        long_df.columns = ["trade_date", "ts_code", "factor_value"]
        long_df["factor_id"] = factor_id
        long_df = long_df.dropna(subset=["factor_value"])
        # 按 trade_date 分组的截面统计（单因子场景无需再按 factor_id 分）
        grouped = long_df.groupby("trade_date")["factor_value"]
        long_df["percentile_rank"] = grouped.rank(pct=True) * 100
        std = grouped.transform("std")
        mean = grouped.transform("mean")
        long_df["z_score"] = np.where(
            std.fillna(0) > 0,
            (long_df["factor_value"] - mean) / std.replace(0, np.nan),
            0.0,
        )
        long_df["trade_date"] = long_df["trade_date"].dt.strftime("%Y-%m-%d")
        return long_df[
            ["ts_code", "trade_date", "factor_id", "factor_value",
             "percentile_rank", "z_score"]
        ]
