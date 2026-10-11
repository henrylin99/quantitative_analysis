"""分钟数据链路股票代码风格统一。

历史沿革：Baostock / 通达信同步链路写入的是 ``sz.000001`` 风格，
而项目其余数据（stock_basic / stk_factor / factor_values / index_basic）
统一使用 tushare 风格 ``000001.SZ``。自 2026-10 起存储规范定为 tushare
风格：写侧经 :func:`normalize_minute_code` 归一，存量分区由
``scripts/migrate_minute_codes.py`` 迁移；读侧查询接受任意风格
（:func:`minute_code_aliases` 生成候选集），旧风格输入仅 debug 提示。
"""

from __future__ import annotations


def normalize_minute_code(value: str) -> str:
    """任意常见风格 → tushare 风格（如 ``sz.000001`` / ``000001`` → ``000001.SZ``）。

    无法识别的风格原样返回（写侧不丢数据），由调用方自行处理。
    """
    text = str(value).strip()
    if not text:
        return text
    lower = text.lower()

    # sz.000001 / sh.600000 / bj.832000
    if len(lower) == 9 and lower[:1] in ("s", "b") and lower[2] == ".":
        market = {"sz": "SZ", "sh": "SH", "bj": "BJ"}.get(lower[:2])
        symbol = lower[3:]
        if market and symbol.isdigit() and len(symbol) == 6:
            return f"{symbol}.{market}"

    # 000001.SZ / 000001.sz
    if "." in text:
        symbol, _, market = text.partition(".")
        if symbol.isdigit() and len(symbol) == 6 and market.upper() in ("SH", "SZ", "BJ"):
            return f"{symbol}.{market.upper()}"

    # 纯 6 位数字：按交易所规则推断后缀
    if text.isdigit() and len(text) == 6:
        return f"{text}.{_bare_market_suffix(text)}"

    return text


def _bare_market_suffix(symbol: str) -> str:
    if symbol.startswith("6"):
        return "SH"
    if symbol.startswith(("4", "8")) or symbol.startswith("920"):
        return "BJ"
    return "SZ"


def is_tushare_style(value: str) -> bool:
    text = str(value).strip()
    if "." not in text:
        return False
    symbol, _, market = text.partition(".")
    return symbol.isdigit() and len(symbol) == 6 and market in ("SH", "SZ", "BJ")


def minute_code_aliases(value: str) -> set[str]:
    """查询输入 → 可能存在于存储中的代码候选集（含迁移前旧风格）。"""
    canonical = normalize_minute_code(value)
    aliases = {str(value).strip(), canonical}

    text = str(value).strip()
    lower = text.lower()
    symbol = canonical.split(".")[0] if "." in canonical else text

    # 兼容前端直接传入的 6 位纯数字代码
    if lower.isdigit() and len(lower) == 6:
        for market in ("SH", "SZ", "BJ"):
            aliases.add(f"{lower}.{market}")
            aliases.add(f"{market.lower()}.{lower}")

    if lower.startswith(("sh.", "sz.", "bj.")):
        market = lower[:2].upper()
        aliases.add(f"{symbol}.{market}")
    elif lower.endswith((".sh", ".sz", ".bj")):
        market = lower.split(".", 1)[1].upper()
        aliases.add(f"{market.lower()}.{symbol}")

    return {alias for alias in aliases if alias}
