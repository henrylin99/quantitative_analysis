from pathlib import Path


def test_data_jobs_guide_uses_current_behavior_wording():
    guide = Path("docs/guides/data_jobs_user_guide.md").read_text(encoding="utf-8")

    assert "支持轮询任务状态与进度展示" in guide
    assert "增量或全量行为以后端当前任务实现为准" in guide
    assert "支持轮询运行中任务状态与进度" not in guide
    assert "默认策略为增量更新" not in guide
