"""ML 训练防泄漏与预测健壮性的回归测试。

覆盖 2026-08 修复的问题:
- scaler/特征选择只在训练集上 fit（泄漏会让测试指标虚高）
- 预处理器不再挂在全局 manager 实例上（并发训练互踩）
- 预测缺因子返回空而不是填 0
"""
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import RobustScaler

from app.services.ml_models import MLModelManager

pytestmark = pytest.mark.module_ml_model


def _make_manager(tmp_path, model_type="random_forest"):
    manager = MLModelManager()
    manager.model_dir = str(tmp_path)
    # 定义一个训练极快的随机森林
    manager.model_configs = {
        "random_forest": {
            "regressor": manager.model_configs["random_forest"]["regressor"],
            "classifier": manager.model_configs["random_forest"]["classifier"],
            "default_params": {"n_estimators": 5, "max_depth": 2, "random_state": 42},
        }
    }
    return manager


def _patch_definition(manager, factor_list=("f1",)):
    return patch.object(
        manager,
        "_get_model_definition",
        return_value={
            "model_id": "m1",
            "model_type": "random_forest",
            "model_params": {},
            "factor_list": list(factor_list),
            "training_config": {
                "test_size": 0.5,
                "scaling_method": "robust",
                "feature_selection": False,
                "validation_method": None,
            },
        },
    )


def test_preprocessor_not_stored_on_manager_instance(tmp_path):
    manager = _make_manager(tmp_path)
    preprocessor = manager._build_preprocessor({"scaling_method": "robust"}, 3)
    assert preprocessor is not None
    # 返回的是未 fit 的 Pipeline，且不在实例上留任何拟合状态
    assert not hasattr(manager, "_scaler")
    scaler = preprocessor.named_steps["scaler"]
    with pytest.raises(Exception):
        scaler.transform(np.array([[1.0, 2.0, 3.0]]))


def test_scaler_fit_on_train_portion_only(tmp_path):
    """测试集数值分布剧烈偏移时，scaler 统计量必须只反映训练集。"""
    manager = _make_manager(tmp_path)
    n = 40
    # 训练段 f1 全在 10 附近，测试段（后一半, 时间序切分）全在 10000 附近
    values = [10.0] * (n // 2) + [10000.0] * (n // 2)
    X = pd.DataFrame({"f1": values})
    y = pd.Series([0.0] * n)

    with _patch_definition(manager), patch.object(
        manager,
        "prepare_training_data",
        return_value=(X, y, pd.Series(pd.to_datetime(["2026-01-01"] * len(y)))),
    ):
        result = manager.train_model("m1", "2026-01-01", "2026-12-31")
    assert result["success"], result.get("error")

    fitted = manager.scalers["m1"].named_steps["scaler"]
    train_only = RobustScaler().fit(X[["f1"]].iloc[: n // 2])
    # 若泄漏，center 会被拉向 ~5000；只 fit 训练集时应为 ~10
    assert fitted.center_[0] == pytest.approx(train_only.center_[0])
    assert abs(fitted.center_[0] - 10.0) < 1.0


def test_feature_selection_applied_consistently_at_predict(tmp_path):
    """训练时做了特征选择，预测必须用同一个选择器（列一致），否则模型形状不匹配。"""
    manager = _make_manager(tmp_path)
    n = 40
    X = pd.DataFrame(
        {
            "f_signal": [float(i % 7) for i in range(n)],  # 与 y 相关
            "f_noise": [float(i * 1000) for i in range(n)],
        }
    )
    y = pd.Series([float(i % 7) for i in range(n)])

    with patch.object(
        manager,
        "_get_model_definition",
        return_value={
            "model_id": "m1",
            "model_type": "random_forest",
            "model_params": {},
            "factor_list": ["f_signal", "f_noise"],
            "training_config": {
                "test_size": 0.5,
                "scaling_method": "robust",
                "feature_selection": True,
                "feature_selection_k": 1,
                "validation_method": None,
            },
        },
    ), patch.object(
        manager,
        "prepare_training_data",
        return_value=(X, y, pd.Series(pd.to_datetime(["2026-06-01"] * len(y)))),
    ):
        result = manager.train_model("m1", "2026-01-01", "2026-12-31")
    assert result["success"], result.get("error")
    # 训练只保留了 1 个特征
    assert result["metrics"]["feature_count"] == 1
    # 预测时缺 f_noise 列 → 因子不全，应返回空（不再填 0）
    factor_data = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 3,
            "trade_date": ["2026-06-01"] * 3,
            "factor_id": ["f_signal"] * 3,
            "factor_value": [1.0, 2.0, 3.0],
        }
    )
    manager.factor_repo = MagicMock()
    manager.factor_repo.get_values.return_value = factor_data
    with patch.object(manager, "load_model", return_value=True), _patch_definition(
        manager, factor_list=("f_signal", "f_noise")
    ):
        predictions = manager.predict("m1", "2026-06-01")
    assert predictions.empty


def test_predict_probability_score_handles_flat_predictions(tmp_path):
    manager = _make_manager(tmp_path)
    factor_data = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "trade_date": ["2026-06-01"] * 2,
            "factor_id": ["f1"] * 2,
            "factor_value": [5.0, 5.0],
        }
    )
    manager.models = {
        "m1": MagicMock(predict=MagicMock(return_value=np.array([0.5, 0.5])))
    }
    manager.scalers = {}
    manager.factor_repo = MagicMock()
    manager.factor_repo.get_values.return_value = factor_data
    with patch.object(manager, "load_model", return_value=True), _patch_definition(manager):
        predictions = manager.predict("m1", "2026-06-01")
    assert not predictions.empty
    assert (predictions["probability_score"] == 0.5).all()
    assert not predictions["probability_score"].isna().any()
