"""事件数据历史归档：龙虎榜/涨停池/跌停池/炸板池/连板天梯 → data/event_archive/。

背景：fuyao 事件类接口只有"当日/最近发布日"快照，无深历史（实测传历史
日期返回空），事件因子研究必须从"开始归档"做起——归档作业一旦上线不可
断，断档不可回补（roadmap 批次四纪律）。

布局：data/event_archive/{dataset}/date=YYYYMMDD/data.parquet
- dragon_tiger：龙虎榜个股明细（net_value/net_rate/buy_value/...）
- limit_up / limit_down / limit_break：三池当日快照
- ladder：连板天梯逐股行（board_num/seal_nextday/sign_level），接口自带
  近 30 个交易日窗口，首跑即回填 30 天——晋级率研究立即可用
- mood：市场情绪单行表（涨停/跌停/炸板家数、炸板率、最高连板），供预警
  情绪极值提醒与后续市场级 regime 消费

个股事件因子（limit_up_streak/break_board_flag/dragon_tiger_net_rate）由
compute_and_save 从归档落 factor_values，走既有标准化管线接受体检。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

_DATASETS = ("dragon_tiger", "limit_up", "limit_down", "limit_break", "ladder", "mood")

# 归档字段白名单：fuyao 返回字段平面化后只保留这些（concept_list 拼接为字符串）
_DRAGON_TIGER_FIELDS = (
    "thscode", "ticker", "name", "change", "net_value", "net_rate",
    "buy_value", "sell_value", "limit_reason", "range_days", "hot_rank",
    "hot_money_net_value",
)
_POOL_FIELDS = ("thscode", "ticker", "name", "last_price", "price_change_ratio_pct")
_LIMIT_UP_FIELDS = _POOL_FIELDS + ("limit_up_time", "limit_up_reason",
                                   "continue_day_cnt", "seal_money")
_LIMIT_DOWN_FIELDS = _POOL_FIELDS + ("first_limit_time", "last_limit_time")
_LIMIT_BREAK_FIELDS = _POOL_FIELDS + ("open_times",)
_LADDER_FIELDS = ("thscode", "ticker", "name", "board_num", "seal_nextday", "sign_level")


def _pick(item: Dict[str, Any], fields) -> Dict[str, Any]:
    row = {}
    for key in fields:
        value = item.get(key)
        if key == "thscode" and not value:
            continue
        row[key] = value
    return row


class EventArchiveService:
    """fuyao 事件数据逐日归档 + 读取 + 个股事件因子落库。"""

    def __init__(self, data_dir: Optional[str] = None, client=None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir
        self._client = client

    # ------------------------------------------------------------------
    # 存储
    # ------------------------------------------------------------------
    @property
    def client(self):
        if self._client is None:
            from app.utils.data_sources.fuyao_client import FuyaoClient

            self._client = FuyaoClient()
        return self._client

    def _partition_dir(self, dataset: str, date: str) -> str:
        return os.path.join(self.data_dir, "event_archive", dataset, f"date={date}")

    def _write_partition(self, dataset: str, date: str, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        path = os.path.join(self._partition_dir(dataset, date), "data.parquet")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        frame.to_parquet(path, index=False)
        return len(frame)

    def read_dataset(self, dataset: str, start: Optional[str] = None,
                     end: Optional[str] = None) -> pd.DataFrame:
        """读取归档数据集（start/end 为 YYYYMMDD，可空=全部）。"""
        base = os.path.join(self.data_dir, "event_archive", dataset)
        if not os.path.isdir(base):
            return pd.DataFrame()
        frames = []
        for name in sorted(os.listdir(base)):
            if not name.startswith("date="):
                continue
            date = name.split("=", 1)[1]
            if start and date < start:
                continue
            if end and date > end:
                continue
            path = os.path.join(base, name, "data.parquet")
            if not os.path.isfile(path):
                continue
            try:
                df = pd.read_parquet(path)
            except Exception as e:
                logger.warning(f"读取事件归档失败 {path}: {e}")
                continue
            if not df.empty:
                df = df.copy()
                df.insert(0, "date", date)
                frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def archived_dates(self, dataset: str) -> List[str]:
        base = os.path.join(self.data_dir, "event_archive", dataset)
        if not os.path.isdir(base):
            return []
        return sorted(
            name.split("=", 1)[1] for name in os.listdir(base)
            if name.startswith("date=")
            and os.path.isfile(os.path.join(base, name, "data.parquet"))
        )

    # ------------------------------------------------------------------
    # 归档
    # ------------------------------------------------------------------
    def archive_day(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """归档一次事件快照。ladder 自带 30 日窗口整体刷新。

        target_date 仅供测试注入；生产恒为"现在"（fuyao 无历史查询，
        传历史日期只会归档到空数据）。
        """
        stats: Dict[str, Any] = {"datasets": {}, "errors": []}
        for name, fn in (
            ("dragon_tiger", self._archive_dragon_tiger),
            ("ladder", self._archive_ladder),
            ("limit_up", self._archive_pools),
        ):
            try:
                stats["datasets"][name] = fn()
            except Exception as e:
                logger.warning(f"[event_archive] {name} 归档失败: {e}")
                stats["errors"].append(f"{name}: {e}")
        return stats

    def _archive_dragon_tiger(self) -> Dict[str, Any]:
        payload = self.client.dragon_tiger_list("all")
        items = payload.get("stock_items") or []
        trade_date = (payload.get("trade_date") or "").replace("-", "")
        if not items or not trade_date:
            return {"rows": 0, "skipped": "无上榜数据或无交易日期"}
        rows = []
        for item in items:
            row = _pick(item, _DRAGON_TIGER_FIELDS)
            if row.get("thscode"):
                rows.append({**row, "concept": self._join_concepts(item)})
        written = self._write_partition("dragon_tiger", trade_date, pd.DataFrame(rows))
        return {"rows": written, "date": trade_date}

    @staticmethod
    def _join_concepts(item: Dict[str, Any]) -> str:
        concepts = item.get("concept_list") or []
        return ",".join(c.get("name", "") for c in concepts if isinstance(c, dict))

    def _archive_ladder(self) -> Dict[str, Any]:
        payload = self.client.limit_up_ladder()
        days = payload.get("item") or []
        written_days = 0
        total_rows = 0
        for day in days:
            date = (day.get("date") or "").replace("-", "")
            if not date:
                continue
            rows = []
            for height, items in (day.get("boards") or {}).items():
                for item in items or []:
                    row = _pick(item, _LADDER_FIELDS)
                    if not row.get("thscode"):
                        continue
                    row["ladder_slot"] = height
                    rows.append(row)
            if not rows:
                continue
            total_rows += self._write_partition("ladder", date, pd.DataFrame(rows))
            written_days += 1
        return {"rows": total_rows, "days": written_days}

    def _archive_pools(self) -> Dict[str, Any]:
        """三池 + mood 归档（空池=非交易日或当日无数据，全部跳过不造假）。"""
        written = {}
        up = self._fetch_pool_all("limit_up", _LIMIT_UP_FIELDS,
                                  lambda p, size: self.client.limit_up_pool(page=p, size=size))
        down = self._fetch_pool_all("limit_down", _LIMIT_DOWN_FIELDS,
                                    lambda p, size: self.client.limit_down_pool(page=p, size=size))
        brk = self._fetch_pool_all("limit_break", _LIMIT_BREAK_FIELDS,
                                   lambda p, size: self.client.limit_break_pool(page=p, size=size))
        # 涨停/炸板池都空 → 视为非交易日或源异常，不落 mood
        if not up and not brk:
            return {"rows": 0, "skipped": "涨停/炸板池均为空（非交易日或数据源空）"}

        today = datetime.now().strftime("%Y%m%d")
        for dataset, rows in (("limit_up", up), ("limit_down", down), ("limit_break", brk)):
            if rows:
                written[dataset] = self._write_partition(dataset, today, pd.DataFrame(rows))

        streaks = [int(r["continue_day_cnt"]) for r in up
                   if r.get("continue_day_cnt") is not None
                   and str(r.get("continue_day_cnt")).replace(".", "").isdigit()]
        mood = {
            "limit_up_count": len(up),
            "limit_down_count": len(down),
            "break_count": len(brk),
            "break_rate": (len(brk) / (len(up) + len(brk))) if (up or brk) else None,
            "max_streak": max(streaks) if streaks else 0,
        }
        written["mood"] = self._write_partition("mood", today, pd.DataFrame([mood]))
        return {"rows": sum(written.values()), "mood": mood, "date": today}

    def _fetch_pool_all(self, name: str, fields, fetch_page) -> List[Dict[str, Any]]:
        """翻页拉全池并平面化字段（fuyao 单页 size 上限按 100 分页）。"""
        rows: List[Dict[str, Any]] = []
        for page in (1, 2, 3):  # 涨停家数历史极值 <300，3 页足够
            payload = fetch_page(page, 100)
            items = payload.get("item") or []
            for item in items:
                row = _pick(item, fields)
                if row.get("thscode"):
                    rows.append(row)
            pagination = payload.get("pagination") or {}
            if page >= int(pagination.get("pages") or 1):
                break
        return rows

    # ------------------------------------------------------------------
    # 个股事件因子 → factor_values（走既有标准化管线）
    # ------------------------------------------------------------------
    EVENT_FACTOR_IDS = ("limit_up_streak", "break_board_flag", "dragon_tiger_net_rate")

    def compute_and_save(self, date: Optional[str] = None, engine=None,
                         reader=None) -> Dict[str, Any]:
        """从当日归档计算个股事件因子并落 factor_values。

        事件稀疏是因子语义的一部分：未上榜/未涨停股票按 0 填充
        （0 连板 / 未炸板 / 净买 0），截面标准化后可直接进 IC 分析。
        当日无涨停池归档（非交易日）时跳过。engine/reader 可注入（测试）。
        """
        date = date or datetime.now().strftime("%Y%m%d")
        up = self.read_dataset("limit_up", start=date, end=date)
        brk = self.read_dataset("limit_break", start=date, end=date)
        dragon = self.read_dataset("dragon_tiger", start=date, end=date)
        if up.empty:
            return {"skipped": f"{date} 无涨停池归档（非交易日或未归档）"}
        if dragon.empty:
            # 龙虎榜按榜单发布日分区（周末拉到的是上一交易日榜单）：
            # 取 target 前 4 个自然日内最新一期作"最近已知净买"
            dragon_all = self.read_dataset("dragon_tiger")
            if not dragon_all.empty:
                dragon_all = dragon_all[pd.to_datetime(dragon_all["date"], format="%Y%m%d")
                                        <= pd.to_datetime(date) + pd.Timedelta(days=0)]
                recent = dragon_all[pd.to_datetime(dragon_all["date"], format="%Y%m%d")
                                    >= pd.to_datetime(date) - pd.Timedelta(days=4)]
                if not recent.empty:
                    dragon = recent[recent["date"] == recent["date"].max()]

        streak = dict(zip(up["thscode"].astype(str),
                          pd.to_numeric(up.get("continue_day_cnt"), errors="coerce").fillna(1)))
        break_flag = set(brk["thscode"].astype(str)) if not brk.empty else set()
        net_rate = {}
        if not dragon.empty and "net_rate" in dragon.columns:
            net_rate = dict(zip(dragon["thscode"].astype(str),
                                pd.to_numeric(dragon["net_rate"], errors="coerce")))

        if reader is None:
            from app.services.data_reader import ParquetDataReader

            reader = ParquetDataReader()
        codes = reader.get_stock_basic()["ts_code"].dropna().astype(str).tolist()
        frame = pd.DataFrame({
            "ts_code": codes,
            "limit_up_streak": [float(streak.get(c, 0.0)) for c in codes],
            "break_board_flag": [1.0 if c in break_flag else 0.0 for c in codes],
            "dragon_tiger_net_rate": [float(net_rate.get(c, 0.0) or 0.0) for c in codes],
        })

        if engine is None:
            from app.services.factor_engine import FactorEngine

            engine = FactorEngine()
        long_rows = []
        for factor_id in self.EVENT_FACTOR_IDS:
            part = frame[["ts_code"]].copy()
            part["factor_id"] = factor_id
            part["trade_date"] = date
            part["factor_value"] = frame[factor_id]
            long_rows.append(part)
        result = engine._calculate_factor_stats(pd.concat(long_rows, ignore_index=True))
        ok = engine.save_factor_values(result, replace_factor_ids=list(self.EVENT_FACTOR_IDS))
        if not ok:
            return {"error": f"{date} 事件因子落库失败"}
        return {"date": date, "rows": len(result),
                "factors": list(self.EVENT_FACTOR_IDS),
                "limit_up": len(streak), "break": len(break_flag),
                "dragon_tiger": len(net_rate)}

    # ------------------------------------------------------------------
    # 事件研究
    # ------------------------------------------------------------------
    def promotion_stats(self, window: int = 30) -> Dict[str, Any]:
        """连板高度 → 次日晋级率（seal_nextday，来自天梯归档）。"""
        df = self.read_dataset("ladder")
        if df.empty or "board_num" not in df.columns or "seal_nextday" not in df.columns:
            return {"error": "天梯归档为空"}
        df = df.copy()
        df["board_num"] = pd.to_numeric(df["board_num"], errors="coerce")
        df["seal_nextday"] = df["seal_nextday"].astype(str).str.lower().isin(("true", "1", "yes"))
        df["date"] = pd.to_datetime(df["date"])
        cutoff = df["date"].max() - pd.Timedelta(days=window * 3)
        df = df[df["date"] >= cutoff]

        bucket = df["board_num"].clip(lower=2, upper=7)
        grouped = df.assign(bucket=bucket).groupby("bucket")
        stats = []
        for height, g in grouped:
            stats.append({
                "height": int(height),
                "n_obs": int(len(g)),
                "n_promoted": int(g["seal_nextday"].sum()),
                "promotion_rate": round(float(g["seal_nextday"].mean()), 4),
                "days": int(g["date"].nunique()),
            })
        overall_seal = df[df["board_num"] >= 2]["seal_nextday"].mean() if len(df) else None
        return {
            "window_days": window,
            "by_height": stats,
            "overall_promotion_rate": round(float(overall_seal), 4) if overall_seal is not None else None,
            "n_days": int(df["date"].nunique()),
        }

    def dragon_tiger_forward(self, horizon: int = 5) -> Dict[str, Any]:
        """龙虎榜上榜后 N 日相对沪深300 超额（净买分组）。

        上榜日 T 收盘入场 → T+N 收盘出场（上榜名单 T 日盘后才可知，
        收盘入场是乐观上界，报告口径注明）。
        """
        from app.services.data_reader import ParquetDataReader

        reader = ParquetDataReader()
        dragon = self.read_dataset("dragon_tiger")
        if dragon.empty:
            return {"error": "龙虎榜归档为空"}
        dragon = dragon.copy()
        dragon["net_rate"] = pd.to_numeric(dragon["net_rate"], errors="coerce")
        dragon = dragon.dropna(subset=["net_rate"])

        codes = sorted(dragon["thscode"].astype(str).unique())
        start = dragon["date"].min()
        end_dt = pd.to_datetime(dragon["date"].max()) + pd.Timedelta(days=horizon * 2 + 7)
        daily = reader.get_daily(
            ts_codes=codes + ["000300.SH"],
            start_date=pd.to_datetime(start).strftime("%Y-%m-%d"),
            end_date=end_dt.strftime("%Y-%m-%d"))
        if daily.empty:
            return {"error": "行情数据不足"}
        close = daily.pivot_table(index="trade_date", columns="ts_code",
                                  values="close", aggfunc="last").sort_index()
        close.index = pd.to_datetime(close.index)

        fwd = close.shift(-horizon) / close - 1
        bench = fwd["000300.SH"]
        records = []
        for _, row in dragon.iterrows():
            code = str(row["thscode"])
            if code not in fwd.columns:
                continue
            entry_dates = close.index[close.index >= pd.to_datetime(row["date"])]
            if len(entry_dates) == 0:
                continue
            ret = fwd.loc[entry_dates[0], code]
            bmk = bench.loc[entry_dates[0]] if entry_dates[0] in bench.index else None
            if ret is None or pd.isna(ret):
                continue
            records.append({
                "net_rate": float(row["net_rate"]),
                "fwd_ret": float(ret),
                "excess": float(ret - bmk) if bmk is not None and pd.notna(bmk) else None,
            })
        if len(records) < 5:
            return {"error": "可计算样本不足（归档积累中）", "n": len(records)}

        panel = pd.DataFrame(records)
        half = panel["net_rate"].median()
        groups = {"net_buy_high": panel[panel["net_rate"] >= half],
                  "net_buy_low": panel[panel["net_rate"] < half]}

        def _summary(g: pd.DataFrame) -> Dict[str, Any]:
            excess = g["excess"].dropna()
            return {
                "n": int(len(g)),
                "avg_fwd_ret": round(float(g["fwd_ret"].mean()), 4),
                "win_rate": round(float((g["fwd_ret"] > 0).mean()), 4),
                "avg_excess": round(float(excess.mean()), 4) if len(excess) else None,
            }

        return {
            "horizon": horizon,
            "n_days_archived": int(dragon["date"].nunique()),
            "net_buy_high": _summary(groups["net_buy_high"]),
            "net_buy_low": _summary(groups["net_buy_low"]),
            "note": "T 日收盘入场为乐观上界：上榜名单盘后才可知；基准 000300.SH",
        }

    def mood_summary(self, window: int = 20) -> Dict[str, Any]:
        """近期市场情绪概要（供预警快照与极值判定）。"""
        mood = self.read_dataset("mood")
        if mood.empty:
            return {}
        mood = mood.tail(window).copy()
        for col in ("limit_up_count", "limit_down_count", "break_count", "max_streak"):
            if col in mood.columns:
                mood[col] = pd.to_numeric(mood[col], errors="coerce")
        if "break_rate" in mood.columns:
            mood["break_rate"] = pd.to_numeric(mood["break_rate"], errors="coerce")
        latest = mood.iloc[-1]
        return {
            "date": str(mood["date"].iloc[-1]),
            "limit_up_count": None if pd.isna(latest.get("limit_up_count")) else int(latest["limit_up_count"]),
            "limit_down_count": None if pd.isna(latest.get("limit_down_count")) else int(latest["limit_down_count"]),
            "break_rate": None if pd.isna(latest.get("break_rate")) else round(float(latest["break_rate"]), 4),
            "max_streak": None if pd.isna(latest.get("max_streak")) else int(latest["max_streak"]),
            "mean_limit_up": round(float(mood["limit_up_count"].mean()), 1) if mood["limit_up_count"].notna().any() else None,
            "std_limit_up": round(float(mood["limit_up_count"].std()), 1) if mood["limit_up_count"].notna().sum() >= 2 else None,
            "n_days": int(len(mood)),
        }
