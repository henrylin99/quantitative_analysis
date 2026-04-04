from pathlib import Path


def test_db_utils_does_not_ship_with_root_password_defaults():
    source = Path("app/utils/db_utils.py").read_text(encoding="utf-8")

    assert "os.getenv('DB_PASSWORD', 'root')" not in source
    assert 'os.getenv("DB_PASSWORD", "root")' not in source
    assert "os.getenv('DB_USER', 'root')" not in source
    assert 'os.getenv("DB_USER", "root")' not in source


def test_db_utils_requires_explicit_db_configuration():
    source = Path("app/utils/db_utils.py").read_text(encoding="utf-8")

    assert "未配置数据库连接参数" in source
