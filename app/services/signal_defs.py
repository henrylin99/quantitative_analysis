"""筹码信号定义：阈值 + 掩码规则 + 文案，扫描与回测服务共用。

历史上 ChipSignalService 与 ChipSignalBacktestService 各自硬编码一份阈值
（改一处漏一处），现统一从这里取。掩码函数同时兼容截面 Series（扫描）
与日期×股票 DataFrame（回测）两种形态。API 层可通过 SignalThresholds
覆盖默认值做参数实验。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Dict, Union

import pandas as pd

SIGNAL_LABELS = {
    "squeeze": "筹码挤压蓄势",
    "resonance": "资金×筹码多头共振",
    "divergence": "量价资金背离预警",
}


@dataclass(frozen=True)
class SignalThresholds:
    """三类筹码信号的阈值；字段即 API 可覆盖参数名。"""
    squeeze_winner_min: float = 60.0        # 获利盘下限：过半但未极端
    squeeze_conc_quantile: float = 0.20     # 集中度截面 20% 分位以内 = 高度集中
    squeeze_volume_ratio_max: float = 0.85  # 近5日均量 / 近20日均量，收缩阈值
    squeeze_pct5d_max: float = 0.10         # 排除已大涨的票
    resonance_winner_lo: float = 30.0       # 获利盘抬升区间下限
    resonance_winner_hi: float = 70.0       # 上限（拥挤区外）
    divergence_pct5d_min: float = 0.03
    divergence_winner_min: float = 70.0

    @classmethod
    def from_params(cls, params: Union[dict, None]) -> "SignalThresholds":
        """从请求参数构造：未知键忽略，非法/越界值回退默认。"""
        if not params:
            return cls()
        allowed = {f.name: f for f in dataclasses.fields(cls)}
        clean: Dict[str, float] = {}
        for key, value in params.items():
            if key not in allowed or value is None or value == "":
                continue
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            if not pd.api.types.is_number(num) or pd.isna(num):
                continue
            clean[key] = num
        return cls(**clean)

    def signature(self) -> tuple:
        """缓存键：任一阈值不同则缓存不同。"""
        return tuple(getattr(self, f.name) for f in dataclasses.fields(self))


DEFAULT_THRESHOLDS = SignalThresholds()


def _le(value, thresh):
    """value <= thresh；DataFrame 对按行 Series 阈值（逐日截面分位）走行对齐。"""
    if isinstance(value, pd.DataFrame) and isinstance(thresh, pd.Series):
        return value.le(thresh, axis=0)
    return value <= thresh


def squeeze_mask(winner, conc, conc_thresh, vol_ratio, pct5,
                 t: SignalThresholds = DEFAULT_THRESHOLDS):
    """挤压蓄势：获利盘过半 + 筹码高度集中 + 量能收缩 + 未大涨。"""
    return (
        (winner >= t.squeeze_winner_min)
        & _le(conc, conc_thresh)
        & (vol_ratio <= t.squeeze_volume_ratio_max)
        & (pct5.fillna(0) <= t.squeeze_pct5d_max)
    )


def resonance_mask(net5, net_last, winner_chg, winner, pct5,
                   t: SignalThresholds = DEFAULT_THRESHOLDS):
    """多头共振：主力连续净流入 + 获利盘抬升且未拥挤 + 上涨。"""
    return (
        (net5 > 0) & (net_last > 0) & (winner_chg > 0)
        & (winner >= t.resonance_winner_lo)
        & (winner <= t.resonance_winner_hi)
        & (pct5.fillna(0) > 0)
    )


def divergence_mask(pct5, net5, winner,
                    t: SignalThresholds = DEFAULT_THRESHOLDS):
    """背离预警：上涨但主力净流出 + 获利盘高位。"""
    return (
        (pct5.fillna(0) >= t.divergence_pct5d_min)
        & (net5 < 0)
        & (winner >= t.divergence_winner_min)
    )


def signal_definitions(t: SignalThresholds = DEFAULT_THRESHOLDS,
                       conc_thresh: float = None) -> Dict[str, str]:
    """三类信号的自然语言定义（供前端展示）；conc_thresh 用于展示当日实际分位值。"""
    conc_part = f"≤截面{int(t.squeeze_conc_quantile * 100)}%分位"
    if conc_thresh is not None:
        conc_part += f"（≤{conc_thresh:.2f}）"
    return {
        "squeeze": (
            f"获利盘≥{t.squeeze_winner_min:g}% 且 90%筹码区间宽度{conc_part} "
            f"且量能收缩（5日均量/20日均量≤{t.squeeze_volume_ratio_max:g}） "
            f"且5日涨幅≤{t.squeeze_pct5d_max:.0%}"
        ),
        "resonance": (
            f"近5日主力净额>0 且最新一日仍净流入，获利盘5日抬升且处于 "
            f"{t.resonance_winner_lo:g}%~{t.resonance_winner_hi:g}% 区间，5日上涨"
        ),
        "divergence": (
            f"5日涨幅≥{t.divergence_pct5d_min:.0%} 且近5日主力净流出， "
            f"获利盘≥{t.divergence_winner_min:g}%"
        ),
    }
