from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

try:
    from .feature_engine import add_features, add_financial_features
    from .yfinance_client import (
        FetchConfig,
        fetch_all_data,
        fetch_financial_metrics,
        fetch_history_batch,
        fetch_stock_info,
        get_stock_pool,
        load_config,
        StockInfo,
    )
    from .scorer import compute_scores
except ImportError:
    from feature_engine import add_features, add_financial_features
    from yfinance_client import (
        FetchConfig,
        fetch_all_data,
        fetch_financial_metrics,
        fetch_history_batch,
        fetch_stock_info,
        get_stock_pool,
        load_config,
        StockInfo,
    )
    from scorer import compute_scores

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = ROOT_DIR / "data" / "us_snapshot.parquet"
DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"

# 快照必需列
REQUIRED_SNAPSHOT_COLUMNS = ["symbol", "name", "trade_date", "close"]

# 数值列（用于类型转换）
NUMERIC_SNAPSHOT_COLUMNS = [
    # 价格数据
    "open", "high", "low", "close", "pre_close", "change", "pct_change",
    "volume", "amount", "total_share",
    # 技术指标
    "ma5", "ma10", "ma20", "ma60",
    "ret_1d", "ret_5d", "ret_20d",
    "vol_ratio_5", "amplitude", "body_ratio",
    "upper_shadow_ratio", "lower_shadow_ratio",
    # 财务指标
    "market_cap", "forward_pe", "trailing_pe", "price_to_book",
    "revenue_growth", "earnings_growth",
    "roe", "profit_margin",
    "peg_ratio", "ps_ratio", "roa", "operating_margin",
    "debt_to_equity", "current_ratio",
    "dividend_yield", "dividend_rate",
    # signal_score is intentionally excluded: compute_scores() returns float64,
    # so pd.to_numeric coercion would be a no-op (column doesn't exist yet at
    # the point this loop runs — it's assigned after the loop).
]

HISTORY_COLUMNS = [
    "symbol", "day",
    "open", "high", "low", "close", "volume",
    "ma5", "ma20", "ma60",
    "pattern_bull_candle", "pattern_bear_candle", "pattern_hammer",
    "pattern_shooting_star", "pattern_doji", "pattern_long_upper_shadow",
    "pattern_long_lower_shadow", "pattern_bullish_engulfing",
    "pattern_bearish_engulfing", "pattern_inside_bar",
    "pattern_three_white_soldiers", "pattern_three_black_crows",
    "pattern_ma_bull", "pattern_trend_confirm", "pattern_pullback_hold",
    "pattern_double_bottom", "pattern_platform_breakout",
    "pattern_false_breakout", "pattern_volume_breakout",
    "pattern_volume_shrink_pullback", "pattern_volatility_contraction",
    "pattern_volatility_expansion", "break_high_20", "break_high_60",
    "consec_up_3", "consec_up_5",
]


def _build_snapshot_from_data(
    history_data: dict,
    stock_info: dict,
    financial_metrics: dict,
) -> pd.DataFrame:
    snapshot_rows = []
    failed_symbols = []

    for symbol, history_df in history_data.items():
        try:
            row = _build_symbol_snapshot(
                symbol=symbol,
                history_df=history_df,
                info=stock_info.get(symbol),
                financials=financial_metrics.get(symbol, {}),
            )
            if row is not None:
                snapshot_rows.append(row)
        except Exception as e:
            logger.warning(f"Failed to build snapshot for {symbol}: {e}")
            failed_symbols.append(symbol)

    if not snapshot_rows:
        raise RuntimeError("Failed to build snapshot: no valid symbols")

    logger.info(f"Built snapshot: {len(snapshot_rows)} successful, {len(failed_symbols)} failed")

    snapshot = pd.DataFrame(snapshot_rows)

    for col in NUMERIC_SNAPSHOT_COLUMNS:
        if col in snapshot.columns:
            snapshot[col] = pd.to_numeric(snapshot[col], errors="coerce")

    for col in REQUIRED_SNAPSHOT_COLUMNS:
        if col not in snapshot.columns:
            snapshot[col] = pd.NA

    # Compute pool-wide signal score — must run after full DataFrame is assembled
    # because percentile ranking requires all rows
    snapshot["signal_score"] = compute_scores(snapshot)

    return snapshot.sort_values("symbol").reset_index(drop=True)


