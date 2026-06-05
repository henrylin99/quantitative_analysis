from __future__ import annotations


def bs_style_code_to_tdx(value: str) -> tuple[int, str]:
    text = str(value).strip().lower()
    if text.startswith("sz."):
        return 0, text.split(".", 1)[1]
    if text.startswith("sh."):
        return 1, text.split(".", 1)[1]
    raise ValueError(f"unsupported bs-style code: {value}")


def any_style_code_to_tdx(value: str) -> tuple[int, str]:
    text = str(value).strip()
    lower_text = text.lower()
    if lower_text.startswith(("sz.", "sh.")):
        return bs_style_code_to_tdx(lower_text)
    if lower_text.endswith(".sz"):
        return 0, text.split(".", 1)[0]
    if lower_text.endswith(".sh"):
        return 1, text.split(".", 1)[0]
    raise ValueError(f"unsupported stock code: {value}")


def tdx_market_code_to_bs_style(market: int, code: str) -> str:
    market_prefix = "sz" if int(market) == 0 else "sh"
    return f"{market_prefix}.{str(code).strip()}"
