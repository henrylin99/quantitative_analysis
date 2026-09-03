import importlib
from unittest.mock import patch


def test_config_does_not_ship_with_hardcoded_secret_or_db_password(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with patch("dotenv.load_dotenv", return_value=False):
        config_module = importlib.import_module("config")
        config_module = importlib.reload(config_module)

    # DB_PASSWORD was removed in the SQLite migration — verify it no longer exists
    assert not hasattr(config_module.Config, "DB_PASSWORD")
    assert config_module.Config.SECRET_KEY == ""