def build_snapshot_dataframe(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> pd.DataFrame:
    """
    构建快照 DataFrame

    Returns:
        包含所有股票最新数据的 DataFrame
    """
    history_data, stock_info, financial_metrics = fetch_all_data(
        config_path=config_path,
    )
    return _build_snapshot_from_data(history_data, stock_info, financial_metrics)


def build_history_dataframe(history_data: dict) -> pd.DataFrame:
    frames = []
    for symbol, df in history_data.items():
        if df.empty:
            continue
        try:
            featured = add_features(df)
        except Exception as e:
            logger.warning(f"Skipping history for {symbol}: {e}")
            continue
        if featured.empty:
            continue
        featured = featured.assign(symbol=symbol)
        available = [c for c in HISTORY_COLUMNS if c in featured.columns]
        frames.append(featured[available])
    if not frames:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def _build_symbol_snapshot(
    symbol: str,
    history_df: pd.DataFrame,
    info: StockInfo | None,
    financials: dict,
) -> dict | None:
    """
    为单只股票构建快照行

    Args:
        symbol: 股票代码
        history_df: 历史行情数据
        info: 股票基本信息
        financials: 财务指标

    Returns:
        快照行字典，如果构建失败返回 None
    """
    if history_df.empty:
        return None

    # 添加技术指标
    featured = add_features(history_df)
    if featured.empty:
        return None

    # 添加财务指标
    if financials:
        featured = add_financial_features(featured, financials)

    # 获取最新一行
    latest = featured.iloc[-1].to_dict()

    # 计算 amount (成交额 = volume * close)
    volume = latest.get("volume")
    close = latest.get("close")
    amount = None
    if pd.notna(volume) and pd.notna(close):
        amount = volume * close

    # 转换字段名
    return {
        "symbol": symbol,
        "name": info.name if info else None,
        "trade_date": latest.get("day"),
        "open": latest.get("open"),
        "high": latest.get("high"),
        "low": latest.get("low"),
        "close": latest.get("close"),
        "pre_close": latest.get("pre_close"),
        "change": latest.get("change"),
        "pct_change": latest.get("pct_change"),
        "volume": volume,
        "amount": amount,
        "total_share": info.total_share if info else None,
        # 技术指标
        "ma5": latest.get("ma5"),
        "ma10": latest.get("ma10"),
        "ma20": latest.get("ma20"),
        "ma60": latest.get("ma60"),
        "ret_1d": latest.get("ret_1d"),
        "ret_5d": latest.get("ret_5d"),
        "ret_20d": latest.get("ret_20d"),
        "vol_ratio_5": latest.get("vol_ratio_5"),
        "amplitude": latest.get("amplitude"),
        "body_ratio": latest.get("body_ratio"),
        "upper_shadow_ratio": latest.get("upper_shadow_ratio"),
        "lower_shadow_ratio": latest.get("lower_shadow_ratio"),
        # K线形态
        "pattern_bull_candle": latest.get("pattern_bull_candle"),
        "pattern_bear_candle": latest.get("pattern_bear_candle"),
        "pattern_hammer": latest.get("pattern_hammer"),
        "pattern_shooting_star": latest.get("pattern_shooting_star"),
        "pattern_doji": latest.get("pattern_doji"),
        "pattern_bullish_engulfing": latest.get("pattern_bullish_engulfing"),
        "pattern_bearish_engulfing": latest.get("pattern_bearish_engulfing"),
        "pattern_ma_bull": latest.get("pattern_ma_bull"),
        "pattern_trend_confirm": latest.get("pattern_trend_confirm"),
        "pattern_pullback_hold": latest.get("pattern_pullback_hold"),
        "pattern_double_bottom": latest.get("pattern_double_bottom"),
        "pattern_volume_breakout": latest.get("pattern_volume_breakout"),
        "pattern_long_upper_shadow": latest.get("pattern_long_upper_shadow"),
        "pattern_long_lower_shadow": latest.get("pattern_long_lower_shadow"),
        "pattern_inside_bar": latest.get("pattern_inside_bar"),
        "pattern_three_white_soldiers": latest.get("pattern_three_white_soldiers"),
        "pattern_three_black_crows": latest.get("pattern_three_black_crows"),
        "pattern_platform_breakout": latest.get("pattern_platform_breakout"),
        "pattern_false_breakout": latest.get("pattern_false_breakout"),
        "pattern_volume_shrink_pullback": latest.get("pattern_volume_shrink_pullback"),
        "pattern_volatility_contraction": latest.get("pattern_volatility_contraction"),
        "pattern_volatility_expansion": latest.get("pattern_volatility_expansion"),
        "break_high_20": latest.get("break_high_20"),
        "break_high_60": latest.get("break_high_60"),
        "consec_up_3": latest.get("consec_up_3"),
        "consec_up_5": latest.get("consec_up_5"),
        # 财务指标
        "market_cap": latest.get("market_cap"),
        "forward_pe": latest.get("forward_pe"),
        "trailing_pe": latest.get("trailing_pe"),
        "price_to_book": latest.get("price_to_book"),
        "peg_ratio": latest.get("peg_ratio"),
        "ps_ratio": latest.get("ps_ratio"),
        "revenue_growth": latest.get("revenue_growth"),
        "earnings_growth": latest.get("earnings_growth"),
        "roe": latest.get("roe"),
        "roa": latest.get("roa"),
        "profit_margin": latest.get("profit_margin"),
        "operating_margin": latest.get("operating_margin"),
        "debt_to_equity": latest.get("debt_to_equity"),
        "current_ratio": latest.get("current_ratio"),
        "dividend_yield": latest.get("dividend_yield"),
        "dividend_rate": latest.get("dividend_rate"),
        # 风险指标
        "risk_ma20_dev": latest.get("risk_ma20_dev"),
        "risk_ma60_dev": latest.get("risk_ma60_dev"),
        "risk_dd_20d": latest.get("risk_dd_20d"),
        "risk_vol_20d": latest.get("risk_vol_20d"),
    }


def _fill_missing_symbols(
    history_data: dict,
    stock_info: dict,
    financial_metrics: dict,
    config_path: Path,
) -> None:
    """Yahoo 端瞬时 TLS/断连会让批量抓取随机缺几只股；对池内缺失股逐一重试补齐，
    避免整份快照静默缺股。补不回的（如确已退市）如实跳过。"""
    config = load_config(config_path)
    pool = get_stock_pool(config)
    missing = [s for s in pool if s not in history_data]
    if not missing:
        return
    logger.warning(f"批量抓取缺 {len(missing)} 只，逐一补抓: {missing}")
    fetch_cfg = FetchConfig(
        history_period=config.get("fetch", {}).get("history_period", "2y"),
        batch_size=1,
        batch_delay=1.0,
        max_retries=3,
        retry_delay=4.0,
        request_timeout=30,
    )
    financials_enabled = config.get("financials", {}).get("enabled", True)
    for sym in missing:
        try:
            hist = fetch_history_batch([sym], fetch_cfg).get(sym)
            if hist is None or hist.empty:
                logger.warning(f"补抓无行情，跳过: {sym}")
                continue
            history_data[sym] = hist
            try:
                stock_info[sym] = fetch_stock_info(sym)
            except Exception as e:
                logger.warning(f"补抓 {sym} 基本信息失败: {e}")
            if financials_enabled:
                try:
                    financial_metrics[sym] = fetch_financial_metrics(sym)
                except Exception as e:
                    logger.warning(f"补抓 {sym} 财务指标失败: {e}")
            logger.info(f"补抓成功: {sym}")
        except Exception as e:
            logger.warning(f"补抓 {sym} 失败: {e}")


def build_snapshot(
    *,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> pd.DataFrame:
    """
    构建快照并保存到 parquet 文件
    """
    history_data, stock_info, financial_metrics = fetch_all_data(config_path=config_path)
    _fill_missing_symbols(history_data, stock_info, financial_metrics, config_path)

    snapshot = _build_snapshot_from_data(history_data, stock_info, financial_metrics)
    resolved_output_path = Path(output_path)
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.to_parquet(resolved_output_path, index=False)

    history = build_history_dataframe(history_data)
    history.to_parquet(resolved_output_path.parent / "us_history.parquet", index=False)
    logger.info(f"Wrote us_history.parquet: {len(history)} rows")

    return snapshot


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build HK stock screener snapshot using yfinance")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Parquet output path",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Config file path",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    snapshot = build_snapshot(
        output_path=args.output,
        config_path=Path(args.config),
    )
    print(f"Wrote {len(snapshot)} rows to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
