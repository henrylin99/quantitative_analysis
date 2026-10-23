"""factor_values staging 落库路径（区间批量回填）的合同测试。

- flush 只写 staging 片段，线上分区在 commit 前不受影响
- commit 合并语义与 save_values 一致：同因子整体替换、未入参因子保留
- 旧分区因子全部被替换时无须整读旧分区（全量重建形态）
- discard 清理残留片段；_BulkSaver staged 模式收尾传替换因子并集
"""
import pandas as pd
import pytest

from app.services.parquet_state_store import FactorRepository, ParquetStateStore
from app.utils.factor_compute import _BulkSaver

pytestmark = pytest.mark.module_factor_engine


def _make_repo(tmp_path):
    return FactorRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))


def _values_frame(trade_date, factor_id="f1", values=(1.0, 2.0), prefix="00000"):
    return pd.DataFrame(
        [
            {"ts_code": f"{prefix}{i}.SZ", "trade_date": trade_date,
             "factor_id": factor_id, "factor_value": value}
            for i, value in enumerate(values, start=1)
        ]
    )


def test_commit_replaces_same_factor_and_keeps_others(tmp_path):
    repo = _make_repo(tmp_path)
    repo.save_values(_values_frame("2024-06-03", factor_id="f1", values=(1.0,)))
    repo.save_values(_values_frame("2024-06-03", factor_id="f2", values=(7.0,)))

    # 线上分区不应被 stage 触碰
    repo.stage_values(_values_frame("2024-06-03", factor_id="f1", values=(9.0,)))
    before = repo.get_values(trade_date="2024-06-03")
    assert set(before["factor_value"]) == {1.0, 7.0}, "stage 后线上分区必须原样"

    committed = repo.commit_staged_values(replace_factor_ids=["f1"])
    assert committed == 1
    after = repo.get_values(trade_date="2024-06-03")
    f1 = after[after["factor_id"] == "f1"]
    f2 = after[after["factor_id"] == "f2"]
    assert set(f1["factor_value"]) == {9.0}, "f1 被整体替换"
    assert set(f2["factor_value"]) == {7.0}, "未入参因子 f2 保留"
    assert len(after) == 2

    # staging 目录清空
    assert not (repo.store.base_dir / repo.TABLE_STAGING).exists()


def test_commit_full_replacement_rebuilds_partition(tmp_path):
    repo = _make_repo(tmp_path)
    repo.save_values(_values_frame("2024-06-03", factor_id="f1", values=(1.0,)))
    repo.save_values(_values_frame("2024-06-03", factor_id="f2", values=(7.0,)))

    # 全量重建：入参覆盖分区内全部因子 → 旧值整体让位
    repo.stage_values(_values_frame("2024-06-03", factor_id="f1", values=(11.0,),
                                    prefix="60000"))
    repo.stage_values(_values_frame("2024-06-03", factor_id="f2", values=(12.0,),
                                    prefix="60000"))
    repo.commit_staged_values(replace_factor_ids=["f1", "f2"])

    after = repo.get_values(trade_date="2024-06-03")
    assert set(after["factor_value"]) == {11.0, 12.0}, "旧因子值全部让位给重建结果"


def test_multiple_flushes_accumulate_in_staging(tmp_path):
    repo = _make_repo(tmp_path)
    repo.stage_values(_values_frame("2024-06-03", factor_id="f1", values=(1.0,)))
    repo.stage_values(_values_frame("2024-06-03", factor_id="f2", values=(2.0,)))
    repo.stage_values(_values_frame("2024-06-04", factor_id="f1", values=(3.0,)))

    committed = repo.commit_staged_values(replace_factor_ids=["f1", "f2"])
    assert committed == 3

    day3 = repo.get_values(trade_date="2024-06-03")
    day4 = repo.get_values(trade_date="2024-06-04")
    assert set(day3["factor_id"]) == {"f1", "f2"}
    assert set(day4["factor_id"]) == {"f1"}
    # 同一缓冲组重复键的防御性去重：keep last
    repo.stage_values(_values_frame("2024-06-03", factor_id="f1", values=(5.0,)))
    repo.commit_staged_values(replace_factor_ids=["f1"])
    day3 = repo.get_values(trade_date="2024-06-03")
    f1 = day3[day3["factor_id"] == "f1"]
    assert set(f1["factor_value"]) == {5.0}


