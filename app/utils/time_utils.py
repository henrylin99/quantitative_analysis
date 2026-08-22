"""统一的时间戳工具。

本项目的数据（Baostock 分钟线、Tushare 交易日）均为北京时间语义，
历史上状态层用 naive utcnow() 而实时层用 naive 本地 now()，两边相差 8 小时，
导致"最近 1 小时"这类跨层比较错位。统一约定：

- 所有内部时间戳使用服务器本地时间的 naive datetime（生产容器设置
  TZ=Asia/Shanghai 后即北京时间），由这里的 helper 生成
- 需要明确时区语义时使用 now_beijing()（tz-aware）

不要在业务代码里直接调用 datetime.utcnow()/datetime.now()。
"""

from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))


def now_local() -> datetime:
    """服务器本地时间的 naive datetime（容器 TZ=Asia/Shanghai 时即北京时间）。"""
    return datetime.now()


def now_local_iso() -> str:
    """内部状态存储统一使用的时间戳字符串。"""
    return now_local().isoformat()


def now_beijing() -> datetime:
    """带时区的北京时间（与本地无关，用于明确的时区语义场景）。"""
    return datetime.now(BEIJING_TZ)
