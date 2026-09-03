from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app.api.text2sql_api import text2sql_bp
from app.extensions import db


def _build_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TESTING=True,
    )
    db.init_app(app)
    app.register_blueprint(text2sql_bp)
    return app


def test_create_query_template_uses_model_helper():
    app = _build_app()
    client = app.test_client()
    template = SimpleNamespace(
        to_dict=lambda: {
            "template_id": "t1",
            "template_name": "模板1",
            "intent_pattern": "pattern",
            "sql_template": "select 1",
            "parameters": {},
            "usage_count": 0,
            "is_active": True,
        }
    )

    with patch("app.api.text2sql_api.QueryTemplate.get_by_id", return_value=None), patch(
        "app.api.text2sql_api.QueryTemplate.create_template", return_value=template
    ) as create_template:
        response = client.post(
            "/api/text2sql/templates",
            json={
                "template_id": "t1",
                "template_name": "模板1",
                "sql_template": "select 1",
                "intent_pattern": "pattern",
            },
        )

    assert response.status_code == 200
    assert create_template.call_args.kwargs["template_id"] == "t1"
    assert create_template.call_args.kwargs["template_name"] == "模板1"


def test_update_query_template_passes_updated_fields():
    app = _build_app()
    client = app.test_client()
    existing = SimpleNamespace(template_name="旧模板", intent_pattern="old", sql_template="select 1", parameters={}, is_active=True)
    updated = SimpleNamespace(
        to_dict=lambda: {
            "template_id": "t1",
            "template_name": "新模板",
            "intent_pattern": "new",
            "sql_template": "select 2",
            "parameters": {"x": 1},
            "usage_count": 0,
            "is_active": False,
        }
    )

    with (
        patch("app.api.text2sql_api.QueryTemplate.get_by_id", return_value=existing),
        patch("app.api.text2sql_api.QueryTemplate.update_template_by_id", return_value=updated) as update_template,
    ):
        response = client.put(
            "/api/text2sql/templates/t1",
            json={
                "template_name": "新模板",
                "intent_pattern": "new",
                "sql_template": "select 2",
                "parameters": {"x": 1},
                "is_active": False,
            },
        )

    assert response.status_code == 200
    assert update_template.call_args.kwargs == {
        "template_name": "新模板",
        "intent_pattern": "new",
        "sql_template": "select 2",
        "parameters": {"x": 1},
        "is_active": False,
    }


def test_create_business_dictionary_uses_model_helper():
    app = _build_app()
    client = app.test_client()
    dictionary = SimpleNamespace(
        to_dict=lambda: {
            "id": 1,
            "category": "tech",
            "standard_term": "市盈率",
            "synonyms": ["PE"],
            "description": "desc",
            "mapping_field": "pe",
            "mapping_table": "stock_basic",
            "is_active": True,
        }
    )

    with patch("app.api.text2sql_api.BusinessDictionary.create_dictionary", return_value=dictionary) as create_dictionary:
        response = client.post(
            "/api/text2sql/dictionary",
            json={
                "category": "tech",
                "standard_term": "市盈率",
                "synonyms": ["PE"],
                "description": "desc",
                "mapping_field": "pe",
                "mapping_table": "stock_basic",
            },
        )

    assert response.status_code == 200
    assert create_dictionary.call_args.kwargs["standard_term"] == "市盈率"
