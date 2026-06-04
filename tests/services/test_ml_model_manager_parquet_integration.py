from pathlib import Path

import pandas as pd

from app.services.ml_models import MLModelManager
from app.services.parquet_state_store import ParquetStateStore


def _write_daily_history(data_dir, ts_code="000001.SZ", days=12):
    rows = []
    for i in range(days):
        dt = pd.Timestamp("2024-06-01") + pd.Timedelta(days=i)
        close = 10.0 + i * 0.5
        rows.append(
            {
                "ts_code": ts_code,
                "trade_date": dt.strftime("%Y-%m-%d"),
                "open": close - 0.1,
                "high": close + 0.2,
                "low": close - 0.3,
                "close": close,
                "pre_close": close - 0.5 if i else close,
                "change": 0.5 if i else 0,
                "pct_chg": 5.0 if i else 0,
                "vol": 100000 + i,
                "amount": 1000000 + i,
            }
        )

    partition_dir = data_dir / "daily_history" / "daily" / "year=2024" / "month=06" / "day=12"
    partition_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(partition_dir / "data.parquet", index=False)


def _write_factor_values(manager, ts_code="000001.SZ", days=12):
    rows = []
    for i in range(days):
        dt = pd.Timestamp("2024-06-01") + pd.Timedelta(days=i)
        rows.append(
            {
                "ts_code": ts_code,
                "trade_date": dt.strftime("%Y-%m-%d"),
                "factor_id": "factor_a",
                "factor_value": float(i),
            }
        )
    manager.factor_repo.save_values(pd.DataFrame(rows))


def test_ml_model_manager_persists_and_lists_model_definitions(tmp_path):
    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))

    assert manager.create_model_definition(
        model_id="model_a",
        model_name="模型A",
        model_type="random_forest",
        factor_list=["factor_a", "factor_b"],
        target_type="return_5d",
    )

    models = manager.get_model_list()
    assert len(models) == 1
    assert models[0]["model_id"] == "model_a"
    assert models[0]["factor_list"] == ["factor_a", "factor_b"]


def test_ml_model_manager_prepare_training_data_uses_parquet_factor_store(tmp_path, monkeypatch):
    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.create_model_definition(
        model_id="model_a",
        model_name="模型A",
        model_type="random_forest",
        factor_list=["factor_a", "factor_b"],
        target_type="return_5d",
    )

    manager.factor_repo.save_values(
        pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "factor_a", "factor_value": 1.0},
                {"ts_code": "000001.SZ", "trade_date": "2024-06-04", "factor_id": "factor_b", "factor_value": 2.0},
                {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "factor_id": "factor_a", "factor_value": 3.0},
                {"ts_code": "000002.SZ", "trade_date": "2024-06-04", "factor_id": "factor_b", "factor_value": 4.0},
            ]
        )
    )

    monkeypatch.setattr(
        manager,
        "_calculate_target_returns",
        lambda feature_df, target_type: pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000002.SZ"],
                "trade_date": pd.to_datetime(["2024-06-04", "2024-06-04"]),
                "target": [0.1, 0.2],
            }
        ),
    )

    X, y = manager.prepare_training_data("model_a", "2024-06-04", "2024-06-04")
    assert list(X.columns) == ["factor_a", "factor_b"]
    assert y.tolist() == [0.1, 0.2]


def test_ml_model_manager_saves_predictions_and_deletes_model_state(tmp_path):
    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.create_model_definition(
        model_id="model_a",
        model_name="模型A",
        model_type="random_forest",
        factor_list=["factor_a"],
        target_type="return_5d",
    )

    predictions = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "2024-06-04",
                "model_id": "model_a",
                "predicted_return": 0.2,
                "probability_score": 0.6,
                "rank_score": 1,
            },
            {
                "ts_code": "000002.SZ",
                "trade_date": "2024-06-04",
                "model_id": "model_a",
                "predicted_return": 0.1,
                "probability_score": 0.4,
                "rank_score": 2,
            },
        ]
    )

    assert manager.save_predictions(predictions)
    saved = manager.model_repo.get_predictions(model_id="model_a", trade_date="2024-06-04")
    assert saved["ts_code"].tolist() == ["000001.SZ", "000002.SZ"]

    result = manager.delete_model("model_a")
    assert result["success"] is True
    assert manager.model_repo.get_definition("model_a")["is_active"] is False
    assert manager.model_repo.get_predictions(model_id="model_a").empty


