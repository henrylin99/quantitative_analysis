from pathlib import Path

import pytest

pytestmark = pytest.mark.module_data_jobs


def test_docs_and_prompt_language_default_to_parquet_not_mysql():
    readme = Path("README.md").read_text(encoding="utf-8")
    claude = Path("CLAUDE.md").read_text(encoding="utf-8")
    llm_service = Path("app/services/llm_service.py").read_text(encoding="utf-8")

    forbidden = [
        "MySQL (默认，建议用MySQL)",
        "生成标准的MySQL SQL语句",
        "数据库: MySQL / SQLite",
    ]

    for phrase in forbidden:
        assert phrase not in readme
        assert phrase not in claude
        assert phrase not in llm_service

    assert "Parquet 文件（默认）" in readme
    assert "DATA_SOURCE" in claude
    assert "默认兼容 MySQL 语法" in llm_service
