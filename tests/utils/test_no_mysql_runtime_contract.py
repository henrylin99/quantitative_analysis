from pathlib import Path


def test_docs_config_and_llm_prompt_do_not_assume_mysql_as_default():
    readme = Path("README.md").read_text(encoding="utf-8")
    claude = Path("CLAUDE.md").read_text(encoding="utf-8")
    config_source = Path("config.py").read_text(encoding="utf-8")
    llm_service = Path("app/services/llm_service.py").read_text(encoding="utf-8")

    assert "仍需 MySQL 5.7 或 8.x" not in readme
    assert "默认会同时启动 Web、MySQL 和 Redis" not in readme
    assert "DB_HOST, DB_USER, DB_PASSWORD, DB_NAME" not in claude
    assert "MYSQL_DATABASE_URI" not in config_source
    assert "MYSQL_COMPAT_ENABLED" not in config_source
    assert "默认兼容 MySQL 语法" not in llm_service
    assert "MySQL" not in llm_service
    assert "目标数据库是 SQLite" in llm_service
    assert "SQLite 兼容" in llm_service
