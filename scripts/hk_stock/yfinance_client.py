"""
yfinance 客户端 - 替代 Aliyun API

功能：
1. 从配置文件加载股票池
2. 分批下载历史行情数据
3. 获取单只股票的详细信息
4. 获取财务指标
5. 错误处理和日志记录
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
import yaml

logger = logging.getLogger(__name__)


@dataclass
class FetchConfig:
    """数据获取配置"""
    history_period: str = "2y"
    batch_size: int = 20
    batch_delay: float = 1.0
    max_retries: int = 2
    retry_delay: float = 2.0
    request_timeout: int = 30
    symbol_delay: float = 0.1  # 单只股票请求间隔秒数


@dataclass
class StockInfo:
    """股票信息"""
    symbol: str
    name: str | None = None
    market_cap: float | None = None
    total_share: float | None = None


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """加载配置文件"""
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_stock_pool(config: dict[str, Any] | None = None) -> list[str]:
    """获取股票池列表"""
    if config is None:
        config = load_config()

    pool = config.get("stock_pool", {})

    # 遍历所有分组，合并去重
    all_stocks = []
    for stocks in pool.values():
        all_stocks.extend(stocks)
    return list(dict.fromkeys(all_stocks))


def _normalize_history_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    标准化历史数据 DataFrame

    yfinance 返回的列名: Open, High, Low, Close, Adj Close, Volume
    转换为: open, high, low, close, volume
    """
    if df.empty:
        return df

    # 重置索引，Date 变为列
    df = df.reset_index()

    # 标准化列名
    column_map = {
        "Date": "day",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    }

    df = df.rename(columns=column_map)

    # 确保日期格式
    if "day" in df.columns:
        df["day"] = pd.to_datetime(df["day"])

    # 选择需要的列
    required_cols = ["day", "open", "high", "low", "close", "volume"]
    existing_cols = [c for c in required_cols if c in df.columns]
    df = df[existing_cols]

    # 极低流动性股票当日尚未成交时，yfinance 会补一根全 NaN 的空 K 线；
    # 丢弃无 close 的 bar，让快照/图表回退到最后一根有效 K 线
    if "close" in df.columns:
        df = df.dropna(subset=["close"])

    return df


def fetch_history_batch(
    symbols: list[str],
    config: FetchConfig | None = None,
) -> dict[str, pd.DataFrame]:
    """
    批量下载历史行情数据

    Args:
        symbols: 股票代码列表
        config: 获取配置

    Returns:
        dict[str, pd.DataFrame]: symbol -> 历史数据DataFrame
    """
    if config is None:
        cfg = load_config()
        fetch_cfg = FetchConfig(**cfg.get("fetch", {}))
    else:
        fetch_cfg = config

    results = {}
    failed_symbols = []

    # 分批处理
    for i in range(0, len(symbols), fetch_cfg.batch_size):
        batch = symbols[i:i + fetch_cfg.batch_size]

        for attempt in range(fetch_cfg.max_retries + 1):
            try:
                # 批量下载
                data = yf.download(
                    batch,
                    period=fetch_cfg.history_period,
                    progress=False,
                    timeout=fetch_cfg.request_timeout,
                )

                # 处理返回数据
                # yfinance >= 0.2.6x 即使单只票也返回 (Price, Ticker) MultiIndex 列，
                # 单/多只统一按 Ticker level 拆分
                if len(batch) == 1 and not isinstance(data.columns, pd.MultiIndex):
                    # 单只股票且列为扁平 DataFrame（旧版 yfinance）
                    results[batch[0]] = _normalize_history_df(data)
                else:
                    ticker_level = "Ticker" if "Ticker" in data.columns.names else 1
                    available_tickers = set(data.columns.get_level_values(ticker_level))
                    for symbol in batch:
                        if symbol in available_tickers:
                            symbol_data = data.xs(symbol, axis=1, level=ticker_level)
                            results[symbol] = _normalize_history_df(symbol_data)
                        else:
                            failed_symbols.append(symbol)

                logger.info(f"Batch {i//fetch_cfg.batch_size + 1}: fetched {len(batch)} symbols")
                break

            except Exception as e:
                if attempt < fetch_cfg.max_retries:
                    logger.warning(f"Retry {attempt + 1}/{fetch_cfg.max_retries} for batch {batch}: {e}")
                    time.sleep(fetch_cfg.retry_delay)
                else:
                    logger.error(f"Failed to fetch batch {batch}: {e}")
                    failed_symbols.extend(batch)

        # 批次间隔
        if i + fetch_cfg.batch_size < len(symbols):
            time.sleep(fetch_cfg.batch_delay)

    if failed_symbols:
        logger.warning(f"Failed to fetch {len(set(failed_symbols))} symbols: {set(failed_symbols)}")

    return results


