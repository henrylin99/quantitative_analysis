# Startup And Data Management Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一系统启动入口、补齐启动前健康检查，并为后续拆分独立数据管理页面建立稳定基础。

**Architecture:** 保留 `run.py` 作为唯一标准 Web 启动入口，`run_system.py` 退回初始化/诊断工具定位。健康检查能力抽到独立模块，供两个入口复用。第一批只修复启动与检查链路，不在本批直接拆大页面，但会为“数据管理独立页面”准备路由和检查清单基座。

**Tech Stack:** Python, Flask, SQLAlchemy, Jinja, pytest

---

### Task 1: 建立启动健康检查契约

**Files:**
- Create: `tests/test_startup_health.py`
- Modify: `startup_runtime.py`
- Test: `tests/test_startup_health.py`

**Step 1: Write the failing test**

```python
def test_build_health_report_marks_missing_tables_and_standard_entrypoint():
    report = build_health_report(...)
    assert report["entrypoint"] == "run.py"
    assert report["database"]["ok"] is False
    assert "stock_basic" in report["database"]["missing_tables"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_startup_health.py -q`
Expected: FAIL with missing function or missing keys

**Step 3: Write minimal implementation**

在 `startup_runtime.py` 中新增：
- 入口说明构建函数
- 数据库表检查函数
- 健康检查报告汇总函数

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_startup_health.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add startup_runtime.py tests/test_startup_health.py
git commit -m "feat: add startup health report contract"
```

### Task 2: 统一 run.py / run_system.py 角色

**Files:**
- Modify: `run.py`
- Modify: `run_system.py`
- Test: `tests/test_startup_runtime.py`
- Test: `tests/test_startup_health.py`

**Step 1: Write the failing test**

```python
def test_startup_report_explains_run_py_as_primary_entrypoint():
    lines = build_startup_report({...})
    assert any("主启动入口: python run.py" in line for line in lines)
    assert any("run_system.py 用于初始化/诊断" in line for line in lines)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_startup_runtime.py tests/test_startup_health.py -q`
Expected: FAIL because startup text is incomplete

**Step 3: Write minimal implementation**

更新 `run.py` / `run_system.py`：
- `run.py` 打印唯一标准入口说明和健康检查摘要
- `run_system.py` 打印“诊断/初始化工具”定位，不再与主入口抢角色

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_startup_runtime.py tests/test_startup_health.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add run.py run_system.py startup_runtime.py tests/test_startup_runtime.py tests/test_startup_health.py
git commit -m "fix: clarify startup entrypoint roles"
```

### Task 3: 补齐数据库初始化与关键表检查

**Files:**
- Create: `tests/test_system_manager_checks.py`
- Modify: `run_system.py`
- Modify: `startup_runtime.py`
- Test: `tests/test_system_manager_checks.py`

**Step 1: Write the failing test**

```python
def test_system_manager_reports_missing_required_tables(monkeypatch):
    manager = SystemManager()
    ...
    assert result["required_tables"]["missing"] == ["stock_basic", "stock_trade_calendar"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_system_manager_checks.py -q`
Expected: FAIL due to missing structured report/check method

**Step 3: Write minimal implementation**

在 `run_system.py` 中新增结构化检查：
- 数据库连通
- 关键表存在性
- 核心任务表存在性
- 数据任务执行模式说明

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_system_manager_checks.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add run_system.py startup_runtime.py tests/test_system_manager_checks.py
git commit -m "feat: add system manager health checks"
```

### Task 4: README 启动说明统一

**Files:**
- Modify: `README.md`
- Test: `tests/ui/test_readme_startup_contract.py`

**Step 1: Write the failing test**

```python
def test_readme_marks_run_py_as_primary_start_command():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "python run.py" in readme
    assert "run_system.py 用于初始化与诊断" in readme
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_readme_startup_contract.py -q`
Expected: FAIL because README still centers run_system.py

**Step 3: Write minimal implementation**

更新 README：
- 主启动方式改为 `python run.py`
- `run_system.py` 标注为初始化/诊断工具
- 端口、数据任务执行模式说明同步

**Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_readme_startup_contract.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md tests/ui/test_readme_startup_contract.py
git commit -m "docs: clarify startup workflow"
```

### Task 5: 为独立数据管理页准备迁移基座

**Files:**
- Create: `tests/ui/test_data_management_route_contract.py`
- Modify: `app/templates/base.html`
- Modify: `app/routes/realtime_analysis_routes.py`
- Modify: `app/main/views.py`
- Test: `tests/ui/test_data_management_route_contract.py`

**Step 1: Write the failing test**

```python
def test_navigation_exposes_data_management_as_separate_menu():
    html = Path("app/templates/base.html").read_text(encoding="utf-8")
    assert "数据管理" in html
    assert "/data-management" in html
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_data_management_route_contract.py -q`
Expected: FAIL because menu/route not present

**Step 3: Write minimal implementation**

先建立轻量基座：
- 新增 `/data-management` 入口
- 保留 `/realtime-analysis/data` 到新入口的兼容跳转
- 导航中新增独立“数据管理”菜单

**Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_data_management_route_contract.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add app/templates/base.html app/routes/realtime_analysis_routes.py app/main/views.py tests/ui/test_data_management_route_contract.py
git commit -m "feat: add data management route foundation"
```

### Task 6: 整体验证

**Files:**
- Verify only

**Step 1: Run focused tests**

Run:

```bash
pytest tests/test_startup_runtime.py tests/test_runtime_compat.py tests/test_startup_health.py tests/test_system_manager_checks.py tests/ui/test_readme_startup_contract.py tests/ui/test_data_management_route_contract.py tests/data_jobs/test_service_execution_mode.py -q
```

Expected: PASS

**Step 2: Run syntax validation**

Run:

```bash
python -m py_compile run.py run_system.py startup_runtime.py app/services/data_jobs/service.py app/routes/realtime_analysis_routes.py app/main/views.py
```

Expected: no output

**Step 3: Manual smoke**

Run:

```bash
python run.py
```

Expected:
- 输出主启动入口说明
- 输出健康检查摘要
- 开发环境可直接使用日频数据中心

**Step 4: Commit**

```bash
git add .
git commit -m "feat: stabilize startup and data management foundation"
```
