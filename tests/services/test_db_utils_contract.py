from pathlib import Path


def test_db_utils_does_not_ship_with_root_password_defaults():
    source = Path("app/utils/db_utils.py").read_text(encoding="utf-8")

    assert "os.getenv('DB_PASSWORD', 'root')" not in source
    assert 'os.getenv("DB_PASSWORD", "root")' not in source
    assert "os.getenv('DB_USER', 'root')" not in source
    assert 'os.getenv("DB_USER", "root")' not in source


def test_db_utils_only_keeps_tushare_bootstrap():
    source = Path("app/utils/db_utils.py").read_text(encoding="utf-8")

    assert "connect_to_mysql" not in source
    assert "TUSHARE_TOKEN" in source
