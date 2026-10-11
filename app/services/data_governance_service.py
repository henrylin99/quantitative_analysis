"""数据治理服务：存储看板 + factor_values 分区审计与保留窗口清理。

背景：data/ml_factor_state/factor_values 是每日一分区的长表
（trade_date=YYYY-MM-DD/data.parquet，单日 ~217 因子 × ~5500 股 ≈ 120 万行，
~15MB），随交易日线性增长且从未清理，2026-10 已达 ~9GB。

清理的真实杠杆是**按日期保留窗口**：因子研究链（体检/IC/分位回测）
默认回看两年，超出保留窗口的分区可安全删除。按因子删行需要重写全部
历史分区，不作为日常清理原语提供。

安全纪律：
- 默认 dry-run：confirm=False 只返回将删清单与可回收空间，不动文件；
- 执行删除必须显式 confirm=True，且逐分区校验名称格式；
- 每次执行落 op log（data/ml_factor_state/cleanup_log.json，保留 50 条）；
- 永不删除保留窗口内的分区与最新分区。
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

_PARTITION_RE = re.compile(r"^trade_date=(\d{4}-\d{2}-\d{2})$")
_MAX_OP_LOG = 50


class DataGovernanceService:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = Path(data_dir)

    # ------------------------------------------------------------------
    # 存储看板
    # ------------------------------------------------------------------
    @staticmethod
    def _dir_size(path: Path) -> tuple[int, int]:
        """返回 (字节数, 文件数)；不存在返回 (0, 0)。"""
        total, files = 0, 0
        for root, _dirs, names in os.walk(path):
            for name in names:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                    files += 1
                except OSError:
                    continue
        return total, files

    def get_storage_overview(self) -> Dict[str, Any]:
        """data/ 各子目录体积排行 + factor_values 分区统计与增长估算。"""
        dirs: List[Dict[str, Any]] = []
        for entry in sorted(self.data_dir.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            size, files = self._dir_size(entry)
            dirs.append({"name": entry.name, "size_bytes": size, "files": files})
        dirs.sort(key=lambda d: d["size_bytes"], reverse=True)

        values_dir = self.data_dir / "ml_factor_state" / "factor_values"
        partitions = self._list_partitions(values_dir)
        partition_info: Dict[str, Any] = {"partitions": len(partitions)}
        if partitions:
            dates = [d for d, _ in partitions]
            total_size = sum(sz for _, sz in partitions)
            span_days = max((datetime.strptime(max(dates), "%Y-%m-%d") - datetime.strptime(min(dates), "%Y-%m-%d")).days, 1)
            partition_info.update(
                {
                    "oldest": min(dates),
                    "latest": max(dates),
                    "size_bytes": total_size,
                    "avg_partition_bytes": total_size // len(partitions),
                    "growth_per_month_bytes": int(total_size / span_days * 30),
                }
            )
        return {
            "data_dir": str(self.data_dir),
            "total_bytes": sum(d["size_bytes"] for d in dirs),
            "dirs": dirs,
            "factor_values": partition_info,
        }

    # ------------------------------------------------------------------
    # factor_values 审计
    # ------------------------------------------------------------------
    @staticmethod
    def _list_partitions(values_dir: Path) -> List[tuple[str, int]]:
        """[(trade_date, size_bytes)]，按日期升序；目录名不符合分区格式则忽略。"""
        out: List[tuple[str, int]] = []
        if not values_dir.is_dir():
            return out
        for entry in values_dir.iterdir():
            m = _PARTITION_RE.match(entry.name)
            if not m or not entry.is_dir():
                continue
            size, _files = DataGovernanceService._dir_size(entry)
            out.append((m.group(1), size))
        out.sort(key=lambda x: x[0])
        return out

    def audit_factor_values(self, min_coverage: int = 2000) -> Dict[str, Any]:
        """分区清单概览 + 最新分区的逐因子行数（识别退化/低覆盖因子）。"""
        values_dir = self.data_dir / "ml_factor_state" / "factor_values"
        partitions = self._list_partitions(values_dir)
        if not partitions:
            return {"partitions_total": 0, "latest_partition": None, "factor_rows": [], "degenerate": []}

        latest_date, latest_size = partitions[-1]
        factor_rows: List[Dict[str, Any]] = []
        latest_file = values_dir / f"trade_date={latest_date}" / "data.parquet"
        try:
            import pandas as pd

            counts = pd.read_parquet(latest_file, columns=["factor_id"])["factor_id"].value_counts()
            factor_rows = [
                {"factor_id": fid, "rows": int(n)} for fid, n in counts.items()
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"读取最新分区失败 {latest_file}: {exc}")

        return {
            "partitions_total": len(partitions),
            "oldest": partitions[0][0],
            "latest": latest_date,
            "latest_size_bytes": latest_size,
            "factor_rows": factor_rows,
            "degenerate": [r for r in factor_rows if r["rows"] < min_coverage],
        }

    # ------------------------------------------------------------------
    # 保留窗口清理（dry-run 默认）
    # ------------------------------------------------------------------
    def cleanup_factor_values_partitions(self, retention_days: int = 800, confirm: bool = False) -> Dict[str, Any]:
        """删除早于保留窗口的 factor_values 分区。

        retention_days 以最新分区日期为锚（非今天）：数据链路停更时
        以"最新 - N 天"为准，避免停更期间误删全部历史。
        """
        values_dir = self.data_dir / "ml_factor_state" / "factor_values"
        partitions = self._list_partitions(values_dir)
        if not partitions:
            return {"success": False, "message": "factor_values 无分区可清理"}

        latest_date = partitions[-1][0]
        cutoff = (
            datetime.strptime(latest_date, "%Y-%m-%d") - timedelta(days=retention_days)
        ).strftime("%Y-%m-%d")

        candidates: List[Dict[str, Any]] = []
        for date, size in partitions:
            if date < cutoff:
                candidates.append({"partition": f"trade_date={date}", "trade_date": date, "size_bytes": size})

        result: Dict[str, Any] = {
            "success": True,
            "retention_days": retention_days,
            "cutoff": cutoff,
            "latest": latest_date,
            "dry_run": not confirm,
            "candidates": candidates,
            "candidate_count": len(candidates),
            "reclaim_bytes": sum(c["size_bytes"] for c in candidates),
            "remaining_partitions": len(partitions) - len(candidates),
        }
        if not confirm:
            return result
        if not candidates:
            return result

        deleted: List[str] = []
        for cand in candidates:
            path = values_dir / cand["partition"]
            # 双重校验：只删格式合法且日期确实早于 cutoff 的分区目录
            if not _PARTITION_RE.match(cand["partition"]) or cand["trade_date"] >= cutoff:
                logger.warning(f"跳过非法清理目标: {cand}")
                continue
            shutil.rmtree(path, ignore_errors=False)
            deleted.append(cand["partition"])

        result["deleted"] = deleted
        result["deleted_count"] = len(deleted)
        result["executed_at"] = datetime.now().isoformat(timespec="seconds")
        self._append_op_log(result)
        logger.info(f"factor_values 清理完成：删除 {len(deleted)} 个分区，回收 {result['reclaim_bytes']} 字节")
        return result

    def cleanup_minute_partitions(self, retention_days: int = 185, timeframe: str = "5min", confirm: bool = False) -> Dict[str, Any]:
        """删除早于保留窗口的 stock_minute 日分区（滚动窗口，默认约 6 个月）。

        与 factor_values 清理同口径：以该周期最新分区日期为锚计算 cutoff，
        默认 dry-run，逐分区校验名称格式后才 rmtree。
        """
        base = self.data_dir / "stock_minute" / timeframe
        if not base.is_dir():
            return {"success": False, "message": f"stock_minute/{timeframe} 不存在"}

        candidates: List[Dict[str, Any]] = []
        latest_date: Optional[str] = None
        for day_dir in sorted(base.glob("year=*/*=*/*=*")):
            if not day_dir.is_dir():
                continue
            date_text = f"{day_dir.parent.parent.name[5:]}-{day_dir.parent.name[6:]}-{day_dir.name[4:]}"
            try:
                datetime.strptime(date_text, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"跳过非法分钟分区目录: {day_dir}")
                continue
            latest_date = max(latest_date, date_text) if latest_date else date_text
            size, _file_count = self._dir_size(day_dir)
            candidates.append({"partition": str(day_dir.relative_to(base)), "trade_date": date_text, "size_bytes": size})

        if not candidates:
            return {"success": False, "message": f"stock_minute/{timeframe} 无分区"}

        cutoff = (
            datetime.strptime(latest_date, "%Y-%m-%d") - timedelta(days=retention_days)
        ).strftime("%Y-%m-%d")
        stale = [c for c in candidates if c["trade_date"] < cutoff]

        result: Dict[str, Any] = {
            "success": True,
            "timeframe": timeframe,
            "retention_days": retention_days,
            "cutoff": cutoff,
            "latest": latest_date,
            "dry_run": not confirm,
            "candidates": stale,
            "candidate_count": len(stale),
            "reclaim_bytes": sum(c["size_bytes"] for c in stale),
            "remaining_partitions": len(candidates) - len(stale),
        }
        if not confirm or not stale:
            return result

        deleted: List[str] = []
        for cand in stale:
            path = base / cand["partition"]
            if cand["trade_date"] >= cutoff:
                logger.warning(f"跳过非法清理目标: {cand}")
                continue
            shutil.rmtree(path, ignore_errors=False)
            deleted.append(cand["partition"])

        result["deleted"] = deleted
        result["deleted_count"] = len(deleted)
        result["executed_at"] = datetime.now().isoformat(timespec="seconds")
        self._append_op_log(result)
        logger.info(f"分钟分区清理完成（{timeframe}）：删除 {len(deleted)} 天，回收 {result['reclaim_bytes']} 字节")
        return result

    @property
    def _op_log_path(self) -> Path:
        return self.data_dir / "ml_factor_state" / "cleanup_log.json"

    def _append_op_log(self, entry: Dict[str, Any]) -> None:
        try:
            logs: List[Dict[str, Any]] = []
            if self._op_log_path.exists():
                try:
                    logs = json.loads(self._op_log_path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    logs = []
            logs.append({
                "executed_at": entry.get("executed_at"),
                "retention_days": entry.get("retention_days"),
                "cutoff": entry.get("cutoff"),
                "deleted_count": entry.get("deleted_count"),
                "reclaim_bytes": entry.get("reclaim_bytes"),
            })
            self._op_log_path.write_text(json.dumps(logs[-_MAX_OP_LOG:], ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"写清理操作日志失败: {exc}")

    def list_cleanup_log(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            logs = json.loads(self._op_log_path.read_text(encoding="utf-8"))
            return logs[-limit:] if isinstance(logs, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []


_GOV: Optional[DataGovernanceService] = None


def get_data_governance_service() -> DataGovernanceService:
    global _GOV
    if _GOV is None:
        _GOV = DataGovernanceService()
    return _GOV
