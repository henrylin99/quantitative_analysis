from pathlib import Path


def test_readme_uses_prototype_positioning_and_real_start_command():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "用于学习和二次开发的多因子选股系统原型" in readme
    assert "python run_system.py" in readme
    assert "python app.py" not in readme
    assert "功能完整" not in readme


def test_readme_has_implemented_partial_unimplemented_matrix():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "已实现" in readme
    assert "部分实现" in readme
    assert "未实现/未开放" in readme


def test_readme_reflects_portfolio_and_model_cleanup_progress():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "投资组合页面已具备真实创建、详情、持仓增删改、组合删除和优化结果落库能力" in readme
    assert "模型删除前后端入口已打通" in readme
    assert "投资组合完整 CRUD 与删除闭环" not in readme
    assert "模型删除闭环" not in readme


def test_readme_avoids_full_demo_and_full_report_backend_claims():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "报告列表与生成功能入口" in readme
    assert "运行当前已接通功能入口" in readme
    assert "完整报告管理后台" not in readme
    assert "完整功能演示" not in readme
    assert "运行完整演示" not in readme


def test_readme_avoids_complete_system_summary_claims():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "多因子选股系统原型，适合继续补齐后再扩展使用" in readme
    assert "完整的多因子选股系统" not in readme


def test_readme_uses_neutral_scoring_copy():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "基础选股评分" in readme
    assert "智能选股" not in readme
