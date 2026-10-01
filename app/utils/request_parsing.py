"""查询参数解析：统一 page/limit 等整型参数的校验口径。

非法值抛 ValueError，由调用方转成 400；不直接裸 int() 避免
畸形参数打穿到 500 或生成超大查询。
"""

from typing import Optional

from flask import request


def parse_int_arg(
    name: str,
    default: int,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
) -> int:
    """从 query string 读取整型参数，缺失时返回 default。

    非整数或越出 [min_val, max_val] 时抛 ValueError（消息可直接返回给客户端）。
    """
    raw = request.args.get(name)
    if raw is None or raw == '':
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"参数 {name} 必须为整数，收到: {raw!r}")
    if min_val is not None and value < min_val:
        raise ValueError(f"参数 {name} 不能小于 {min_val}")
    if max_val is not None and value > max_val:
        raise ValueError(f"参数 {name} 不能大于 {max_val}")
    return value
