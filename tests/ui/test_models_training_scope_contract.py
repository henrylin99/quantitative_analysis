from pathlib import Path


def test_models_template_does_not_claim_fake_stop_training_action():
    html = Path("app/templates/ml_factor/models.html").read_text(encoding="utf-8")

    assert "停止训练" not in html
    assert "关闭窗口不会中断后端训练任务" in html
    assert "继续后台训练" in html