def fetch_stock_info(symbol: str) -> StockInfo:
    """获取单只股票的基本信息"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        return StockInfo(
            symbol=symbol,
            name=info.get("longName") or info.get("shortName"),
            market_cap=info.get("marketCap"),
            total_share=info.get("sharesOutstanding"),
        )
    except Exception as e:
        logger.warning(f"Failed to fetch info for {symbol}: {e}")
        return StockInfo(symbol=symbol)


def fetch_financial_metrics(symbol: str) -> dict[str, Any]:
    """
    获取财务指标

    Returns:
        dict: 包含估值、成长、盈利能力、财务健康等指标
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        return {
            # 估值指标
            "market_cap": info.get("marketCap"),
            "forward_pe": info.get("forwardPE"),
            "trailing_pe": info.get("trailingPE"),
            "price_to_book": info.get("priceToBook"),
            "peg_ratio": info.get("pegRatio"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),

            # 成长指标
            "revenue_growth": info.get("revenueQuarterlyGrowth"),
            "earnings_growth": info.get("earningsQuarterlyGrowth"),

            # 盈利能力
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            "profit_margin": info.get("profitMargins"),
            "operating_margin": info.get("operatingMargins"),

            # 财务健康
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),

            # 股息
            "dividend_yield": info.get("dividendYield"),
            "dividend_rate": info.get("dividendRate"),
        }
    except Exception as e:
        logger.warning(f"Failed to fetch financials for {symbol}: {e}")
        return {}


def fetch_all_data(
    symbols: list[str] | None = None,
    config_path: str | Path | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, StockInfo], dict[str, dict[str, Any]]]:
    """
    获取所有数据：历史行情 + 股票信息 + 财务指标

    Returns:
        (history_data, stock_info, financial_metrics)
    """
    config = load_config(config_path)

    if symbols is None:
        symbols = get_stock_pool(config)

    fetch_cfg = FetchConfig(**config.get("fetch", {}))
    financials_enabled = config.get("financials", {}).get("enabled", True)

    # 1. 批量获取历史行情
    logger.info(f"Fetching history for {len(symbols)} symbols...")
    history_data = fetch_history_batch(symbols, fetch_cfg)

    if not history_data:
        raise RuntimeError("Failed to fetch any history data")

    # 2. 获取股票信息
    logger.info(f"Fetching stock info for {len(history_data)} symbols...")
    stock_info = {}
    for symbol in history_data.keys():
        stock_info[symbol] = fetch_stock_info(symbol)
        time.sleep(fetch_cfg.symbol_delay)

    # 3. 获取财务指标
    financial_metrics = {}
    if financials_enabled:
        logger.info(f"Fetching financial metrics for {len(history_data)} symbols...")
        for symbol in history_data.keys():
            financial_metrics[symbol] = fetch_financial_metrics(symbol)
            time.sleep(fetch_cfg.symbol_delay)

    success_count = len(history_data)
    failed_count = len(symbols) - success_count
    logger.info(f"Completed: {success_count} successful, {failed_count} failed")

    return history_data, stock_info, financial_metrics
