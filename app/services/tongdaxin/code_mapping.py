from __future__ import annotations


def bs_style_code_to_tdx(value: str) -> tuple[int, str]:
    text = str(value).strip().lower()
    if text.startswith("sz."):
        return 0, text.split(".", 1)[1]
    if text.startswith("sh."):
        return 1, text.split(".", 1)[1]
    if text.startswith("bj."):
        # 北交所：TDX market=2（2026-10-11 实测 117.34.114.x 可返回 920 开头 bars）
        return 2, text.split(".", 1)[1]
    raise ValueError(f"unsupported bs-style code: {value}")


def any_style_code_to_tdx(value: str) -> tuple[int, str]:
    text = str(value).strip()
    lower_text = text.lower()
    if lower_text.startswith(("sz.", "sh.", "bj.")):
        return bs_style_code_to_tdx(lower_text)
    if lower_text.endswith(".sz"):
        return 0, text.split(".", 1)[0]
    if lower_text.endswith(".sh"):
        return 1, text.split(".", 1)[0]
    if lower_text.endswith(".bj"):
        return 2, text.split(".", 1)[0]
    # 纯数字代码：0/3 开头 → 深市(0)，6 开头 → 沪市(1)，4/8/920 开头 → 北交所(2)
    if text.isdigit():
        if text[0] in ("0", "3"):
            return 0, text
        if text.startswith("6"):
            return 1, text
        return 2, text
    raise ValueError(f"unsupported stock code: {value}")


def tdx_market_code_to_bs_style(market: int, code: str) -> str:
    market_prefix = {0: "sz", 1: "sh", 2: "bj"}.get(int(market), "sh")
    return f"{market_prefix}.{str(code).strip()}"
