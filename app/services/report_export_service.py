"""报告导出服务：把结构化报告内容渲染为 HTML / PDF。

报告内容（report_content）是 JSON 结构 {title, generated_at, report_type,
sections[]}，section 类型：metrics / table / chart / summary / alerts / error。

PDF 依赖 weasyprint（可选依赖，requirements-dev 中提供）；未安装时
export_pdf 抛出 WeasyprintUnavailable，API 层引导用户改走 HTML 导出
（浏览器打开后打印为 PDF），不把重依赖加进最小运行链路。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from loguru import logger

_SECTION_COLORS = {
    "primary": "#1a73e8",
    "success": "#188038",
    "danger": "#d93025",
    "warning": "#e37400",
    "info": "#1a73e8",
}

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         color: #202124; margin: 32px auto; max-width: 860px; line-height: 1.55; }}
  h1 {{ font-size: 22px; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; }}
  .meta {{ color: #5f6368; font-size: 13px; margin-bottom: 24px; }}
  h2 {{ font-size: 16px; margin: 24px 0 8px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border: 1px solid #dadce0; padding: 6px 10px; text-align: left; }}
  th {{ background: #f8f9fa; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 12px; }}
  .metric {{ border: 1px solid #dadce0; border-radius: 6px; padding: 10px 14px; min-width: 140px; }}
  .metric .label {{ color: #5f6368; font-size: 12px; }}
  .metric .value {{ font-size: 18px; font-weight: 600; }}
  .summary, .alert-item {{ background: #f8f9fa; border-left: 3px solid #1a73e8;
                          padding: 10px 14px; margin: 8px 0; font-size: 13px; }}
  .alert-item {{ border-left-color: #e37400; }}
  .error {{ color: #d93025; font-size: 13px; }}
  .bar {{ background: #1a73e8; height: 14px; display: inline-block; vertical-align: middle; }}
  .bar-row {{ margin: 6px 0; font-size: 13px; }}
  .bar-label {{ display: inline-block; width: 160px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">报告类型：{report_type}　生成时间：{generated_at}</div>
{body}
</body>
</html>"""


class WeasyprintUnavailable(Exception):
    """weasyprint 未安装，PDF 导出不可用。"""


def _escape(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return (
        text.replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;")
    )


def _render_section(section: Dict[str, Any]) -> str:
    sec_type = section.get("type")
    title = _escape(section.get("title") or "")
    parts = [f"<h2>{title}</h2>"]
    content = section.get("content")

    if sec_type == "metrics" and isinstance(content, list):
        items = []
        for item in content:
            color = _SECTION_COLORS.get(item.get("color"), "#202124")
            items.append(
                f'<div class="metric"><div class="label">{_escape(item.get("label"))}</div>'
                f'<div class="value" style="color:{color}">{_escape(item.get("value"))}</div></div>'
            )
        parts.append(f'<div class="metrics">{"".join(items)}</div>')
    elif sec_type == "table" and isinstance(content, dict):
        columns = content.get("columns") or []
        rows = content.get("rows") or []
        head = "".join(f"<th>{_escape(c)}</th>" for c in columns)
        body_rows = []
        for row in rows:
            if isinstance(row, dict):
                cells = [_escape(row.get(c)) for c in columns]
            else:
                cells = [_escape(row)]
            body_rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
        parts.append(f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>")
        if not rows:
            parts.append('<div class="meta">（无数据行）</div>')
    elif sec_type == "chart" and isinstance(content, dict):
        data = content.get("data") or []
        max_value = max((abs(item.get("value") or 0) for item in data), default=0) or 1
        bars = []
        for item in data:
            width = max(1, int(abs(item.get("value") or 0) / max_value * 300))
            bars.append(
                f'<div class="bar-row"><span class="bar-label">{_escape(item.get("name"))}</span>'
                f'<span class="bar" style="width:{width}px"></span> {_escape(item.get("value"))}</div>'
            )
        parts.append("".join(bars) or '<div class="meta">（无数据）</div>')
    elif sec_type == "alerts" and isinstance(content, list):
        for alert in content:
            parts.append(f'<div class="alert-item">{_escape(alert.get("message") or alert)}</div>')
    elif sec_type == "error":
        parts.append(f'<div class="error">{_escape(content)}</div>')
    else:  # summary 或未知类型：尽力转文本
        parts.append(f'<div class="summary">{_escape(content)}</div>')
    return "".join(parts)


def load_report_content(report) -> Dict[str, Any]:
    """从报告模型解析 report_content；解析失败回退最小结构。"""
    raw = getattr(report, "report_content", None)
    if isinstance(raw, dict):
        return raw
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"报告内容解析失败 id={getattr(report, 'id', '?')}: {exc}")
    return {"title": getattr(report, "report_name", "报告"), "sections": []}


def render_report_html(report) -> str:
    """把报告渲染为独立 HTML 文档。"""
    content = load_report_content(report)
    body = "".join(_render_section(sec) for sec in content.get("sections") or [])
    return _HTML_TEMPLATE.format(
        title=_escape(content.get("title") or getattr(report, "report_name", "报告")),
        report_type=_escape(content.get("report_type") or getattr(report, "report_type", "")),
        generated_at=_escape(content.get("generated_at") or ""),
        body=body,
    )


def export_pdf(report) -> bytes:
    """渲染报告为 PDF 字节流；weasyprint 未安装时抛 WeasyprintUnavailable。"""
    try:
        from weasyprint import HTML
    except Exception as exc:  # noqa: BLE001
        raise WeasyprintUnavailable(
            "weasyprint 未安装，无法生成 PDF；可改用 HTML 导出后在浏览器打印"
        ) from exc
    html = render_report_html(report)
    return HTML(string=html).write_pdf()


def export_filename(report, extension: str) -> str:
    """构造导出文件名：报告名/类型 + 日期 + 扩展名。"""
    name = getattr(report, "report_name", None) or getattr(report, "report_type", "report")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(name))[:60]
    stamp = datetime.now().strftime("%Y%m%d")
    return f"{safe}_{stamp}.{extension}"


def report_digest_text(report, max_chars: int = 1200) -> str:
    """把报告内容压成适合推送渠道的纯文本摘要。"""
    content = load_report_content(report)
    title = content.get("title") or getattr(report, "report_name", "报告")
    lines = []
    for sec in content.get("sections") or []:
        sec_title = sec.get("title") or ""
        sec_type = sec.get("type")
        body = sec.get("content")
        if sec_type == "metrics" and isinstance(body, list):
            detail = "，".join(f"{item.get('label')} {item.get('value')}" for item in body[:6])
            lines.append(f"· {sec_title}：{detail}")
        elif sec_type == "table" and isinstance(body, dict):
            rows = body.get("rows") or []
            lines.append(f"· {sec_title}：{len(rows)} 行")
        elif sec_type == "alerts" and isinstance(body, list):
            for alert in body[:3]:
                lines.append(f"· {_escape(alert.get('message') if isinstance(alert, dict) else alert)}")
        elif sec_type == "error":
            lines.append(f"· {sec_title}：{body}")
        elif isinstance(body, str):
            lines.append(f"· {sec_title}：{body[:200]}")
    text = "\n".join(lines) or "（报告无正文摘要）"
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return f"{title}\n{text}"