def test_ml_model_manager_returns_model_detail(tmp_path):
    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.create_model_definition(
        model_id="model_a",
        model_name="模型A",
        model_type="random_forest",
        factor_list=["factor_a", "factor_b"],
        target_type="return_5d",
        training_config={"test_size": 0.2, "validation_method": "none"},
    )
    manager.model_repo.save_predictions(
        pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "2024-06-04",
                    "model_id": "model_a",
                    "predicted_return": 0.2,
                    "probability_score": 0.8,
                    "rank_score": 1,
                },
                {
                    "ts_code": "000002.SZ",
                    "trade_date": "2024-06-04",
                    "model_id": "model_a",
                    "predicted_return": 0.1,
                    "probability_score": 0.2,
                    "rank_score": 2,
                },
            ]
        )
    )

    detail = manager.get_model_detail("model_a")

    assert detail["model_id"] == "model_a"
    assert detail["factor_list"] == ["factor_a", "factor_b"]
    assert detail["prediction_summary"]["total_predictions"] == 2
    assert detail["prediction_summary"]["latest_trade_date"] == "2024-06-04"
    assert len(detail["recent_predictions"]) == 2


def test_ml_model_manager_can_train_a_minimal_parquet_model(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.model_dir = str(tmp_path / "models")
    Path(manager.model_dir).mkdir(parents=True, exist_ok=True)

    _write_daily_history(data_dir)
    manager.create_model_definition(
        model_id="model_minimal",
        model_name="最小模型",
        model_type="random_forest",
        factor_list=["factor_a"],
        target_type="return_1d",
        training_config={
            "test_size": 0.2,
            "validation_method": "none",
            "feature_selection": False,
            "scaling_method": "robust",
        },
    )
    _write_factor_values(manager)

    X, y = manager.prepare_training_data("model_minimal", "2024-06-01", "2024-06-12")
    assert len(X) > 0
    assert len(y) > 0

    result = manager.train_model("model_minimal", "2024-06-01", "2024-06-12")

    assert result["success"] is True
    assert result["metrics"]["sample_count"] == len(X)
    assert (Path(manager.model_dir) / "model_minimal.pkl").is_file()


def test_target_return_calculation_reads_only_required_daily_window(monkeypatch):
    calls = []

    class CapturingReader:
        def get_daily(self, ts_codes=None, start_date=None, end_date=None):
            calls.append(
                {
                    "ts_codes": ts_codes,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
            return pd.DataFrame(
                [
                    {"ts_code": "000001.SZ", "trade_date": "2024-06-10", "close": 10.0},
                    {"ts_code": "000001.SZ", "trade_date": "2024-06-11", "close": 11.0},
                    {"ts_code": "000002.SZ", "trade_date": "2024-06-11", "close": 20.0},
                    {"ts_code": "000002.SZ", "trade_date": "2024-06-12", "close": 22.0},
                ]
            )

    monkeypatch.setattr("app.services.ml_models.ParquetDataReader", CapturingReader)

    manager = MLModelManager()
    feature_df = pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "trade_date": "2024-06-10", "factor_a": 1.0},
            {"ts_code": "000002.SZ", "trade_date": "2024-06-11", "factor_a": 2.0},
        ]
    )

    target_df = manager._calculate_target_returns(feature_df, "return_1d")

    assert calls == [
        {
            "ts_codes": ["000001.SZ", "000002.SZ"],
            "start_date": "2024-06-10",
            "end_date": "2024-06-22",
        }
    ]
    assert target_df[["ts_code", "target"]].to_dict("records") == [
        {"ts_code": "000001.SZ", "target": 0.1},
        {"ts_code": "000002.SZ", "target": 0.1},
    ]


