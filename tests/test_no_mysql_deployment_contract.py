from pathlib import Path


def test_deployment_defaults_do_not_ship_mysql_runtime():
    env_example = Path(".env.example").read_text(encoding="utf-8")
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    requirements = Path("requirements.txt").read_text(encoding="utf-8")

    assert "MYSQL_COMPAT_ENABLED" not in env_example
    assert "DB_HOST=localhost" not in env_example
    assert "DB_USER=root" not in env_example
    assert "DB_PASSWORD=root" not in env_example
    assert "DB_NAME=stock_cursor" not in env_example
    assert "mysql:" not in compose
    assert "mysql:8" not in compose
    assert "PyMySQL" not in requirements
