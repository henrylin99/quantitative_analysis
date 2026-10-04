"""因子计算作业（衍生计算）。

把 FactorEngine 的因子计算纳入 data_jobs 流水线：数据日更完成后运行
本作业，将内置因子与自定义表达式因子的值批量计算并写入 factor_values
存储，供打分/回测读取。

alpha191 因子（alpha_001~alpha_191）走全市场宽面板批量计算
（Alpha191FactorService.calculate_many：面板只加载一次），逐因子调用会
各自重复加载 400 天预热面板，量级上不可行。

区间模式（START/END 跨多日且未指定因子清单）的三个关键路径：

1. 内置与自定义因子按「逐因子整段向量化」计算：每个数据源全区间只读
   一次（内置因子间共享 data_cache），而不是逐日重复读取滚动预热窗。
2. 落库走 _BulkSaver 跨因子缓冲：factor_values 按交易日分区，分区读改写
   的代价随分区行数线性增长（百万行级分区单次读改写约 0.2s，全区间
   664 个分区 ≈ 2 分钟）；逐因子落库时 N 个因子就是 N 遍全分区读改写。
   缓冲多个因子后一次 flush，读改写次数降到每缓冲组一遍。
3. alpha191 批量按「已有覆盖」跳过：189 个因子的全区间重算本身是
   十小时级计算；显式点名（DATA_JOB_PARAM_FACTOR_IDS）的因子不跳过。

单日模式仍按日截面走 calculate_all_factors，行为不变。

Usage:
    python app/utils/factor_compute.py

环境变量（由 ScriptRunner 注入）:
    DATA_JOB_TRADE_DATE          单日模式：只算这个交易日
    DATA_JOB_START_DATE/_END_DATE 区间模式：计算整个区间（推荐回填用）
    DATA_JOB_PARAM_FACTOR_IDS    逗号分隔的因子列表；缺省算全部因子
    DATA_JOB_PARAM_TS_CODES      逗号分隔的股票列表；缺省全市场
    DATA_JOB_FLUSH_ROWS          批量落库缓冲行数阈值（默认 3000 万；
                                 调小可更早落盘，测试用）
"""
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd
from loguru import logger

from app.services.alpha191_factor_service import ALPHA191_FACTORS, computable_factors
from app.services.data_reader import ParquetDataReader
from app.services.factor_engine import FactorEngine

_DEFAULT_FLUSH_ROWS = 30_000_000


def _split_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


class _BulkSaver:
    """批量回填的跨因子缓冲写入器。

    save_values 按交易日分区做读-改-写：逐因子落库时，每个因子都要把
    全部涉及分区各重写一遍（分区含 189 个 alpha 时约百万行/日，全区间
    单因子就要分钟级）。这里把多个因子的长表压成 category/datetime
    紧凑 dtype 攒在内存里，攒够 FLUSH_ROWS 行后按「同因子整体替换」
    一次落盘，每个分区的读改写次数从每因子一次降到每缓冲组一次。

    flush 失败时抛 RuntimeError 并记录 last_failed_ids / last_failed_rows，
    缓冲随即丢弃（调用方把对应因子记为 error），不重放。
    """

    def __init__(self, engine, flush_rows: int = None):
        self._engine = engine
        self._flush_rows = flush_rows or int(
            os.getenv("DATA_JOB_FLUSH_ROWS", _DEFAULT_FLUSH_ROWS)
        )
        self._parts: list = []
        self._buffered_ids: list = []
        self._rows = 0
        self.written = 0
        self.last_failed_ids: list = []
        self.last_failed_rows = 0

    def add(self, factor_id: str, frame: pd.DataFrame) -> None:
        if frame is None or frame.empty:
            return
        compact = frame.copy()
        # 紧凑 dtype：3.6M 行的因子长表从 ~700MB 压到 ~100MB，
        # 3000 万行缓冲约 1GB 内存
        compact["ts_code"] = compact["ts_code"].astype("category")
        compact["trade_date"] = pd.to_datetime(compact["trade_date"], format="mixed")
        compact["factor_id"] = compact["factor_id"].astype("category")
        self._parts.append(compact)
        self._buffered_ids.append(factor_id)
        self._rows += len(compact)
        if self._rows >= self._flush_rows:
            self.flush()

    def flush(self) -> None:
        if not self._parts:
            return
        frame = pd.concat(self._parts, ignore_index=True)
        for column in ("ts_code", "factor_id"):
            frame[column] = frame[column].astype(str)
        replace_ids = sorted(frame["factor_id"].unique())
        failed_ids = list(self._buffered_ids)
        failed_rows = self._rows
        self._parts, self._buffered_ids, self._rows = [], [], 0
        logger.info(
            f"批量落盘 {len(failed_ids)} 个因子 / {len(frame)} 行 "
            f"({failed_ids[0]}..{failed_ids[-1]})"
        )
        ok = self._engine.save_factor_values(frame, replace_factor_ids=replace_ids)
        if not ok:
            self.last_failed_ids = failed_ids
            self.last_failed_rows = failed_rows
            raise RuntimeError(f"批量落盘失败: {len(failed_ids)} 个因子")
        self.written += failed_rows
        self.last_failed_ids, self.last_failed_rows = [], 0


