from pathlib import Path


def test_models_template_marks_training_scope_as_backend_driven():
    html = Path("app/templates/ml_factor/models.html").read_text(encoding="utf-8")

    assert "当前页面仅展示真实模型定义、训练轮询和预测结果入口。" in html


def test_scoring_template_marks_scope_as_supported_methods_only():
    html = Path("app/templates/ml_factor/scoring.html").read_text(encoding="utf-8")

    assert "当前仅开放已接通的因子评分与 ML 评分链路。" in html
    assert "基于因子和机器学习模型对股票进行评分排名" not in html
