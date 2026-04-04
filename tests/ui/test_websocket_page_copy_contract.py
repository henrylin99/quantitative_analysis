from pathlib import Path


def test_websocket_page_marks_scope_as_current_entry():
    html = Path("app/templates/realtime_analysis/websocket_management.html").read_text(encoding="utf-8")

    assert "当前提供推送连接、订阅和状态查看入口，实际能力以后端当前实现为准" in html
    assert "实时数据推送服务管理和监控" not in html


def test_websocket_page_avoids_static_running_status_copy():
    html = Path("app/templates/realtime_analysis/websocket_management.html").read_text(encoding="utf-8")

    assert "等待状态更新" in html
    assert '<h4 id="pushStatus" class="text-success mb-1">停止</h4>' not in html
