from pathlib import Path

import pytest

pytestmark = pytest.mark.module_feature_engineering


def test_factor_management_template_uses_backend_is_builtin_and_capabilities():
    html = Path("app/templates/ml_factor/index.html").read_text(encoding="utf-8")

    assert "is_builtin: true" not in html
    assert "/api/ml-factor/factors/custom-capabilities" in html
    assert "allowed_columns" in html
    assert "allowed_series_methods" in html
