from pathlib import Path


def test_navigation_exposes_feature_intro_as_first_trial_item():
    """「试用功能」下拉的第 1 项应为「功能介绍」。"""
    html = Path("app/templates/base.html").read_text(encoding="utf-8")

    assert "url_for('main.feature_intro')" in html
    assert "功能介绍" in html
    # 功能介绍 必须排在 板块热力图 之前（下拉第 1 位）
    assert html.index("功能介绍") < html.index("板块热力图")


def test_feature_intro_route_shows_plain_language_intro(app):
    """GET /trial/feature-intro 返回通俗易懂的大宽表介绍页面。"""
    client = app.test_client()
    response = client.get("/trial/feature-intro")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "大宽表" in html  # 页面主题
    assert "市盈率" in html  # 通俗字段举例
    assert "均线金叉" in html  # 形态举例
    assert "使用小提示" in html  # 面向普通用户的注意事项
