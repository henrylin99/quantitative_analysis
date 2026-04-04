from pathlib import Path


def test_enhanced_financial_factors_guide_avoids_most_complete_claims():
    guide = Path("docs/guides/ENHANCED_FINANCIAL_FACTORS_README.md").read_text(encoding="utf-8")

    assert "当前基于三张财务报表的已接入字段计算财务因子，实际覆盖范围以当前表结构和脚本实现为准。" in guide
    assert "当前字段覆盖范围" in guide
    assert "这是目前最全面的财务因子计算工具" not in guide
    assert "全面覆盖" not in guide
    assert "完整字段" not in guide


def test_real_training_data_guide_avoids_mock_target_recommendation_as_default():
    guide = Path("docs/guides/data_requirements_for_real_training.md").read_text(encoding="utf-8")

    assert "当前文档仅用于说明真实训练所需的数据缺口，不建议再默认使用模拟目标变量方案。" in guide
    assert "建议继续使用模拟目标变量方案" not in guide
    assert "立即可用" not in guide
    assert "展示完整的ML流程" not in guide
    assert "R²达到0.53" not in guide