def _scan_factor_coverage(engine, start_date: str, end_date: str):
    """扫描 factor_values 分区，统计各因子在区间内的覆盖天数与首末日。

    只读每个分区的 factor_id 一列（字典编码，单分区约 0.1s）。返回
    ({factor_id: {"covered": n, "first": d, "last": d}}, {date: 当日因子数})，
    分区按日期升序遍历，first/last 天然正确。
    """
    store = engine.factor_repo.store
    partitions = store.list_partitions(engine.factor_repo.TABLE_VALUES)
    lo = pd.to_datetime(start_date)
    hi = pd.to_datetime(end_date)
    factor_cov: dict = {}
    date_counts: dict = {}
    for partition in partitions:
        ts = pd.to_datetime(partition, errors="coerce")
        if pd.isna(ts) or ts < lo or ts > hi:
            continue
        path = (
            store.base_dir / engine.factor_repo.TABLE_VALUES
            / f"trade_date={partition}" / "data.parquet"
        )
        try:
            ids = pd.read_parquet(path, columns=["factor_id"])["factor_id"]
        except Exception:
            continue
        present = set(ids.astype(str))
        for factor_id in present:
            entry = factor_cov.setdefault(
                factor_id, {"covered": 0, "first": partition, "last": partition}
            )
            entry["covered"] += 1
            entry["last"] = partition
        date_counts[partition] = len(present)
    return factor_cov, date_counts


