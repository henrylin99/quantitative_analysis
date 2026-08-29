"""factor_compute 退出码合约：零产出/全失败必须退出码 1，不能假成功。"""
import pandas as pd
import pytest

from app.utils import factor_compute


class _FakeEngine:
    def __init__(self, behaviors):
        self._behaviors = behaviors
        self.saved = []

    def calculate_factor(self, factor_id, ts_codes, start_date, end_date):
        behavior = self._behaviors[factor_id]
        if isinstance(behavior, Exception):
            raise behavior
        return behavior

    def save_factor_values(self, result):
        self.saved.append(result)
        return len(result)


@pytest.fixture(autouse=True)
def _single_trade_date(monkeypatch):
    monkeypatch.setenv("DATA_JOB_TRADE_DATE", "20260601")
    monkeypatch.delenv("DATA_JOB_START_DATE", raising=False)
    monkeypatch.delenv("DATA_JOB_END_DATE", raising=False)
    monkeypatch.delenv("DATA_JOB_PARAM_FACTOR_IDS", raising=False)
    monkeypatch.delenv("DATA_JOB_PARAM_TS_CODES", raising=False)


def test_all_factors_fail_exits_nonzero(monkeypatch):
    monkeypatch.setenv("DATA_JOB_PARAM_FACTOR_IDS", "bad_a,bad_b")
    engine = _FakeEngine({"bad_a": RuntimeError("上游缺失"), "bad_b": RuntimeError("上游缺失")})
    monkeypatch.setattr(factor_compute, "FactorEngine", lambda: engine)

    with pytest.raises(SystemExit) as excinfo:
        factor_compute.main()

    assert excinfo.value.code == 1


def test_zero_output_exits_nonzero(monkeypatch):
    """接口不报错但全是空结果（上游数据缺失的典型表现）同样不能记成功。"""
    monkeypatch.setenv("DATA_JOB_PARAM_FACTOR_IDS", "empty_a,empty_b")
    engine = _FakeEngine({"empty_a": pd.DataFrame(), "empty_b": pd.DataFrame()})
    monkeypatch.setattr(factor_compute, "FactorEngine", lambda: engine)

    with pytest.raises(SystemExit) as excinfo:
        factor_compute.main()

    assert excinfo.value.code == 1


def test_partial_failure_still_succeeds(monkeypatch):
    """个别自定义因子坏了不应阻断整体：缺失值由回测覆盖率校验兜底。"""
    good = pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "2026-06-01", "factor_id": "good", "factor_value": 1.0}])
    monkeypatch.setenv("DATA_JOB_PARAM_FACTOR_IDS", "good,bad")
    engine = _FakeEngine({"good": good, "bad": RuntimeError("表达式错误")})
    monkeypatch.setattr(factor_compute, "FactorEngine", lambda: engine)

    factor_compute.main()  # 不抛 SystemExit

    assert len(engine.saved) == 1


def test_full_success_saves_everything(monkeypatch):
    good_a = pd.DataFrame([{"ts_code": "000001.SZ", "factor_id": "a", "factor_value": 1.0}])
    good_b = pd.DataFrame([{"ts_code": "000001.SZ", "factor_id": "b", "factor_value": 2.0}])
    monkeypatch.setenv("DATA_JOB_PARAM_FACTOR_IDS", "a,b")
    engine = _FakeEngine({"a": good_a, "b": good_b})
    monkeypatch.setattr(factor_compute, "FactorEngine", lambda: engine)

    factor_compute.main()

    assert len(engine.saved) == 2
