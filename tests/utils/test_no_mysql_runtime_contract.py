from pathlib import Path


def test_docs_and_config_label_mysql_as_legacy_only():
    readme = Path("README.md").read_text(encoding="utf-8")
    claude = Path("CLAUDE.md").read_text(encoding="utf-8")
    config_source = Path("config.py").read_text(encoding="utf-8")

    assert "仍需 MySQL 5.7 或 8.x" not in readme
    assert "默认会同时启动 Web、MySQL 和 Redis" not in readme
    assert "MySQL-compatible app state" not in claude
    assert "SQLALCHEMY_DATABASE_URI = MYSQL_DATABASE_URI" not in config_source
