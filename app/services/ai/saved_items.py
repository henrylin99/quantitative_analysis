"""AI 工作台沉淀：常用查询（prompt 模板）与看板（保存的分析结果）。

此前 AI 工具的 20 个结果都是一次性的，看完即丢。这里提供两类沉淀：
- queries：常用查询模板（标题 + prompt 文本），点击即回填输入框；
- boards：把一段分析结论/表格（markdown）保存为命名看板，供随时回看。

落盘 data/ai_workbench/saved.json，各保留 50 条；原子写 + 线程锁。
AI 侧有同名工具（save_board / save_query / list_saved / delete_saved），
前端侧走 /ai-assistant/saved 端点，两边共用同一份存储。
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

_DIR_NAME = "ai_workbench"
_FILE_NAME = "saved.json"
_MAX_PER_KIND = 50

_lock = threading.Lock()


def _slug(text: str, max_len: int = 24) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(text or ""))[:max_len]
    return cleaned or datetime.now().strftime("%Y%m%d%H%M%S")


class AiSavedStore:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.getenv(
                "DATA_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data"),
            )
        self.data_dir = data_dir

    @property
    def _path(self) -> str:
        return os.path.join(self.data_dir, _DIR_NAME, _FILE_NAME)

    # ------------------------------------------------------------------
    def _read(self) -> Dict[str, List[Dict[str, Any]]]:
        try:
            with open(self._path, encoding="utf-8") as f:
                payload = json.load(f)
            return {
                "boards": payload.get("boards", []) or [],
                "queries": payload.get("queries", []) or [],
            }
        except FileNotFoundError:
            return {"boards": [], "queries": []}
        except Exception as e:
            logger.warning(f"读取 AI 沉淀失败: {e}")
            return {"boards": [], "queries": []}

    def _write(self, payload: Dict[str, List[Dict[str, Any]]]) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._path)

    # ------------------------------------------------------------------
    def list_all(self) -> Dict[str, List[Dict[str, Any]]]:
        with _lock:
            payload = self._read()
            return {
                "boards": list(reversed(payload["boards"])),
                "queries": list(reversed(payload["queries"])),
            }

    def save_board(self, title: str, content: str,
                   content_type: str = "markdown",
                   meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not str(content or "").strip():
            raise ValueError("看板内容为空")
        record = {
            "id": f"board_{_slug(title)}_{int(datetime.now().timestamp())}",
            "title": str(title or "").strip() or "未命名看板",
            "content_type": content_type if content_type in ("markdown", "text") else "markdown",
            "content": str(content),
            "meta": meta or {},
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with _lock:
            payload = self._read()
            boards = [b for b in payload["boards"] if b.get("title") != record["title"]]
            boards.append(record)
            payload["boards"] = boards[-_MAX_PER_KIND:]
            self._write(payload)
        return record

    def save_query(self, prompt: str, title: Optional[str] = None) -> Dict[str, Any]:
        prompt = str(prompt or "").strip()
        if not prompt:
            raise ValueError("查询内容为空")
        record = {
            "id": f"query_{_slug(title or prompt)}_{int(datetime.now().timestamp())}",
            "title": str(title or "").strip() or prompt[:30],
            "prompt": prompt,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with _lock:
            payload = self._read()
            queries = [q for q in payload["queries"] if q.get("prompt") != prompt]
            queries.append(record)
            payload["queries"] = queries[-_MAX_PER_KIND:]
            self._write(payload)
        return record

    def delete(self, kind: str, item_id: str) -> bool:
        if kind not in ("boards", "queries"):
            raise ValueError("kind 必须是 boards 或 queries")
        with _lock:
            payload = self._read()
            before = len(payload[kind])
            payload[kind] = [x for x in payload[kind] if x.get("id") != item_id]
            removed = len(payload[kind]) < before
            if removed:
                self._write(payload)
            return removed
