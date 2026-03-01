# Data Download UI Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 `realtime-analysis` 页面提供 `app/utils` 全量数据任务的可视化异步执行能力（提交、进度、日志、历史、重试），默认增量更新并支持受控全量重建。

**Architecture:** 采用“页面 + API + 任务服务 + Worker”四层结构。API 只做参数校验与任务编排，实际执行由异步 Worker 完成。通过统一任务注册表和状态持久化模型，把脚本能力包装为可管理任务，并复用现有 `realtime_analysis/index.html` 的同步交互样式。

**Tech Stack:** Flask, SQLAlchemy, Redis, Celery, PyMySQL, Tushare/Baostock, pytest

---

### Task 1: 建立数据任务模块骨架与测试基线

**Files:**
- Create: `app/services/data_jobs/__init__.py`
- Create: `app/services/data_jobs/schemas.py`
- Create: `tests/data_jobs/test_schemas.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`

**Step 1: Write the failing test**

```python
# tests/data_jobs/test_schemas.py
from app.services.data_jobs.schemas import JobSubmitRequest


def test_job_submit_request_defaults():
    req = JobSubmitRequest(job_type="stock_basic")
    assert req.job_type == "stock_basic"
    assert req.full_refresh is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/data_jobs/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.data_jobs'`

**Step 3: Write minimal implementation**

```python
# app/services/data_jobs/schemas.py
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class JobSubmitRequest:
    job_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    full_refresh: bool = False
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/data_jobs/test_schemas.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pytest.ini tests/conftest.py tests/data_jobs/test_schemas.py app/services/data_jobs/__init__.py app/services/data_jobs/schemas.py
git commit -m "test: bootstrap data jobs schema tests"
```

### Task 2: 实现任务注册表（覆盖 app/utils 全量任务）

**Files:**
- Create: `app/services/data_jobs/registry.py`
- Modify: `app/services/data_jobs/schemas.py`
- Test: `tests/data_jobs/test_registry.py`

**Step 1: Write the failing test**

```python
# tests/data_jobs/test_registry.py
from app.services.data_jobs.registry import JobRegistry


def test_registry_contains_all_utils_jobs():
    registry = JobRegistry()
    jobs = registry.list_jobs()
    assert len(jobs) >= 18
    assert "stock_basic" in {job.job_type for job in jobs}
    assert "min60" in {job.job_type for job in jobs}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/data_jobs/test_registry.py -v`
Expected: FAIL with `ImportError` or assertion failure

**Step 3: Write minimal implementation**

```python
# app/services/data_jobs/registry.py
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class JobDefinition:
    job_type: str
    group: str
    script_path: str
    dangerous: bool = False
    dependencies: List[str] = field(default_factory=list)


class JobRegistry:
    def __init__(self):
        self._jobs: Dict[str, JobDefinition] = {
            "stock_basic": JobDefinition("stock_basic", "基础资料", "app/utils/stock_basic.py"),
            "trade_calendar": JobDefinition("trade_calendar", "基础资料", "app/utils/trade_calendar.py"),
            "stock_company": JobDefinition("stock_company", "基础资料", "app/utils/stock_company.py"),
            # ...补齐 app/utils 全量任务
        }

    def list_jobs(self):
        return list(self._jobs.values())
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/data_jobs/test_registry.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/data_jobs/registry.py app/services/data_jobs/schemas.py tests/data_jobs/test_registry.py
git commit -m "feat: add data job registry for utils tasks"
```

### Task 3: 新增任务状态模型与迁移脚本

**Files:**
- Create: `app/models/data_job_run.py`
- Create: `app/models/data_job_cursor.py`
- Modify: `app/models/__init__.py`
- Create: `migrations/versions/20260301_add_data_job_tables.sql`
- Test: `tests/data_jobs/test_models.py`

**Step 1: Write the failing test**

```python
# tests/data_jobs/test_models.py
from app.models.data_job_run import DataJobRun


def test_data_job_run_has_status_field():
    assert hasattr(DataJobRun, "status")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/data_jobs/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# app/models/data_job_run.py
from app.extensions import db
from datetime import datetime


class DataJobRun(db.Model):
    __tablename__ = "data_job_run"
    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    job_type = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="pending")
    progress = db.Column(db.Float, nullable=False, default=0.0)
    params_json = db.Column(db.JSON, nullable=False)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/data_jobs/test_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/models/data_job_run.py app/models/data_job_cursor.py app/models/__init__.py migrations/versions/20260301_add_data_job_tables.sql tests/data_jobs/test_models.py
git commit -m "feat: add data job run and cursor models"
```

### Task 4: 实现任务状态存储层（StateStore）

