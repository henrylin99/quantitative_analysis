import importlib
from unittest.mock import patch


def test_sqlalchemy_defaults_to_sqlite_while_market_data_defaults_to_parquet():
    with patch("dotenv.load_dotenv", return_value=False):
        config_module = importlib.import_module("config")
        config_module = importlib.reload(config_module)

    assert config_module.Config.DATA_SOURCE == "parquet"
    assert config_module.Config.SQLALCHEMY_DATABASE_URI.startswith("sqlite:///")
