"""研报中心 API（数据来自东方财富研报中心，见 research_report_service）。"""

import re

from flask import Blueprint, jsonify, request
from loguru import logger

from app.services.research_report_service import VALID_CATEGORIES, get_research_report_service
from app.utils.data_sources.eastmoney_report_client import EastmoneyReportError

_DATE_RE = re.compile(r"\d{8}")
_INFO_CODE_RE = re.compile(r"AP\d{8,20}")

research_bp = Blueprint("research_api", __name__, url_prefix="/api/research")


def _ok(data) -> "tuple":
    return jsonify({"code": 200, "message": "成功", "data": data})


def _error(message: str, status: int = 500) -> "tuple":
    return jsonify({"code": status, "message": message, "data": None}), status


@research_bp.route("/reports", methods=["GET"])
def get_reports():
    """研报检索（category: industry/stock/strategy/macro/new_stock）。

    begin/end 为 YYYYMMDD 可空（默认近 90 天）；code 仅 stock 类别（6 位数字）。
    """
    category = (request.args.get("category") or "").strip()
    if category not in VALID_CATEGORIES:
        return _error(f"category 取值须为 {'/'.join(VALID_CATEGORIES)}", 400)

    begin = (request.args.get("begin") or "").strip() or None
    end = (request.args.get("end") or "").strip() or None
    if (begin and not _DATE_RE.fullmatch(begin)) or (end and not _DATE_RE.fullmatch(end)):
        return _error("begin/end 格式应为 YYYYMMDD", 400)

    code = (request.args.get("code") or "").strip() or None

    try:
        page = max(1, int(request.args.get("page", 1)))
        size = min(50, max(1, int(request.args.get("size", 20))))
    except ValueError:
        return _error("page/size 须为整数", 400)

    try:
        return _ok(
            get_research_report_service().search_reports(
                category, page=page, size=size, begin=begin, end=end, code=code
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except EastmoneyReportError as exc:
        logger.warning(f"研报正文上游错误: {exc}")
        return _error(f"研报内容获取失败: {exc.message}", 502)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"研报API错误: {exc}")
        return _error(f"研报获取失败: {exc}")


@research_bp.route("/content", methods=["GET"])
def get_report_content():
    """研报正文提取（PDF 下载 + PyMuPDF 文本）。

    info_code 类（行业/个股/新股）传 info_code；策略/宏观传 category+encode。
    """
    info_code = (request.args.get("info_code") or "").strip() or None
    category = (request.args.get("category") or "").strip() or None
    encode = (request.args.get("encode") or "").strip() or None

    # info_code 优先（列表接口的行业/个股/新股条目同时带 encodeUrl，以前者为准）
    if info_code:
        if not _INFO_CODE_RE.fullmatch(info_code):
            return _error("info_code 格式不合法（AP 开头研报编号）", 400)
    elif encode and category:
        if category not in ("strategy", "macro"):
            return _error("encode 参数须配合 category=strategy/macro 使用", 400)
    else:
        return _error("需要 info_code 参数，或 category(strategy/macro)+encode 参数", 400)

    try:
        return _ok(
            get_research_report_service().get_report_content(
                info_code=info_code, category=category, encode=encode
            )
        )
    except ValueError as exc:
        return _error(str(exc), 400)
    except EastmoneyReportError as exc:
        logger.warning(f"研报正文上游错误: {exc}")
        return _error(f"研报内容获取失败: {exc.message}", 502)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"研报正文API错误: {exc}")
        return _error(f"研报内容获取失败: {exc}")
