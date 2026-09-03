from pathlib import Path


def test_readme_marks_realtime_analysis_status_honestly():
    """实时行情分析已从"仅设计"进入开发（监控/指标/信号/风险页面可用），
    README 必须在能力矩阵中如实标注其状态，而不是回退到夸大或过时的说法。"""
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "实时行情分析" in readme
    # 能力矩阵中如实标注（部分实现：页面可用、依赖本地分钟数据同步）
    assert "实时行情分析 | 部分实现" in readme
    # 过时的说法不应再出现
    assert "实时行情分析当前仅做设计，不进入开发范围" not in readme


def test_analysis_doc_marks_realtime_analysis_as_design_only():
    analysis_doc = Path("docs/analysis/项目现状与完整量化工程差距分析.md").read_text(encoding="utf-8")

    assert "实时行情分析当前仅做设计，不进入本阶段开发范围" in analysis_doc


def test_realtime_design_boundary_doc_exists_and_declares_scope():
    design_doc = Path("docs/plans/2026-04-04-realtime-analysis-design-boundary.md")

    assert design_doc.exists()

    content = design_doc.read_text(encoding="utf-8")
    assert "实时行情分析边界说明" in content
    assert "当前仅输出设计方案" in content
    assert "不开发实时行情接入" in content
