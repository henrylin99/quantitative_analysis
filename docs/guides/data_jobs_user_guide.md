# 日频数据中心使用指南

## 1. 功能入口
- 页面：`/realtime-analysis`
- 模块：`日频数据中心`

## 2. 启动依赖
1. 启动 Redis（默认 `localhost:6379`）
2. 启动 Flask 服务
3. 启动 Celery Worker：

```bash
celery -A app.celery_app.celery worker -l info
```

## 3. 页面操作流程
1. 在“任务类型”中选择数据任务
2. 选择开始/结束日期（可选）
3. 点击“启动任务”
4. 页面返回 `run_id` 后，可通过 API 查询状态

## 4. API 查询示例
```bash
# 提交任务
curl -X POST http://127.0.0.1:5001/api/data-jobs/submit \
  -H 'Content-Type: application/json' \
  -d '{"job_type":"stock_basic","params":{}}'

# 查询任务列表
curl http://127.0.0.1:5001/api/data-jobs/list
```

## 5. 全量重建说明
- 默认策略为增量更新。
- 全量重建需要显式开启，并建议仅管理员执行。

## 6. 常见问题
- `script not found`：检查 `app/utils` 下脚本是否存在。
- `ModuleNotFoundError: celery`：安装依赖 `pip install -r requirements.txt`。
- 任务未执行：确认 Celery Worker 是否正在运行。
