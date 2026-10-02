"""Alpha191 内置因子计算脚本 — 批量计算并落库 factor_values。

Usage:
    python scripts/compute_alpha191.py --start 2026-09-01 --end 2026-09-22
    python scripts/compute_alpha191.py alpha_001 alpha_002 --start 2026-09-01
    python scripts/compute_alpha191.py --list

结果写入 data/ml_factor_state/factor_values（按交易日分区，与因子中心同库），
按 (ts_code, trade_date, factor_id) 去重，可安全重跑。

说明：
- 全部因子共享一次全市场面板加载（预热 400 自然日，覆盖 252 交易日窗口）；
- alpha_030 / alpha_143 始终跳过（参考实现即不可计算）；
- alpha_075/149/181/182 依赖基准指数，指数数据不覆盖区间时自动跳过；
- ts_rank / decay_linear 等算子已向量化，单因子秒级。
"""
import sys
import argparse
import logging
from datetime import datetime, timedelta

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="批量计算 Alpha191 内置因子并入库")
    parser.add_argument(
        "factor_names", nargs="*", default=None,
        help="因子名（如 alpha_001），缺省为全部可计算因子",
    )
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD",
                        help="开始日期，缺省为 end 往前 60 个自然日")
    parser.add_argument("--end", default=None, metavar="YYYY-MM-DD",
                        help="结束日期，缺省为今天")
    parser.add_argument("--list", action="store_true", help="列出因子清单后退出")
    parser.add_argument("--include-skip", action="store_true",
                        help="连跳过清单因子一起传给服务（默认剔除）")
    return parser.parse_args()


def main():
    from app.services.alpha191_factor_service import (
        ALPHA191_FACTORS,
        Alpha191FactorService,
        computable_factors,
    )
    from app.services.factor_engine import FactorEngine

    args = parse_args()

    if args.list:
        for item in Alpha191FactorService.list_factors():
            skip = f"  [跳过: {item['skip_reason']}]" if "skip_reason" in item else ""
            bench = "  [需基准指数]" if item["needs_benchmark"] else ""
            log.info(f"{item['factor_id']}: {item['name']}{bench}{skip}")
        return

    end_date = args.end or datetime.now().strftime("%Y-%m-%d")
    start_date = args.start or (
        datetime.now() - timedelta(days=60)
    ).strftime("%Y-%m-%d")

    if args.factor_names:
        factor_names = args.factor_names
        invalid = [n for n in factor_names if n not in ALPHA191_FACTORS]
        if invalid:
            sys.exit(f"未知因子: {invalid}，用 --list 查看可用清单")
    else:
        factor_names = list(computable_factors())

    engine = FactorEngine()
    service = Alpha191FactorService(engine.data_reader)

    saved: dict = {}
    skipped: dict = {}

    def save_result(factor_id: str, long_df) -> None:
        if engine.save_factor_values(long_df):
            saved[factor_id] = (len(long_df), long_df["trade_date"].nunique())
        else:
            skipped[factor_id] = "入库失败"

    log.info(f"开始计算 {len(factor_names)} 个因子: {start_date} → {end_date}")
    results = service.calculate_many(
        factor_names, start_date, end_date, on_result=save_result,
        collect_results=False,
    )

    # calculate_many 返回值里包含未落库的（on_result 异常兜底），值为行数
    for factor_id, row_count in results.items():
        if factor_id not in saved and factor_id not in skipped:
            skipped[factor_id] = f"未落库（on_result 未调用，共 {row_count} 行）"

    # 没算出来的 = 显式跳过或区间内无有效值
    computed = set(saved) | set(skipped)
    for factor_id in factor_names:
        if factor_id not in computed:
            skipped[factor_id] = "区间内无有效值或计算失败（详见日志）"

    log.info(f"完成: 入库 {len(saved)} 个因子")
    for factor_id, (rows, days) in sorted(saved.items()):
        log.info(f"  ✓ {factor_id}: {rows} 行 / {days} 交易日")
    if skipped:
        log.warning(f"未入库 {len(skipped)} 个:")
        for factor_id, reason in sorted(skipped.items()):
            log.warning(f"  - {factor_id}: {reason}")


if __name__ == "__main__":
    main()
