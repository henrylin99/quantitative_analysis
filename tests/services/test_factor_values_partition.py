"""factor_values 按交易日分区存储的回归测试。

- 写入按 trade_date 拆成独立分区文件，读取按条件裁剪分区
- 业务键覆盖语义与旧单文件存储一致
- 旧单文件 factor_values.parquet 首次访问时自动迁移到分区
"""
import pandas as pd
import pytest

from app.services.parquet_state_store import FactorRepository, ParquetStateStore

pytestmark = pytest.mark.module_factor_engine


def _make_repo(tmp_path):
    return FactorRepository(ParquetStateStore(base_dir=str(tmp_path / "state")))


def _values_frame(trade_date, factor_id="f1", values=(1.0, 2.0)):
    return pd.DataFrame(
        [
            {"ts_code": f"00000{i}.SZ", "trade_date": trade_date,
             "factor_id": factor_id, "factor_value": value}
            for i, value in enumerate(values, start=1)
        ]
    )


def test_values_stored_in_daily_partitions(tmp_path):
    repo = _make_repo(tmp_path)
    store = repo.store
    repo.save_values(_values_frame("2024-06-03", values=(1.0, 2.0)))
    repo.save_values(_values_frame("2024-06-04", values=(3.0, 4.0)))

    assert store.list_partitions("factor_values") == [
        "2024-06-03", "2024-06-04",
    ]
    for partition in ("2024-06-03", "2024-06-04"):
        assert (store.base_dir / "factor_values" / f"trade_date={partition}" / "data.parquet").is_file()

    # 精确日期只返回该分区数据
    day = repo.get_values(trade_date="2024-06-04")
    assert set(day["factor_value"]) == {3.0, 4.0}

    # 无过滤条件返回全部分区
    everything = repo.get_values()
    assert set(everything["trade_date"].dt.strftime("%Y-%m-%d")) == {
        "2024-06-03", "2024-06-04",
    }


def test_range_query_and_business_key_overwrite(tmp_path):
    repo = _make_repo(tmp_path)
    repo.save_values(_values_frame("2024-06-03", values=(1.0,)))
    repo.save_values(_values_frame("2024-06-04", values=(2.0,)))
    repo.save_values(_values_frame("2024-06-05", values=(3.0,)))

    middle = repo.get_values(start_date="2024-06-04", end_date="2024-06-04")
    assert set(middle["factor_value"]) == {2.0}

    # 同一业务键重复写入 → 覆盖，不产生重复行
    repo.save_values(_values_frame("2024-06-04", values=(9.0,)))
    target = repo.get_values(trade_date="2024-06-04")
    assert len(target) == 1
    assert target["factor_value"].iloc[0] == 9.0


def test_other_partitions_intact_after_resave(tmp_path):
    repo = _make_repo(tmp_path)
    repo.save_values(_values_frame("2024-06-03", values=(1.0,)))
    repo.save_values(_values_frame("2024-06-04", values=(2.0, 2.2)))

    repo.save_values(_values_frame("2024-06-03", values=(7.0,)))

    other = repo.get_values(trade_date="2024-06-04")
    # 存储为 float32（既有设计），用容差比较
    assert {round(float(v), 3) for v in other["factor_value"]} == {2.0, 2.2}, (
        "重写 06-03 分区不能影响 06-04"
    )


def test_legacy_single_file_migrates_once(tmp_path, caplog):
    repo = _make_repo(tmp_path)
    store = repo.store
    legacy = _values_frame("2024-06-03", values=(5.0,))
    legacy["trade_date"] = "2024-06-03"
    store.write_frame("factor_values", legacy)

    frame = repo.get_values(trade_date="2024-06-03")
    assert set(frame["factor_value"]) == {5.0}, "迁移后的数据必须可读"
    legacy_path = store.path_for("factor_values")
    assert not legacy_path.is_file(), "旧单文件应被改名备份"
    assert legacy_path.with_name("factor_values.parquet.migrated").is_file()

    # 迁移后再写入新日期：分区与迁移数据共存
    repo.save_values(_values_frame("2024-06-04", values=(6.0,)))
    everything = repo.get_values()
    assert set(everything["factor_value"]) == {5.0, 6.0}


def test_invalid_trade_dates_dropped_with_warning(tmp_path):
    repo = _make_repo(tmp_path)
    frame = _values_frame("2024-06-03", values=(1.0, 2.0))
    frame.loc[frame.index[1], "trade_date"] = None

    written = repo.save_values(frame)

    assert written == 1
    assert len(repo.get_values()) == 1
