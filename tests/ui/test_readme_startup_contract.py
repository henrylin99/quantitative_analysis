from pathlib import Path


def test_readme_marks_run_py_as_primary_start_command():
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "python run.py" in readme
    assert "run_system.py 用于初始化与诊断" in readme
    assert "run_system.py         # 系统启动器" not in readme
    assert "# 或通过启动器运行" not in readme