**Files:**
- Create: `app/services/data_jobs/state_store.py`
- Test: `tests/data_jobs/test_state_store.py`

**Step 1: Write the failing test**

```python
# tests/data_jobs/test_state_store.py
from app.services.data_jobs.state_store import DataJobStateStore


def test_create_run_sets_pending_status(db_session):
    store = DataJobStateStore(db_session)
    run = store.create_run("stock_basic", {"start_date": "20250101"})
    assert run.status == "pending"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/data_jobs/test_state_store.py -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

```python
# app/services/data_jobs/state_store.py
class DataJobStateStore:
    def __init__(self, session):
        self.session = session

    def create_run(self, job_type, params):
        run = DataJobRun(job_type=job_type, params_json=params, status="pending")
        self.session.add(run)
        self.session.commit()
        return run
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/data_jobs/test_state_store.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/data_jobs/state_store.py tests/data_jobs/test_state_store.py
git commit -m "feat: add data job state store"
```

### Task 5: 实现脚本执行适配器（Runner Adapter）

**Files:**
- Create: `app/services/data_jobs/runner.py`
- Create: `app/services/data_jobs/execution_context.py`
- Test: `tests/data_jobs/test_runner.py`

**Step 1: Write the failing test**

```python
# tests/data_jobs/test_runner.py
from app.services.data_jobs.runner import ScriptRunner


def test_runner_rejects_unknown_script():
    runner = ScriptRunner()
    ok, msg = runner.validate_script("app/utils/not_exists.py")
    assert ok is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/data_jobs/test_runner.py -v`
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

```python
# app/services/data_jobs/runner.py
from pathlib import Path


class ScriptRunner:
    def validate_script(self, script_path: str):
        p = Path(script_path)
        if not p.exists():
            return False, f"script not found: {script_path}"
        return True, "ok"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/data_jobs/test_runner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/data_jobs/runner.py app/services/data_jobs/execution_context.py tests/data_jobs/test_runner.py
git commit -m "feat: add script runner adapter for data jobs"
```

### Task 6: 接入异步队列（Celery Worker）

**Files:**
- Create: `app/celery_app.py`
- Create: `app/tasks/data_jobs_tasks.py`
- Modify: `config.py`
- Modify: `requirements.txt`
- Test: `tests/data_jobs/test_celery_tasks.py`

**Step 1: Write the failing test**

```python
# tests/data_jobs/test_celery_tasks.py
from app.tasks.data_jobs_tasks import run_data_job


def test_run_data_job_task_exists():
    assert callable(run_data_job)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/data_jobs/test_celery_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# app/tasks/data_jobs_tasks.py
from app.celery_app import celery


@celery.task(name="data_jobs.run")
def run_data_job(run_id: int):
    return {"run_id": run_id, "status": "queued"}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/data_jobs/test_celery_tasks.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/celery_app.py app/tasks/data_jobs_tasks.py config.py requirements.txt tests/data_jobs/test_celery_tasks.py
git commit -m "feat: add celery worker for data jobs"
```

### Task 7: 实现任务编排服务（提交/查询/取消/重试）

**Files:**
- Create: `app/services/data_jobs/service.py`
- Modify: `app/services/data_jobs/registry.py`
- Modify: `app/services/data_jobs/state_store.py`
- Test: `tests/data_jobs/test_service.py`

**Step 1: Write the failing test**

```python
# tests/data_jobs/test_service.py

def test_submit_creates_run_and_dispatches_task(mocker, service):
    delay = mocker.patch("app.tasks.data_jobs_tasks.run_data_job.delay")
    run = service.submit("stock_basic", {})
    delay.assert_called_once_with(run.id)
    assert run.status in {"pending", "queued"}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/data_jobs/test_service.py -v`
Expected: FAIL with attribute/method missing

**Step 3: Write minimal implementation**

```python
# app/services/data_jobs/service.py
class DataJobService:
    def __init__(self, registry, store):
        self.registry = registry
        self.store = store

    def submit(self, job_type, params):
        run = self.store.create_run(job_type, params)
        run_data_job.delay(run.id)
        return run
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/data_jobs/test_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/data_jobs/service.py app/services/data_jobs/registry.py app/services/data_jobs/state_store.py tests/data_jobs/test_service.py
git commit -m "feat: add data job orchestration service"
```

### Task 8: 提供 API 接口并注册蓝图

**Files:**
- Create: `app/api/data_jobs_api.py`
- Modify: `app/__init__.py`
- Test: `tests/api/test_data_jobs_api.py`

**Step 1: Write the failing test**

```python
# tests/api/test_data_jobs_api.py

