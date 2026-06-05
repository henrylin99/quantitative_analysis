from config import Config


def test_parquet_is_the_default_data_source():
    assert Config.DATA_SOURCE == "parquet"
    assert Config.SQLALCHEMY_DATABASE_URI.startswith("sqlite:///")
    assert Config.SQLITE_DATABASE_URI == Config.SQLALCHEMY_DATABASE_URI
    assert not hasattr(Config, "MYSQL_DATABASE_URI")
    assert not hasattr(Config, "MYSQL_COMPAT_ENABLED")
