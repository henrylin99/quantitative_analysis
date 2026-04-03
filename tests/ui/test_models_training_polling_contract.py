from pathlib import Path


def test_models_template_uses_backend_training_job_polling():
    html = Path("app/templates/ml_factor/models.html").read_text(encoding="utf-8")

    assert "Math.random() * 10 + 2" not in html
    assert "trainingInterval = setInterval" not in html
    assert "/api/ml-factor/models/train-jobs/" in html
