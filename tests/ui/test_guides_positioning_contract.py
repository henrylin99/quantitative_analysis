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