def test_commit_without_replacement_dedupes(tmp_path):
    repo = _make_repo(tmp_path)
    repo.save_values(_values_frame("2024-06-03", factor_id="f1", values=(1.0,)))

    # 不传 replace_factor_ids：走常规去重合并，同键保留新值
    repo.stage_values(_values_frame("2024-06-03", factor_id="f1", values=(4.0,)))
    repo.commit_staged_values()

    day = repo.get_values(trade_date="2024-06-03")
    assert len(day) == 1
    assert day["factor_value"].iloc[0] == 4.0


def test_discard_staged_keeps_live_untouched(tmp_path):
    repo = _make_repo(tmp_path)
    repo.save_values(_values_frame("2024-06-03", values=(1.0,)))
    repo.stage_values(_values_frame("2024-06-03", values=(2.0,)))
    repo.discard_staged_values()

    assert repo.commit_staged_values() == 0, "丢弃后 commit 应为空操作"
    day = repo.get_values(trade_date="2024-06-03")
    assert set(day["factor_value"]) == {1.0}, "线上分区不受残留片段影响"


def test_stage_drops_invalid_trade_dates(tmp_path):
    repo = _make_repo(tmp_path)
    frame = _values_frame("2024-06-03", values=(1.0, 2.0))
    frame.loc[frame.index[1], "trade_date"] = None

    written = repo.stage_values(frame)

    assert written == 1
    assert repo.commit_staged_values(replace_factor_ids=["f1"]) == 1


class _FakeEngine:
    def __init__(self):
        self.staged_frames = []
        self.commit_calls = []

    def stage_factor_values(self, df):
        self.staged_frames.append(df)
        return len(df)

    def commit_staged_factor_values(self, replace_factor_ids=None):
        self.commit_calls.append(replace_factor_ids)
        return sum(len(f) for f in self.staged_frames)


def test_bulk_saver_staged_mode_commit_union(tmp_path):
    engine = _FakeEngine()
    saver = _BulkSaver(engine, flush_rows=5, staged=True)

    saver.add("alpha_001", _values_frame("2024-06-03", factor_id="alpha_001",
                                         values=(1.0, 2.0, 3.0)))
    assert engine.staged_frames == [], "未达阈值不 flush"
    saver.add("alpha_002", _values_frame("2024-06-03", factor_id="alpha_002",
                                         values=(4.0, 5.0, 6.0)))
    assert len(engine.staged_frames) == 1, "超阈值自动 flush 到 staging"
    assert saver.written == 6

    committed = saver.commit()
    assert committed == 6
    assert engine.commit_calls == [["alpha_001", "alpha_002"]], (
        "commit 必须传全部 staged 因子的并集（同因子整体替换语义）"
    )
    assert saver.commit() == 0, "重复 commit 为空操作"


def test_bulk_saver_staged_failure_marks_buffer_group():
    class _FailingEngine(_FakeEngine):
        def stage_factor_values(self, df):
            raise OSError("disk full")

    engine = _FailingEngine()
    saver = _BulkSaver(engine, flush_rows=2, staged=True)
    saver.add("alpha_001", _values_frame("2024-06-03", factor_id="alpha_001",
                                         values=(1.0,)))
    with pytest.raises(RuntimeError):
        saver.add("alpha_002", _values_frame("2024-06-03", factor_id="alpha_002",
                                             values=(3.0, 4.0)))
    assert saver.last_failed_ids == ["alpha_001", "alpha_002"]
    assert saver.last_failed_rows == 3
