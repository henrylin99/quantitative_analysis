from pathlib import Path


def test_models_template_uses_backend_training_job_polling():
    html = Path("app/templates/ml_factor/models.html").read_text(encoding="utf-8")

    assert "Math.random() * 10 + 2" not in html
    assert "trainingInterval = setInterval" not in html
    assert "/api/ml-factor/models/train-jobs/" in html


def test_models_template_supports_model_detail_view_and_datetime_formatting():
    html = Path("app/templates/ml_factor/models.html").read_text(encoding="utf-8")

    assert "function viewModel(" in html
    assert "/api/ml-factor/models/${modelId}" in html
    assert "function formatDisplayDateTime(" in html
    assert "onclick=\"viewModel(" in html
