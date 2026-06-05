import importlib
from unittest.mock import patch

from app import create_app
from app.extensions import db


def test_sqlalchemy_defaults_to_sqlite_while_market_data_defaults_to_parquet():
    with patch("dotenv.load_dotenv", return_value=False):
        config_module = importlib.import_module("config")
        config_module = importlib.reload(config_module)

    assert config_module.Config.DATA_SOURCE == "parquet"
    assert config_module.Config.SQLALCHEMY_DATABASE_URI.startswith("sqlite:///")
    assert config_module.Config.SQLALCHEMY_DATABASE_URI.endswith("stock_cursor.sqlite3")
    assert config_module.Config.SQLITE_DATABASE_URI == config_module.Config.SQLALCHEMY_DATABASE_URI
    assert not hasattr(config_module.Config, "MYSQL_COMPAT_ENABLED")
    assert not hasattr(config_module.Config, "MYSQL_DATABASE_URI")


def test_app_models_initialize_against_sqlite_default():
    app = create_app()

    with app.app_context():
        assert app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///")
        assert app.config["DATA_SOURCE"] == "parquet"
        assert db.engine.url.get_backend_name() == "sqlite"
        assert db.engine.url.database.endswith("stock_cursor.sqlite3")
