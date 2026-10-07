"""每日预警出站推送：把 DailyAlertService 的扫描结果推到外部渠道。

支持的渠道（push_config.channels[].type）：
- serverchan        Server酱·Turbo，参数 send_key（https://sctapi.ftqq.com）
- wecom_webhook     企业微信群机器人，参数 url
- dingtalk_webhook  钉钉群机器人，参数 url
- webhook           通用 JSON POST（{"title", "text", "scan_date", "alerts"}），参数 url

配置落盘 data/alerts/push_config.json（enabled 默认 false，配置前不影响任何行为）；
每次推送结果追加到 data/alerts/push_log.json（保留最近 50 条）。
推送在扫描线程内同步执行但单渠道超时 10s、任何异常只记日志，绝不影响扫描落盘。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

_DIR_NAME = "alerts"
_CONFIG_FILE = "push_config.json"
_LOG_FILE = "push_log.json"
_MAX_LOG_RECORDS = 50
_HTTP_TIMEOUT = 10.0

_CHANNEL_TYPES = ("serverchan", "wecom_webhook", "dingtalk_webhook", "webhook")
_LOCK = threading.Lock()


class AlertPushService:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"),
            )
        self.data_dir = data_dir

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    @property
    def _config_path(self) -> str:
        return os.path.join(self.data_dir, _DIR_NAME, _CONFIG_FILE)

    @property
    def _log_path(self) -> str:
        return os.path.join(self.data_dir, _DIR_NAME, _LOG_FILE)

    def get_config(self) -> Dict[str, Any]:
        try:
            with open(self._config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            if isinstance(cfg, dict):
                return self._sanitize(cfg)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f"读取推送配置失败: {e}")
        return {"enabled": False, "min_level": "info", "channels": []}

    @staticmethod
    def _sanitize(cfg: Dict[str, Any]) -> Dict[str, Any]:
        channels = cfg.get("channels")
        if not isinstance(channels, list):
            channels = []
        clean = []
        for ch in channels:
            if not isinstance(ch, dict) or ch.get("type") not in _CHANNEL_TYPES:
                continue
            entry = {"type": ch["type"]}
            if ch["type"] == "serverchan":
                entry["send_key"] = str(ch.get("send_key") or "").strip()
            else:
                entry["url"] = str(ch.get("url") or "").strip()
            if entry.get("send_key") or entry.get("url"):
                clean.append(entry)
        min_level = cfg.get("min_level") if cfg.get("min_level") in ("info", "warn") else "info"
        return {"enabled": bool(cfg.get("enabled")), "min_level": min_level, "channels": clean}

    def update_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cfg = self._sanitize(payload if isinstance(payload, dict) else {})
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        tmp = self._config_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._config_path)
        return cfg

    # ------------------------------------------------------------------
    # 推送
    # ------------------------------------------------------------------
    def push_record(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """把一条扫描记录推到所有启用渠道；返回逐渠道结果并落推送日志。"""
        cfg = self.get_config()
        if not cfg["enabled"] or not cfg["channels"]:
            return []
        if cfg["min_level"] == "warn" \
                and not any(a.get("level") == "warn" for a in record.get("alerts") or []):
            return []

        title, text = self._digest(record)
        results = []
        for ch in cfg["channels"]:
            ok, message = self._send(ch, title, text, record)
            results.append({"type": ch["type"], "ok": ok, "message": message})
        self._append_log(record.get("scan_date") or "", results)
        return results

    @staticmethod
    def _digest(record: Dict[str, Any]) -> tuple:
        scan_date = record.get("scan_date") or datetime.now().strftime("%Y-%m-%d")
        lines: List[str] = []
        for a in record.get("alerts") or []:
            icon = "⚠️" if a.get("level") == "warn" else "·"
            lines.append(f"{icon} {a.get('message', '')}")
        regime = record.get("regime") or []
        if regime:
            lines.append("regime：" + " ".join(f"{r['name']}·{r['regime']}" for r in regime))
        sig = record.get("signals") or {}
        if sig.get("stats"):
            c = sig["stats"].get("counts") or {}
            lines.append(f"信号数（挤/共/背）：{c.get('squeeze', 0)}/{c.get('resonance', 0)}/{c.get('divergence', 0)}")
        rot = record.get("rotation") or {}
        if rot.get("top"):
            lines.append("轮动最强：" + "、".join(t["industry"] for t in rot["top"]))
        text = f"**{scan_date} 每日预警**\n" + "\n".join(lines)
        return f"📊 每日预警 {scan_date}", text

    def _send(self, channel: Dict[str, Any], title: str, text: str,
              record: Dict[str, Any]) -> tuple:
        try:
            ctype = channel["type"]
            if ctype == "serverchan":
                resp = requests.post(
                    f"https://sctapi.ftqq.com/{channel['send_key']}.send",
                    data={"title": title, "desp": text}, timeout=_HTTP_TIMEOUT)
            elif ctype == "wecom_webhook":
                resp = requests.post(channel["url"], json={
                    "msgtype": "markdown",
                    "markdown": {"content": text[:1800]},
                }, timeout=_HTTP_TIMEOUT)
            elif ctype == "dingtalk_webhook":
                resp = requests.post(channel["url"], json={
                    "msgtype": "markdown",
                    "markdown": {"title": title, "text": text[:1800]},
                }, timeout=_HTTP_TIMEOUT)
            else:  # webhook
                resp = requests.post(channel["url"], json={
                    "title": title, "text": text,
                    "scan_date": record.get("scan_date"),
                    "alerts": record.get("alerts") or [],
                }, timeout=_HTTP_TIMEOUT)
            if resp.status_code < 200 or resp.status_code >= 300:
                return False, f"HTTP {resp.status_code}"
            body = {}
            try:
                body = resp.json()
            except Exception:
                pass
            # 各渠道业务码：Server酱 code==0、企业微信/钉钉 errcode==0
            for key in ("code", "errcode"):
                if key in body and body[key] != 0:
                    return False, str(body.get("errmsg") or body)
            return True, "ok"
        except requests.exceptions.Timeout:
            return False, "超时（10s）"
        except Exception as e:
            return False, str(e)

    def _append_log(self, scan_date: str, results: List[Dict[str, Any]]) -> None:
        with _LOCK:
            try:
                try:
                    with open(self._log_path, encoding="utf-8") as f:
                        log = json.load(f).get("records", [])
                except Exception:
                    log = []
                log.append({
                    "pushed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "scan_date": scan_date,
                    "results": results,
                })
                log = log[-_MAX_LOG_RECORDS:]
                os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
                tmp = self._log_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"records": log}, f, ensure_ascii=False)
                os.replace(tmp, self._log_path)
            except Exception:
                logger.warning("写推送日志失败", exc_info=True)

    def list_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            with open(self._log_path, encoding="utf-8") as f:
                return json.load(f).get("records", [])[-limit:]
        except Exception:
            return []

    def send_test(self) -> Dict[str, Any]:
        """向当前配置的所有启用渠道发一条测试消息。"""
        cfg = self.get_config()
        if not cfg["channels"]:
            return {"ok": False, "message": "未配置任何推送渠道"}
        record = {
            "scan_date": datetime.now().strftime("%Y-%m-%d"),
            "alerts": [{"level": "info", "message": "这是一条测试推送（push-test）"}],
        }
        results = []
        for ch in cfg["channels"]:
            ok, message = self._send(ch, "📊 量化平台推送测试", "**量化平台推送测试**\n配置成功。", record)
            results.append({"type": ch["type"], "ok": ok, "message": message})
        self._append_log("push-test", results)
        return {"ok": all(r["ok"] for r in results), "results": results}
