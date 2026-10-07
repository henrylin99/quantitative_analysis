"""自选股服务端持久化：分组 / 备注 / 价格提醒。

此前自选股只存浏览器 localStorage（清缓存即丢，且无法配合定时任务）。
现落盘 data/watchlist/watchlist.json：
    {"items": [{"ts_code", "group", "note", "alert_high", "alert_low", "added_at"}]}

价格提醒（WatchlistAlertService）挂在每日调度里：收盘数据就绪后用最近
收盘价对比 alert_high / alert_low，触发即记入 data/watchlist/alerts.json
（同票同方向同日去重，保留 100 条），并经 AlertPushService 外推（若已配置）。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

_DIR_NAME = "watchlist"
_ITEMS_FILE = "watchlist.json"
_ALERTS_FILE = "alerts.json"
_MAX_ALERTS = 100

_lock = threading.Lock()


class WatchlistService:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir

    @property
    def _items_path(self) -> str:
        return os.path.join(self.data_dir, _DIR_NAME, _ITEMS_FILE)

    @property
    def _alerts_path(self) -> str:
        return os.path.join(self.data_dir, _DIR_NAME, _ALERTS_FILE)

    # ------------------------------------------------------------------
    def list_items(self) -> List[Dict[str, Any]]:
        with _lock:
            return self._read_items()

    def _read_items(self) -> List[Dict[str, Any]]:
        try:
            with open(self._items_path, encoding="utf-8") as f:
                return json.load(f).get("items", [])
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"读取自选股失败: {e}")
            return []

    def _write_items(self, items: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self._items_path), exist_ok=True)
        tmp = self._items_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._items_path)

    @staticmethod
    def _normalize(code: str) -> Optional[str]:
        text = str(code or "").strip().upper()
        if len(text) == 6 and text.isdigit():
            if text.startswith("6"):
                return f"{text}.SH"
            if text.startswith(("8", "4")):
                return f"{text}.BJ"
            return f"{text}.SZ"
        return text if text else None

    def _sanitize_item(self, raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        code = self._normalize(raw.get("ts_code"))
        if not code:
            return None

        def _num(key: str) -> Optional[float]:
            v = raw.get(key)
            if v is None or v == "":
                return None
            try:
                n = float(v)
            except (TypeError, ValueError):
                return None
            return n if n > 0 else None

        return {
            "ts_code": code,
            "group": str(raw.get("group") or "").strip() or "默认",
            "note": str(raw.get("note") or "").strip(),
            "alert_high": _num("alert_high"),
            "alert_low": _num("alert_low"),
            "added_at": str(raw.get("added_at")
                            or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        }

    def replace_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """整体替换（PUT 语义）；老 localStorage 迁移也走这里。"""
        clean: List[Dict[str, Any]] = []
        seen = set()
        for raw in items or []:
            item = self._sanitize_item(raw)
            if item and item["ts_code"] not in seen:
                seen.add(item["ts_code"])
                clean.append(item)
        with _lock:
            self._write_items(clean)
        return clean

    def add_item(self, ts_code: str, group: str = "", note: str = "") -> Dict[str, Any]:
        with _lock:
            items = self._read_items()
            item = self._sanitize_item({"ts_code": ts_code, "group": group, "note": note})
            if item is None:
                raise ValueError("未识别的股票代码")
            existing = next((x for x in items if x["ts_code"] == item["ts_code"]), None)
            if existing:
                return existing
            items.append(item)
            self._write_items(items)
            return item

    def update_item(self, ts_code: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with _lock:
            items = self._read_items()
            code = self._normalize(ts_code)
            for i, item in enumerate(items):
                if item["ts_code"] != code:
                    continue
                merged = self._sanitize_item({**item, **(patch or {}), "ts_code": code,
                                              "added_at": item["added_at"]})
                if merged:
                    items[i] = merged
                    self._write_items(items)
                    return merged
            return None

    def remove_item(self, ts_code: str) -> bool:
        with _lock:
            items = self._read_items()
            code = self._normalize(ts_code)
            remaining = [x for x in items if x["ts_code"] != code]
            if len(remaining) == len(items):
                return False
            self._write_items(remaining)
            return True


class WatchlistAlertService:
    """价格提醒检查：最近收盘价 vs alert_high / alert_low。"""

    def __init__(self, data_dir: Optional[str] = None):
        self.svc = WatchlistService(data_dir)

    @property
    def _alerts_path(self) -> str:
        return self.svc._alerts_path

    def list_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with open(self._alerts_path, encoding="utf-8") as f:
                return json.load(f).get("alerts", [])[-limit:]
        except Exception:
            return []

    def check(self) -> Dict[str, Any]:
        """对设了提醒价的自选股跑一轮检查，返回新触发的提醒。"""
        items = [x for x in self.svc.list_items()
                 if x.get("alert_high") or x.get("alert_low")]
        if not items:
            return {"checked": 0, "triggered": []}

        from app.services.data_reader import ParquetDataReader

        reader = ParquetDataReader()
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        try:
            daily = reader.get_daily(ts_codes=[x["ts_code"] for x in items],
                                     start_date=start, end_date=end)
        except Exception as e:
            logger.warning(f"价格提醒读取行情失败: {e}")
            return {"checked": len(items), "error": str(e), "triggered": []}
        if daily.empty:
            return {"checked": len(items), "triggered": []}

        closes: Dict[str, tuple] = {}
        d = daily.copy()
        d["trade_date"] = d["trade_date"].astype(str)
        last = d.sort_values("trade_date").groupby("ts_code").tail(1)
        for _, r in last.iterrows():
            closes[r["ts_code"]] = (str(r["trade_date"])[:10], float(r["close"]))

        with _lock:
            existing = self.list_alerts()
            seen = {(a["ts_code"], a["kind"], a["close_date"]) for a in existing}
            new_alerts = []
            for item in items:
                close_info = closes.get(item["ts_code"])
                if not close_info:
                    continue
                close_date, close = close_info
                for kind, threshold in (("above", item.get("alert_high")),
                                        ("below", item.get("alert_low"))):
                    if not threshold:
                        continue
                    hit = close >= threshold if kind == "above" else close <= threshold
                    if not hit or (item["ts_code"], kind, close_date) in seen:
                        continue
                    arrow = "≥" if kind == "above" else "≤"
                    new_alerts.append({
                        "ts_code": item["ts_code"],
                        "kind": kind,
                        "close": close,
                        "close_date": close_date,
                        "threshold": threshold,
                        "message": f"{item['ts_code']} 收盘 {close} {arrow} 提醒价 {threshold}"
                                   f"（{close_date}）",
                        "triggered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
            if new_alerts:
                alerts = (existing + new_alerts)[-_MAX_ALERTS:]
                os.makedirs(os.path.dirname(self._alerts_path), exist_ok=True)
                tmp = self._alerts_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"alerts": alerts}, f, ensure_ascii=False)
                os.replace(tmp, self._alerts_path)

        if new_alerts:
            self._push(new_alerts)
        return {"checked": len(items), "triggered": new_alerts}

    @staticmethod
    def _push(alerts: List[Dict[str, Any]]) -> None:
        try:
            from app.services.alert_push_service import AlertPushService

            text = "\n".join(f"· {a['message']}" for a in alerts)
            record = {
                "scan_date": datetime.now().strftime("%Y-%m-%d"),
                "alerts": [{"level": "warn", "message": a["message"]} for a in alerts],
            }
            svc = AlertPushService()
            cfg = svc.get_config()
            if cfg["enabled"] and cfg["channels"]:
                results = []
                for ch in cfg["channels"]:
                    ok, message = svc._send(ch, "🔔 自选股价格提醒", f"**自选股价格提醒**\n{text}", record)
                    results.append({"type": ch["type"], "ok": ok, "message": message})
                svc._append_log("watchlist", results)
        except Exception:
            logger.warning("价格提醒推送失败", exc_info=True)
