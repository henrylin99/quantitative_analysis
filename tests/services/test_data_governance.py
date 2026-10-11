"""数据治理（批次 2.3）：存储看板、factor_values 审计、保留窗口清理。"""

import json

import pandas as pd
import pytest

from app.services.data_governance_service import DataGovernanceService

pytestmark = pytest.mark.module_data_jobs


@pytest.fixture()
def gov(tmp_path):
    return DataGovernanceService(data_dir=str(tmp_path))


def _write_partitions(tmp_path, dates, factors=("momentum_20", "alpha_019"), stocks=3):
    values_dir = tmp_path / "ml_factor_state" / "factor_values"
    for date in dates:
        pdir = values_dir / f"trade_date={date}"
        pdir.mkdir(parents=True, exist_ok=True)
        rows = []
        for factor in factors:
            for i in range(stocks):
                rows.append(
                    {
                        "ts_code": f"00000{i}.SZ",
                        "trade_date": date,
                        "factor_id": factor,
                        "factor_value": 1.0,
                        "percentile_rank": 50.0,
                        "z_score": 0.0,
                    }
                )
        pd.DataFrame(rows).to_parquet(pdir / "data.parquet", index=False)
        # 造一点体积便于断言
        (pdir / "data.parquet").write_bytes((pdir / "data.parquet").read_bytes() * 1)


def test_storage_overview_lists_dirs_and_factor_values(gov, tmp_path):
    _write_partitions(tmp_path, ["2026-09-29", "2026-09-30"])

    overview = gov.get_storage_overview()
    names = {d["name"] for d in overview["dirs"]}
    assert "ml_factor_state" in names
    assert overview["factor_values"]["partitions"] == 2
    assert overview["factor_values"]["latest"] == "2026-09-30"
    assert overview["factor_values"]["oldest"] == "2026-09-29"
    assert overview["factor_values"]["avg_partition_bytes"] > 0


def test_storage_overview_empty_state(gov):
    overview = gov.get_storage_overview()
    assert overview["dirs"] == []
    assert overview["factor_values"] == {"partitions": 0}


def test_audit_flags_degenerate_factors(gov, tmp_path):
    # alpha_138 只覆盖 1 只股票（真实退化因子的镜像），其余 3 只
    values_dir = tmp_path / "ml_factor_state" / "factor_values" / "trade_date=2026-09-30"
    values_dir.mkdir(parents=True)
    date = "2026-09-30"
    rows = []
    for i in range(3):
        rows.append({"ts_code": f"00000{i}.SZ", "trade_date": date,
                     "factor_id": "momentum_20", "factor_value": 1.0})
    rows.append({"ts_code": "000000.SZ", "trade_date": date,
                 "factor_id": "alpha_138", "factor_value": 2.0})
    pd.DataFrame(rows).to_parquet(values_dir / "data.parquet", index=False)

    audit = gov.audit_factor_values(min_coverage=2)
    rows_by_factor = {r["factor_id"]: r["rows"] for r in audit["factor_rows"]}
    assert rows_by_factor["momentum_20"] == 3
    assert rows_by_factor["alpha_138"] == 1
    assert {r["factor_id"] for r in audit["degenerate"]} == {"alpha_138"}


def test_cleanup_dry_run_lists_candidates_without_deleting(gov, tmp_path):
    _write_partitions(tmp_path, ["2024-01-02", "2026-01-02", "2026-09-30"])

    result = gov.cleanup_factor_values_partitions(retention_days=300, confirm=False)
    assert result["dry_run"] is True
    assert result["candidate_count"] == 1
    assert result["candidates"][0]["partition"] == "trade_date=2024-01-02"
    assert result["remaining_partitions"] == 2
    # dry-run 不动文件
    assert (tmp_path / "ml_factor_state" / "factor_values" / "trade_date=2024-01-02").exists()


def test_cleanup_execute_deletes_only_candidates_and_logs(gov, tmp_path):
    _write_partitions(tmp_path, ["2024-01-02", "2026-01-02", "2026-09-30"])

    result = gov.cleanup_factor_values_partitions(retention_days=300, confirm=True)
    assert result["dry_run"] is False
    assert result["deleted_count"] == 1
    assert not (tmp_path / "ml_factor_state" / "factor_values" / "trade_date=2024-01-02").exists()
    assert (tmp_path / "ml_factor_state" / "factor_values" / "trade_date=2026-01-02").exists()
    assert (tmp_path / "ml_factor_state" / "factor_values" / "trade_date=2026-09-30").exists()

    logs = gov.list_cleanup_log()
    assert logs and logs[-1]["deleted_count"] == 1


def test_cleanup_anchor_is_latest_partition_not_today(gov, tmp_path):
    # 数据链路停更时以"最新分区 - N 天"为锚，避免停更期间误删全部历史
    _write_partitions(tmp_path, ["2025-01-02"])

    result = gov.cleanup_factor_values_partitions(retention_days=300, confirm=False)
    assert result["cutoff"] == "2024-03-08"
    assert result["candidate_count"] == 0


def test_cleanup_no_partitions_returns_failure(gov):
    result = gov.cleanup_factor_values_partitions(retention_days=300)
    assert result["success"] is False
