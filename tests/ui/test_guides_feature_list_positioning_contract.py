from pathlib import Path


def test_feature_list_avoids_full_report_backend_claim():
    guide = Path("docs/guides/多因子模型系统功能列表.md").read_text(encoding="utf-8")

    assert "报告列表与生成功能入口" in guide
    assert "完整报告管理后台" not in guide


def test_full_guide_avoids_full_report_backend_claim():
    guide = Path("docs/guides/多因子模型系统完整指南.md").read_text(encoding="utf-8")

    assert "报告列表与生成功能入口" in guide
    assert "完整报告管理后台" not in guide
