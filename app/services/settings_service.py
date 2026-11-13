"""系统配置服务：tushare / 扶摇（fuyao）/ 大模型（LLM）三类关键配置的
状态读取与在线修改。

设计要点：
- 配置唯一落盘源仍是仓库根 ``.env``（不引入配置表避免双源漂移）；
- 修改时同步 ``os.environ`` 与 Flask ``app.config['AI_ASSISTANT_CONFIG']``，
  保证**不重启即生效**（读取方均为 os.getenv 惰性读取；db_utils 已改惰性）；
- fuyao 状态探测有 5 分钟缓存（market_snapshot_service），更新 key 后主动
  失效该缓存，让数据源中心立即反映新 key。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import current_app

# 允许通过设置 API 写入的环境变量（白名单，防任意 env 注入）
WRITABLE_ENV_KEYS = (
    "TUSHARE_TOKEN",
    "FUYAO_API_KEY",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_PROVIDER",
)

_PLACEHOLDER_VALUES = ("", "your_tushare_token", "your_api_key", "sk-xxx")

_ENV_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _project_root() -> Path:
    # app/services/settings_service.py → 仓库根
    return Path(__file__).resolve().parents[2]


def env_file_path() -> Path:
    return _project_root() / ".env"


def _mask(value: str) -> Optional[str]:
    """脱敏展示：只回显尾 4 位；过短或占位值不回显。"""
    value = (value or "").strip()
    if not value or value in _PLACEHOLDER_VALUES:
        return None
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def _is_configured(key: str) -> bool:
    value = (os.getenv(key) or "").strip()
    return value not in _PLACEHOLDER_VALUES


def get_settings(probe_fuyao: bool = False) -> Dict[str, Any]:
    """三类配置状态（GET /api/settings 用）。

    默认只做本地 token 存在性检查（零网络开销）；``probe_fuyao=True`` 时
    复用 market_snapshot_service 的真实探测（数据源中心已有该能力）。
    """
    result: Dict[str, Any] = {
        "tushare": {
            "configured": _is_configured("TUSHARE_TOKEN"),
            "token_masked": _mask(os.getenv("TUSHARE_TOKEN") or ""),
        },
        "fuyao": {
            "configured": _is_configured("FUYAO_API_KEY"),
            "api_key_masked": _mask(os.getenv("FUYAO_API_KEY") or ""),
        },
        "llm": {
            "configured": _llm_configured(),
            "base_url": (os.getenv("LLM_BASE_URL") or "").strip() or None,
            "model": (os.getenv("LLM_MODEL") or "").strip() or None,
            "api_key_masked": _mask(os.getenv("LLM_API_KEY") or ""),
            # openai | ollama | anthropic；空 = 未指定（LLMClient 按 base_url 推断）
            "provider": (os.getenv("LLM_PROVIDER") or "").strip() or None,
        },
    }
    if probe_fuyao and result["fuyao"]["configured"]:
        try:
            from app.services.market_snapshot_service import MarketSnapshotService

            status = MarketSnapshotService().get_source_status(force=True)
            result["fuyao"]["ok"] = status.get("fuyao", {}).get("ok")
            result["fuyao"]["error"] = status.get("fuyao", {}).get("error")
        except Exception as exc:  # 探测失败不影响状态返回
            result["fuyao"]["ok"] = False
            result["fuyao"]["error"] = str(exc)
    result["all_configured"] = all(
        (result[name].get("configured") for name in ("tushare", "fuyao", "llm"))
    )
    return result


def _llm_configured() -> bool:
    """与 LLMClient.configured 同口径：云端端点需要 api_key，本地端点免 key。"""
    from urllib.parse import urlparse

    base_url = (os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").strip()
    model = (os.getenv("LLM_MODEL") or "").strip()
    if not base_url or not model:
        return False
    if _is_configured("LLM_API_KEY"):
        return True
    host = (urlparse(base_url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def update_settings(updates: Dict[str, str]) -> Dict[str, Any]:
    """白名单键写入 .env + os.environ + 刷新运行中缓存的配置。

    :param updates: {env_key: value}，仅接受 WRITABLE_ENV_KEYS 内的键；
        值为空字符串视为「清空该配置」。
    :return: {"updated": [已更新键], "reboot_required": False}
    """
    unknown = [k for k in updates if k not in WRITABLE_ENV_KEYS]
    if unknown:
        raise ValueError(f"不支持的配置项: {', '.join(unknown)}")

    normalized: Dict[str, str] = {}
    for key, value in (updates or {}).items():
        value = str(value).strip() if value is not None else ""
        # 允许清空；不允许写入占位值（防止误把示例值当真实配置）
        if value and value in _PLACEHOLDER_VALUES:
            raise ValueError(f"{key} 不能设置为占位值")
        normalized[key] = value

    _write_env_file(normalized)

    for key, value in normalized.items():
        os.environ[key] = value

    _refresh_runtime_caches(set(normalized))

    return {"updated": sorted(normalized), "reboot_required": False}


def _write_env_file(updates: Dict[str, str]) -> None:
    """保留 .env 其他行，只替换/追加目标键；无文件则创建。"""
    path = env_file_path()
    lines: List[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    new_lines: List[str] = []
    for line in lines:
        match = _ENV_LINE_RE.match(line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            new_lines.append(f"{key}={remaining.pop(key)}")
        else:
            new_lines.append(line)

    # 追加未命中（新键）的行；保证与既有内容之间有空行分隔
    if remaining:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        for key, value in remaining.items():
            new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _refresh_runtime_caches(changed: set) -> None:
    """让运行中进程的派生配置立即反映新 env 值。"""
    # 1) LLM：AssistantService 每次请求从 app.config['AI_ASSISTANT_CONFIG']
    #    取配置（config.py 在 import 时固化），更新后需要重写该 dict
    llm_keys = changed & {"LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_PROVIDER"}
    if llm_keys and current_app:
        cfg = dict(current_app.config.get("AI_ASSISTANT_CONFIG") or {})
        if "LLM_API_KEY" in llm_keys:
            cfg["api_key"] = os.getenv("LLM_API_KEY", "")
        if "LLM_BASE_URL" in llm_keys:
            cfg["base_url"] = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        if "LLM_MODEL" in llm_keys:
            cfg["model"] = os.getenv("LLM_MODEL", "deepseek-chat")
        if "LLM_PROVIDER" in llm_keys:
            cfg["provider"] = os.getenv("LLM_PROVIDER", "")
        current_app.config["AI_ASSISTANT_CONFIG"] = cfg

    # 2) fuyao：数据源状态有 5 分钟缓存，换 key 后主动失效
    if "FUYAO_API_KEY" in changed:
        try:
            from app.services.market_snapshot_service import get_market_snapshot_service

            service = get_market_snapshot_service()
            with service._lock:
                service._status_cache = None
        except Exception:
            pass


def test_llm(provider: str = "", base_url: str = "", model: str = "",
             api_key: str = "") -> Dict[str, Any]:
    """真实调用一次大模型验证配置可用性（POST /api/settings/test-llm 用）。

    参数为空时回退到当前 env 配置；provider 支持 openai / ollama / anthropic，
    空则由 LLMClient 按 base_url 推断。
    """
    import time

    from app.services.ai.llm_client import LLMClient, LLMClientError

    config = {
        "provider": provider or os.getenv("LLM_PROVIDER", ""),
        "base_url": base_url or os.getenv("LLM_BASE_URL") or "",
        "model": model or os.getenv("LLM_MODEL") or "",
        "api_key": api_key or os.getenv("LLM_API_KEY") or "",
        "timeout": 60,
        # 推理模型 reasoning 会先吃 token，测试上限给足
        "max_tokens": 512,
        "temperature": 0.0,
    }
    if not config["base_url"] or not config["model"]:
        return {"ok": False, "error": "base_url / model 未配置"}

    client = LLMClient(config)
    if not client.configured:
        return {"ok": False, "error": "该 provider 需要 api_key（本地 Ollama 可免）"}

    started = time.monotonic()
    try:
        events = list(client.chat(
            [{"role": "user", "content": "请只回复两个字：可用"}],
            stream=False,
        ))
    except LLMClientError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # 兜底：协议/网络异常都以友好信息返回
        return {"ok": False, "error": f"调用失败: {exc}"}

    reply = ""
    for event in events:
        if event.get("type") == "message":
            reply = (event.get("message") or {}).get("content") or ""
    # 推理模型小 token 预算下可能只有 reasoning 没有正文——只要拿到 200
    # 且无 error 事件即视为连通（正文为空提示用户换模型或加大 max_tokens）
    had_error = any(e.get("type") == "error" for e in events)
    if had_error:
        return {"ok": False, "error": "大模型返回错误（详见服务日志）"}
    return {
        "ok": True,
        "provider": client.provider,
        "model": client.model,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "reply": reply[:80] or "（无正文返回，可能是推理模型 token 上限过小，连通性正常）",
    }
