"""因子计算作业（衍生计算）。

把 FactorEngine 的因子计算纳入 data_jobs 流水线：数据日更完成后运行
本作业，将内置因子与自定义表达式因子的值批量计算并写入 factor_values
存储，供打分/回测读取。

alpha191 因子（alpha_001~alpha_191）走全市场宽面板批量计算
（Alpha191FactorService.calculate_many：面板只加载一次），逐因子调用会
各自重复加载 400 天预热面板，量级上不可行。

Usage:
    python app/utils/factor_compute.py

环境变量（由 ScriptRunner 注入）:
    DATA_JOB_TRADE_DATE          单日模式：只算这个交易日
    DATA_JOB_START_DATE/_END_DATE 区间模式：计算整个区间（推荐回填用）
    DATA_JOB_PARAM_FACTOR_IDS    逗号分隔的因子列表；缺省算全部因子
    DATA_JOB_PARAM_TS_CODES      逗号分隔的股票列表；缺省全市场

两者都不传时默认计算最新交易日的全部因子。
"""
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from loguru import logger

from app.services.alpha191_factor_service import ALPHA191_FACTORS, computable_factors
from app.services.data_reader import ParquetDataReader
from app.services.factor_engine import FactorEngine


def _split_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _run_alpha191_batch(engine, alpha_ids, start_date, end_date, ts_codes,
                        per_factor_stats) -> int:
    """alpha191 宽面板批量：面板只加载一次，逐因子落库，返回成功行数。"""
    from app.services.alpha191_factor_service import Alpha191FactorService

    total = 0
    service = Alpha191FactorService(engine.data_reader)

    def _on_result(factor_id, long_df):
        nonlocal total
        if long_df is None or long_df.empty:
            per_factor_stats[factor_id] = 0
            return
        try:
            engine.save_factor_values(long_df)
            per_factor_stats[factor_id] = len(long_df)
            total += len(long_df)
        except Exception as exc:  # noqa: BLE001 - 单因子落库失败不中断批次
            logger.error(f"保存因子 {factor_id} 失败: {exc}")
            per_factor_stats[factor_id] = f"error: {exc}"

    service.calculate_many(
        alpha_ids, start_date, end_date, ts_codes=ts_codes,
        on_result=_on_result, collect_results=False,
    )
    return total


def main():
    engine = FactorEngine()

    trade_date = os.getenv("DATA_JOB_TRADE_DATE") or None
    start_date = os.getenv("DATA_JOB_START_DATE") or None
    end_date = os.getenv("DATA_JOB_END_DATE") or None
    factor_ids = _split_env("DATA_JOB_PARAM_FACTOR_IDS")
    ts_codes = _split_env("DATA_JOB_PARAM_TS_CODES")

    if not start_date and not end_date and not trade_date:
        # 默认：最新交易日
        all_dates = ParquetDataReader().get_trade_dates()
        if not all_dates:
            print("没有任何交易日数据，无法计算因子")
            sys.exit(1)
        trade_date = all_dates[-1]

    if not end_date:
        end_date = trade_date or start_date
    if not start_date:
        start_date = end_date or trade_date

    alpha_ids: list = []
    other_ids: list = []
    if factor_ids:
        alpha_ids = [fid for fid in factor_ids if fid in ALPHA191_FACTORS]
        other_ids = [fid for fid in factor_ids if fid not in ALPHA191_FACTORS]
    else:
        alpha_ids = sorted(computable_factors())

    total_saved = 0
    per_factor_stats = {}
    failed = 0
    attempted = 0

    if alpha_ids:
        # alpha191：区间一次算完（宽面板共享一次加载）
        attempted += 1
        try:
            total_saved += _run_alpha191_batch(
                engine, alpha_ids, start_date, end_date, ts_codes,
                per_factor_stats,
            )
        except Exception as e:
            failed += 1
            logger.error(f"alpha191 批量计算失败: {e}")

    if other_ids:
        # 指定普通因子：区间一次算完（内置因子支持任意区间）
        for factor_id in other_ids:
            attempted += 1
            try:
                result = engine.calculate_factor(
                    factor_id, ts_codes, start_date, end_date
                )
                if result.empty:
                    per_factor_stats[factor_id] = 0
                    continue
                engine.save_factor_values(result)
                per_factor_stats[factor_id] = len(result)
                total_saved += len(result)
            except Exception as e:
                failed += 1
                logger.error(f"计算因子 {factor_id} 失败: {e}")
                per_factor_stats[factor_id] = f"error: {e}"

    if not factor_ids:
        # 全部因子：calculate_all_factors 按单日截面计算内置与自定义因子
        # （alpha191 已在上方按区间批量算过，calculate_all_factors 会跳过它们）
        dates = ParquetDataReader().get_trade_dates(start_date, end_date)
        if not dates:
            print(f"区间 {start_date} ~ {end_date} 没有交易日数据")
            sys.exit(1)
        for date in dates:
            attempted += 1
            try:
                result = engine.calculate_all_factors(date, ts_codes)
            except Exception as e:
                failed += 1
                logger.error(f"计算 {date} 全部因子失败: {e}")
                continue
            if result.empty:
                per_factor_stats[str(date)] = 0
                continue
            engine.save_factor_values(result)
            per_factor_stats[str(date)] = len(result)
            total_saved += len(result)

    print(f"因子计算完成: {start_date} ~ {end_date}, 共写入 {total_saved} 条")
    print(per_factor_stats)

    # 零产出或全部失败必须以非零码退出：否则流水线把作业记成 success，
    # 缺失的因子值要等到回测覆盖率校验才暴露
    if attempted and total_saved == 0:
        print(f"{attempted} 个计算单元全部零产出，判定作业失败")
        sys.exit(1)
    if failed:
        print(
            f"警告: {failed}/{attempted} 个计算单元失败。部分成功不阻断流水线，"
            "缺失的因子值会被回测覆盖率校验拦截"
        )


if __name__ == "__main__":
    main()
