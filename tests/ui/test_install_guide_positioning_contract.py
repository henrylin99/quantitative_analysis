from pathlib import Path


def test_install_guide_avoids_full_version_positioning():
    guide = Path("docs/guides/INSTALL_GUIDE.md").read_text(encoding="utf-8")

    assert "可选增强版本" in guide
    assert "开发调试（按需启用增强能力）" in guide
    assert "部署环境（补齐能力后再使用）" in guide
    assert "完整版本" not in guide
    assert "开发者（完整功能）" not in guide
    assert "生产环境" not in guide
