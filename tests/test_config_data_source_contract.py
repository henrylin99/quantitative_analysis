import pytest

from config import Config
from app.utils.db_utils import DatabaseUtils


def test_parquet_is_the_default_data_source():
    assert Config.DATA_SOURCE == "parquet"
    assert Config.MYSQL_DATABASE_URI.startswith("mysql+pymysql://")


def test_mysql_connection_is_explicitly_compatibility_only(monkeypatch):
    monkeypatch.setattr(DatabaseUtils, "_mysql_compat_enabled", False, raising=False)

    with pytest.raises(RuntimeError, match="MySQL compatibility layer is disabled"):
        DatabaseUtils.connect_to_mysql()
