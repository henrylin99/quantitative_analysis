from pathlib import Path


def test_deployment_baseline_files_exist():
    assert Path("Dockerfile").exists()
    assert Path("docker-compose.yml").exists()
    assert Path(".github/workflows/test.yml").exists()
    assert Path("pytest.ini").exists()
    assert Path("docs/guides/DEPLOYMENT_GUIDE.md").exists()