def _split_alpha_backfill(alpha_ids, factor_cov, date_counts):
    """把 alpha 清单分成（需要重算的, 已完成回填的）。

    跳过判据（以「当日过半 alpha 因子有数据」的日期为基准集 U）：
    - 覆盖 ≥ 95% × |U|：完整回填过；
    - 首次出现晚于区间起点（长窗口因子预热不足的自然形态）且从自己的
      首日往后覆盖 ≥ 98%：已达可达上限——行情历史没有更早数据，重算
      只会原样重写。显式点名的因子不走本函数，不跳过。
    """
    if not date_counts:
        return list(alpha_ids), {}
    threshold = max(2, len(alpha_ids) // 2)
    universe = sorted(d for d, n in date_counts.items() if n >= threshold)
    if not universe:
        return list(alpha_ids), {}
    universe_ts = [pd.to_datetime(d) for d in universe]
    total = len(universe)

    todo, skipped = [], {}
    for factor_id in alpha_ids:
        entry = factor_cov.get(factor_id)
        if entry is None:
            todo.append(factor_id)
            continue
        covered = entry["covered"]
        if covered >= 0.95 * total:
            skipped[factor_id] = f"skip: 已覆盖 {covered}/{total} 天"
            continue
        first_ts = pd.to_datetime(entry["first"])
        if first_ts > universe_ts[0]:
            expected = sum(1 for t in universe_ts if t >= first_ts)
            if expected and covered >= 0.98 * expected:
                skipped[factor_id] = (
                    f"skip: 预热上限形态，覆盖 {covered}/{expected} 天"
                    f"（自 {entry['first']} 起）"
                )
                continue
        todo.append(factor_id)
    return todo, skipped


def _run_alpha191_batch(engine, alpha_ids, start_date, end_date, ts_codes,
                        per_factor_stats, saver: _BulkSaver) -> int:
    """alpha191 宽面板批量：面板只加载一次，逐因子进缓冲，返回成功行数。"""
    from app.services.alpha191_factor_service import Alpha191FactorService

    written_before = saver.written
    service = Alpha191FactorService(engine.data_reader)

    def _on_result(factor_id, long_df):
        if long_df is None or long_df.empty:
            per_factor_stats[factor_id] = 0
            return
        try:
            saver.add(factor_id, long_df)
            per_factor_stats[factor_id] = len(long_df)
        except RuntimeError as exc:  # 缓冲组落盘失败：标记后继续算后续因子
            logger.error(f"保存因子 {factor_id} 所在缓冲组失败: {exc}")
            for fid in saver.last_failed_ids:
                per_factor_stats[fid] = "error: 批量落盘失败"

    service.calculate_many(
        alpha_ids, start_date, end_date, ts_codes=ts_codes,
        on_result=_on_result, collect_results=False,
    )
    try:
        saver.flush()
    except RuntimeError as exc:
        logger.error(f"alpha191 收尾落盘失败: {exc}")
        for fid in saver.last_failed_ids:
            per_factor_stats[fid] = "error: 批量落盘失败"
    return saver.written - written_before


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

    # 批量回填统一走缓冲落库：区间模式跨多日，单日模式只有一两个
    # 分区、缓冲无收益，直接落库即可
    saver = _BulkSaver(engine)

    total_saved = 0
    per_factor_stats = {}
    failed = 0
    attempted = 0

    if alpha_ids:
        if factor_ids is None and ts_codes is None and start_date != end_date:
            # 区间全市场回填：先扫已有覆盖，跳过已完成回填的 alpha——
            # 189 个因子的全区间重算是十小时级计算，覆盖已达标时纯属重写。
            # 单日/点名/部分股票清单不做跳过（扫描本身要遍历全部分区）。
            factor_cov, date_counts = _scan_factor_coverage(
                engine, start_date, end_date
            )
            alpha_todo, alpha_skipped = _split_alpha_backfill(
                alpha_ids, factor_cov, date_counts
            )
            if alpha_skipped:
                logger.info(
                    f"alpha191: {len(alpha_skipped)}/{len(alpha_ids)} 个因子"
                    f"在 {start_date}~{end_date} 已有覆盖，跳过重算"
                )
            per_factor_stats.update(alpha_skipped)
            alpha_ids = alpha_todo
        if alpha_ids:
            # alpha191：区间一次算完（宽面板共享一次加载）
            attempted += 1
            try:
                total_saved += _run_alpha191_batch(
                    engine, alpha_ids, start_date, end_date, ts_codes,
                    per_factor_stats, saver,
                )
            except Exception as e:
                failed += 1
                logger.error(f"alpha191 批量计算失败: {e}")

    if other_ids:
        # 指定普通因子：区间一次算完（内置因子支持任意区间）；
        # 多个内置因子共享同一份数据读取
        other_cache: dict = {}
        saved_before = saver.written
        for factor_id in other_ids:
            attempted += 1
            try:
                result = engine.calculate_factor(
                    factor_id, ts_codes, start_date, end_date,
                    data_cache=other_cache,
                )
                if result.empty:
                    per_factor_stats[factor_id] = 0
                    continue
                saver.add(factor_id, result)
                per_factor_stats[factor_id] = len(result)
            except RuntimeError as e:
                failed += 1
                logger.error(f"批量落盘失败（{factor_id} 所在组）: {e}")
                for fid in saver.last_failed_ids:
                    per_factor_stats[fid] = "error: 批量落盘失败"
            except Exception as e:
                failed += 1
                logger.error(f"计算因子 {factor_id} 失败: {e}")
                per_factor_stats[factor_id] = f"error: {e}"
        try:
            saver.flush()
        except RuntimeError as e:
            failed += 1
            logger.error(f"批量落盘失败: {e}")
            for fid in saver.last_failed_ids:
                per_factor_stats[fid] = "error: 批量落盘失败"
        total_saved += saver.written - saved_before

    if not factor_ids:
        if start_date == end_date:
            # 单日模式：按日截面一次算完全部因子（共享当日数据缓存）
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
        else:
            # 区间模式：逐因子整段向量化，不逐日循环。逐日路径每天要为
            # 内置 5 个数据源 + 8 个自定义因子重复读取 252 日预热窗
            # （约 13 次窗口读/天），666 个交易日累计 8000+ 次读取；股票
            # 分区过期时每次读取还回退日期分区全量扫描——实测单次窗口
            # 读 25s+，整段全量读仅 4.5s，逐日循环量级为数小时，整段
            # 逐因子为分钟级。滚动窗口类公式的数值与逐日路径一致：
            # 同样的预热窗 + 事后按区间过滤，只是向量化一次算完。
            range_ids = [
                fid for fid in engine.builtin_factors
                if fid not in ALPHA191_FACTORS
            ]
            custom_ids = list(engine.factor_definitions.keys())
            shared_cache: dict = {}
            saved_before = saver.written
            for factor_id in range_ids + custom_ids:
                attempted += 1
                try:
                    result = engine.calculate_factor(
                        factor_id, ts_codes, start_date, end_date,
                        data_cache=shared_cache,
                    )
                except Exception as e:
                    failed += 1
                    logger.error(f"计算因子 {factor_id} 失败: {e}")
                    per_factor_stats[factor_id] = f"error: {e}"
                    continue
                if result.empty:
                    per_factor_stats[factor_id] = 0
                    continue
                try:
                    saver.add(factor_id, result)
                except RuntimeError as e:
                    failed += 1
                    logger.error(f"批量落盘失败（{factor_id} 所在组）: {e}")
                    for fid in saver.last_failed_ids:
                        per_factor_stats[fid] = "error: 批量落盘失败"
                    continue
                per_factor_stats[factor_id] = len(result)
            try:
                saver.flush()
            except RuntimeError as e:
                failed += 1
                logger.error(f"批量落盘失败: {e}")
                for fid in saver.last_failed_ids:
                    per_factor_stats[fid] = "error: 批量落盘失败"
            total_saved += saver.written - saved_before

    print(f"因子计算完成: {start_date} ~ {end_date}, 共写入 {total_saved} 条")
    print(per_factor_stats)

    # 零产出或全部失败必须以非零码退出：否则流水线把作业记成 success，
    # 缺失的因子值要等到回测覆盖率校验才暴露。全部因子因已有覆盖被跳过
    # 时 attempted 为 0，不算失败。
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
