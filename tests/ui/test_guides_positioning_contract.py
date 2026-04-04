from pathlib import Path


def test_complete_guide_uses_prototype_positioning_and_real_start_command():
    guide = Path("docs/guides/多因子模型系统完整指南.md").read_text(encoding="utf-8")

    assert "当前仓库应视为用于学习和二次开发的原型系统" in guide
    assert "python run_system.py" in guide
    assert "simple_working_system.py" not in guide
    assert "complete_system_launcher.py" not in guide
    assert "web_interface_v2.py" not in guide
    assert "现在已经完全可用" not in guide
    assert "功能完整" not in guide


def test_feature_list_guide_matches_current_remediation_scope():
    guide = Path("docs/guides/多因子模型系统功能列表.md").read_text(encoding="utf-8")

    assert "当前以真实可用能力为准，不再按完整量化平台对外描述。" in guide
    assert "组合页当前未开放再平衡入口" in guide
    assert "最大夏普比率" not in guide
    assert "最小方差" not in guide
    assert "完整工作流程" not in guide
    assert "完整的量化投资解决方案" not in guide


def test_text2sql_guide_avoids_complete_platform_claims():
    guide = Path("docs/guides/Text2SQL功能列表.md").read_text(encoding="utf-8")

    assert "当前仅说明 Text2SQL 模块自身的实现状态，不代表整个仓库已达到完整交付状态。" in guide
    assert "功能开发完成" not in guide
    assert "完全集成" not in guide
    assert "功能完整的智能查询系统" not in guide