def test_training_date_range_rolls_back_to_latest_date_with_future_prices(tmp_path, monkeypatch):
    class CalendarReader:
        def get_trade_dates(self, start_date=None, end_date=None):
            return ["2024-06-10", "2024-06-11"]

    monkeypatch.setattr("app.services.ml_models.ParquetDataReader", CalendarReader)

    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.create_model_definition(
        model_id="model_a",
        model_name="模型A",
        model_type="random_forest",
        factor_list=["factor_a"],
        target_type="return_1d",
    )
    manager.factor_repo.save_values(
        pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-10", "factor_id": "factor_a", "factor_value": 1.0},
                {"ts_code": "000001.SZ", "trade_date": "2024-06-11", "factor_id": "factor_a", "factor_value": 2.0},
            ]
        )
    )

    resolved = manager.resolve_training_date_range("model_a", "2024-06-10", "2024-06-11")

    assert resolved["start_date"] == "2024-06-10"
    assert resolved["end_date"] == "2024-06-10"
    assert resolved["adjusted"] is True


def test_training_date_range_uses_latest_trainable_date_when_requested_range_has_no_factors(tmp_path, monkeypatch):
    class CalendarReader:
        def get_trade_dates(self, start_date=None, end_date=None):
            return ["2024-06-10", "2024-06-11"]

    monkeypatch.setattr("app.services.ml_models.ParquetDataReader", CalendarReader)

    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.create_model_definition(
        model_id="model_a",
        model_name="模型A",
        model_type="random_forest",
        factor_list=["factor_a"],
        target_type="return_1d",
    )
    manager.factor_repo.save_values(
        pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-10", "factor_id": "factor_a", "factor_value": 1.0},
                {"ts_code": "000001.SZ", "trade_date": "2024-06-11", "factor_id": "factor_a", "factor_value": 2.0},
            ]
        )
    )

    resolved = manager.resolve_training_date_range("model_a", "2023-01-01", "2024-01-01")

    assert resolved["start_date"] == "2024-06-10"
    assert resolved["end_date"] == "2024-06-10"
    assert resolved["requested_start_date"] == "2023-01-01"
    assert resolved["requested_end_date"] == "2024-01-01"
    assert resolved["adjusted"] is True


def test_training_date_range_rolls_back_when_requested_latest_date_has_no_future_price(tmp_path, monkeypatch):
    class CalendarReader:
        def get_trade_dates(self, start_date=None, end_date=None):
            return ["2024-06-10", "2024-06-11"]

    monkeypatch.setattr("app.services.ml_models.ParquetDataReader", CalendarReader)

    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.create_model_definition(
        model_id="model_a",
        model_name="模型A",
        model_type="random_forest",
        factor_list=["factor_a"],
        target_type="return_1d",
    )
    manager.factor_repo.save_values(
        pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-10", "factor_id": "factor_a", "factor_value": 1.0},
                {"ts_code": "000001.SZ", "trade_date": "2024-06-11", "factor_id": "factor_a", "factor_value": 2.0},
            ]
        )
    )

    resolved = manager.resolve_training_date_range("model_a", "2024-06-11", "2024-06-11")

    assert resolved["start_date"] == "2024-06-10"
    assert resolved["end_date"] == "2024-06-10"
    assert resolved["requested_start_date"] == "2024-06-11"
    assert resolved["requested_end_date"] == "2024-06-11"
    assert resolved["adjusted"] is True


def test_suggest_training_date_range_uses_latest_trainable_factor_date(tmp_path, monkeypatch):
    class CalendarReader:
        def get_trade_dates(self, start_date=None, end_date=None):
            return ["2024-06-10", "2024-06-11", "2024-06-12"]

    monkeypatch.setattr("app.services.ml_models.ParquetDataReader", CalendarReader)

    manager = MLModelManager(state_store=ParquetStateStore(base_dir=str(tmp_path / "state")))
    manager.create_model_definition(
        model_id="model_a",
        model_name="模型A",
        model_type="random_forest",
        factor_list=["factor_a"],
        target_type="return_1d",
    )
    manager.factor_repo.save_values(
        pd.DataFrame(
            [
                {"ts_code": "000001.SZ", "trade_date": "2024-06-10", "factor_id": "factor_a", "factor_value": 1.0},
                {"ts_code": "000001.SZ", "trade_date": "2024-06-11", "factor_id": "factor_a", "factor_value": 2.0},
                {"ts_code": "000001.SZ", "trade_date": "2024-06-12", "factor_id": "factor_a", "factor_value": 3.0},
            ]
        )
    )

    suggestion = manager.suggest_training_date_range("model_a")

    assert suggestion["start_date"] == "2024-06-11"
    assert suggestion["end_date"] == "2024-06-11"
    assert suggestion["target_period"] == 1
