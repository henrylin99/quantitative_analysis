from pathlib import Path

import pytest

pytestmark = pytest.mark.module_ml_model


def test_ml_models_source_does_not_keep_unused_simulated_target_helper():
    source = Path("app/services/ml_models.py").read_text(encoding="utf-8")

    assert "def _generate_simulated_targets" not in source
