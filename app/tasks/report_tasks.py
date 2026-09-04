"""报告订阅派发任务注册。

当前无 beat 调度方：app/api/realtime_report.py 直接调用 service 层派发。
保留模块以维持 `app.tasks` 注册表结构，后续接定时调度时在此挂任务。
"""
