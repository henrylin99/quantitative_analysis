import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    import click.core as click_core

    if not hasattr(click_core, "ParameterSource"):
        class ParameterSource:  # pragma: no cover - compatibility shim
            COMMANDLINE = "COMMANDLINE"
            DEFAULT = "DEFAULT"
            DEFAULT_MAP = "DEFAULT_MAP"
            ENVIRONMENT = "ENVIRONMENT"
            PROMPT = "PROMPT"

        click_core.ParameterSource = ParameterSource
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "xgboost" not in sys.modules:
    sys.modules["xgboost"] = types.SimpleNamespace(
        XGBRegressor=object,
        XGBClassifier=object,
    )

if "lightgbm" not in sys.modules:
    sys.modules["lightgbm"] = types.SimpleNamespace(
        LGBMRegressor=object,
        LGBMClassifier=object,
    )

if "cvxpy" not in sys.modules:
    sys.modules["cvxpy"] = types.SimpleNamespace()

if "baostock" not in sys.modules:
    sys.modules["baostock"] = types.SimpleNamespace()

if "tushare" not in sys.modules:
    sys.modules["tushare"] = types.SimpleNamespace(
        pro_api=lambda *args, **kwargs: None,
        set_token=lambda *args, **kwargs: None,
    )


@pytest.fixture()
def app():
    import app as app_module

    with patch.object(app_module.socketio, "init_app", return_value=None):
        flask_app = app_module.create_app("development")
    with flask_app.app_context():
        yield flask_app