def test_submit_endpoint_returns_job_id(client):
    resp = client.post("/api/data-jobs/submit", json={"job_type": "stock_basic"})
    assert resp.status_code == 200
    assert "run_id" in resp.get_json()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_data_jobs_api.py -v`
Expected: FAIL with `404`

**Step 3: Write minimal implementation**

```python
# app/api/data_jobs_api.py
from flask import Blueprint, request, jsonify


data_jobs_bp = Blueprint("data_jobs", __name__, url_prefix="/api/data-jobs")


@data_jobs_bp.route("/submit", methods=["POST"])
def submit_job():
    data = request.get_json() or {}
    return jsonify({"success": True, "run_id": 1, "job_type": data.get("job_type")})
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_data_jobs_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/api/data_jobs_api.py app/__init__.py tests/api/test_data_jobs_api.py
git commit -m "feat: add data jobs api endpoints"
```

### Task 9: 扩展 realtime-analysis 页面（数据中心UI）

**Files:**
- Modify: `app/templates/realtime_analysis/index.html`
- Create: `app/static/js/data_jobs.js`
- Test: `tests/ui/test_data_jobs_ui_contract.py`

**Step 1: Write the failing test**

```python
# tests/ui/test_data_jobs_ui_contract.py
from pathlib import Path


def test_realtime_page_contains_data_jobs_entry():
    html = Path("app/templates/realtime_analysis/index.html").read_text(encoding="utf-8")
    assert "日频数据中心" in html
    assert "data-jobs-panel" in html
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/ui/test_data_jobs_ui_contract.py -v`
Expected: FAIL with string not found

**Step 3: Write minimal implementation**

```html
<!-- app/templates/realtime_analysis/index.html -->
<div id="data-jobs-panel" class="card mt-4">
  <div class="card-header">日频数据中心</div>
  <div class="card-body">
    <button id="submitStockBasicJob" class="btn btn-primary">下载 stock_basic</button>
  </div>
</div>
<script src="{{ url_for('static', filename='js/data_jobs.js') }}"></script>
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/ui/test_data_jobs_ui_contract.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/templates/realtime_analysis/index.html app/static/js/data_jobs.js tests/ui/test_data_jobs_ui_contract.py
git commit -m "feat: add realtime data jobs center ui"
```

### Task 10: 完成端到端联调与文档

**Files:**
- Create: `docs/guides/data_jobs_user_guide.md`
- Modify: `README.md`
- Modify: `.env.example`
- Create: `scripts/validation/validate_data_jobs_flow.sh`

**Step 1: Write the failing test/check**

```bash
# validate_data_jobs_flow.sh
curl -sS http://127.0.0.1:5001/api/data-jobs/list | jq '.success'
```

**Step 2: Run check to verify it fails**

Run: `bash scripts/validation/validate_data_jobs_flow.sh`
Expected: FAIL (接口未完整返回或服务未启动)

**Step 3: Write minimal implementation**

```markdown
# docs/guides/data_jobs_user_guide.md
- 如何启动 Redis/Celery
- 如何在页面提交任务
- 如何查看日志与重试
- 如何执行全量重建确认
```

**Step 4: Run checks to verify pass**

Run: `pytest tests/data_jobs tests/api/test_data_jobs_api.py tests/ui/test_data_jobs_ui_contract.py -v`
Expected: PASS

Run: `bash scripts/validation/validate_data_jobs_flow.sh`
Expected: PASS with `true`

**Step 5: Commit**

```bash
git add docs/guides/data_jobs_user_guide.md README.md .env.example scripts/validation/validate_data_jobs_flow.sh
git commit -m "docs: add data jobs runbook and validation script"
```

## 执行顺序与检查点
1. Task 1-3 完成后，先验收“任务元数据 + 状态模型”是否可用。
2. Task 4-7 完成后，先验收“提交任务 -> 入队 -> 状态可查”。
3. Task 8-9 完成后，执行页面联调验收。
4. Task 10 完成后，执行全量回归与文档检查。

## 验收命令集合
- `pytest tests/data_jobs -v`
- `pytest tests/api/test_data_jobs_api.py -v`
- `pytest tests/ui/test_data_jobs_ui_contract.py -v`
- `bash scripts/validation/validate_data_jobs_flow.sh`

## 外部依赖与环境准备
- Redis 服务可用（默认 `localhost:6379`）。
- MySQL 已就绪（`localhost:3306`, `root/root`, `stock_cursor`）。
- `.env` 提供 `TUSHARE_TOKEN`（已确认存在）。
- Worker 启动命令（建议）：`celery -A app.celery_app.celery worker -l info`。

