"""因子体检（批量扫描/生命周期/去冗余）与数据质量监控的测试。"""
import numpy as np
import pandas as pd
import pytest

from app.services.factor_analyzer import FactorAnalyzer
from app.services.factor_screening import (
    FactorQualityMonitor, FactorScreeningService,
)
from app.services.parquet_state_store import ParquetStateStore

pytestmark = pytest.mark.module_factor_engine

STOCKS = [f"S{i}.SZ" for i in range(30)]
DATES = pd.date_range("2026-01-05", periods=40, freq="B")


def _build_frames():
    """perfect 因子 = 常数日收益排序；noise 因子 = 纯随机；dup = perfect 的镜像。"""
    rng = np.random.default_rng(7)
    price_rows, factor_rows = [], []
    for code_i, code in enumerate(STOCKS):
        daily = 0.001 * (code_i - len(STOCKS) / 2)  # 线性排序的日收益
        price = 10.0
        for date in pd.date_range("2026-01-05", periods=45, freq="B"):
            price_rows.append({"ts_code": code, "trade_date": date,
                               "close": price})
            price *= 1 + daily
        for date in DATES:
            factor_rows.append({"ts_code": code, "trade_date": date,
                                "factor_id": "perfect", "factor_value": daily,
                                "percentile_rank": None, "z_score": None})
            factor_rows.append({
                "ts_code": code, "trade_date": date, "factor_id": "noise",
                "factor_value": rng.normal(),
                "percentile_rank": None, "z_score": None})
            factor_rows.append({
                "ts_code": code, "trade_date": date, "factor_id": "dup",
                "factor_value": -daily,
                "percentile_rank": None, "z_score": None})
    return pd.DataFrame(price_rows), pd.DataFrame(factor_rows)


class _FakeFactorRepo:
    TABLE_VALUES = "factor_values"

    def __init__(self, frames):
        self.frames = frames
        self.store = None  # 由用例注入 _FakeStore

    def list_definitions(self, include_inactive=False):
        return [{"factor_id": f} for f in self.frames]

    def get_values(self, factor_ids=None, trade_date=None, ts_codes=None,
                   start_date=None, end_date=None):
        ids = factor_ids or list(self.frames)
        df = pd.concat([self.frames[f] for f in ids if f in self.frames],
                       ignore_index=True)
        if df.empty:
            return df
        td = pd.to_datetime(df["trade_date"])
        if trade_date is not None:
            df = df[td == pd.to_datetime(trade_date)]
        if start_date is not None:
            df = df[td >= pd.to_datetime(start_date)]
        if end_date is not None:
            df = df[td <= pd.to_datetime(end_date)]
        return df


class _FakeStore:
    def __init__(self, partitions):
        self.partitions = partitions

    def list_partitions(self, table, by):
        return list(self.partitions)


class _FakeReader:
    def __init__(self, prices):
        self.prices = prices

    def get_return_prices(self, ts_codes=None, start_date=None, end_date=None):
        df = self.prices
        td = pd.to_datetime(df["trade_date"])
        if start_date is not None:
            df = df[td >= pd.to_datetime(start_date)]
        if end_date is not None:
            df = df[td <= pd.to_datetime(end_date)]
        return df


@pytest.fixture()
def service(tmp_path):
    prices, factors = _build_frames()
    repo = _FakeFactorRepo({"perfect": factors[factors.factor_id == "perfect"],
                            "noise": factors[factors.factor_id == "noise"],
                            "dup": factors[factors.factor_id == "dup"]})
    repo.store = _FakeStore([d.strftime("%Y-%m-%d") for d in DATES])
    analyzer = FactorAnalyzer(factor_repo=repo,
                              data_reader=_FakeReader(prices))
    state_store = ParquetStateStore(base_dir=str(tmp_path / "state"))
    svc = FactorScreeningService(store=state_store, analyzer=analyzer,
                                 factor_repo=repo)
    return svc, repo, prices


def test_screen_factors_metrics_and_save(service):
    svc, repo, prices = service
    report = svc.screen_factors(forward_period=1, sample_stride=2,
                                min_stocks=10)
    assert 'error' not in report
    perfect = report['factors']['perfect']
    assert perfect['ic_mean'] == pytest.approx(1.0, abs=1e-6)
    assert perfect['monotonicity'] == pytest.approx(1.0, abs=1e-6)
    # 常数因子截面秩恒定 → 相邻截面秩相关 = 1
    assert perfect['rank_autocorr'] == pytest.approx(1.0)
    noise = report['factors']['noise']
    assert abs(noise['ic_mean']) < 0.5
    # dup 与 perfect 完全负相关
    assert report['factors']['dup']['max_abs_corr'] == pytest.approx(1.0)
    assert report['factors']['dup']['most_correlated'] == 'perfect'

    # 入库后可按状态查询，且默认状态为 evaluated
    records = svc.list_screenings()
    assert {r['factor_id'] for r in records} == {'perfect', 'noise', 'dup'}
    assert all(r['status'] == 'evaluated' for r in records)


def test_screening_lifecycle(service):
    svc, _, _ = service
    svc.screen_factors(forward_period=1, sample_stride=2, min_stocks=10)
    result = svc.set_status('perfect', 'accepted', note='IC 稳定')
    assert result == {'factor_id': 'perfect', 'status': 'accepted'}
    assert svc.accepted_factors() == ['perfect']
    # 非法状态拒绝
    assert 'error' in svc.set_status('perfect', 'bogus')
    # 未体检过的因子拒绝
    assert 'error' in svc.set_status('ghost', 'accepted')


def test_select_low_collinearity(service):
    svc, _, _ = service
    selection = svc.select_low_collinearity(
        ['perfect', 'dup', 'noise'], threshold=0.7)
    assert 'error' not in selection
    assert 'perfect' in selection['kept']
    assert 'noise' in selection['kept']
    dropped = {d['factor_id']: d for d in selection['dropped']}
    assert dropped['dup']['correlated_with'] == 'perfect'


class _RealStore(ParquetStateStore):
    """带分区读写的假因子库：给质量监控用。"""


def test_quality_monitor_alerts(tmp_path):
    store = ParquetStateStore(base_dir=str(tmp_path / "q"))
    repo_rows = []
    partitions = [d.strftime("%Y-%m-%d") for d in DATES]
    for i, p in enumerate(partitions):
        rows = []
        for code_i, code in enumerate(STOCKS[:20]):
            rows.append({"ts_code": code, "trade_date": p,
                         "factor_id": "alpha_test",
                         "factor_value": 1.0 + code_i * 0.01 + i * 0.001})
        # 最后一个分区：覆盖骤降到 5 只 + 均值漂移
        if i == len(partitions) - 1:
            rows = rows[:5]
            for r in rows:
                r["factor_value"] = 50.0
        # 倒数第二个分区多一个因子，最新分区让它缺席
        if i == len(partitions) - 2:
            rows.append({"ts_code": STOCKS[0], "trade_date": p,
                         "factor_id": "alpha_gone", "factor_value": 0.5})
        repo_rows.extend(rows)

    df = pd.DataFrame(repo_rows)
    for p in partitions:
        part = df[df["trade_date"] == p]
        store.write_partition("factor_values", "trade_date", p, part)

    class _Repo:
        TABLE_VALUES = "factor_values"

        def __init__(self):
            self.store = store

    class _Reader:
        def get_return_prices(self, **kw):
            return pd.DataFrame({
                "ts_code": "X", "trade_date": pd.to_datetime(partitions),
                "close": 1.0,
            })

    monitor = FactorQualityMonitor(store=store, factor_repo=_Repo(),
                                   data_reader=_Reader())
    report = monitor.quality_report(last_n_partitions=40)
    assert 'error' not in report
    types = {a['type'] for a in report['alerts']}
    assert 'coverage_drop' in types
    assert 'coverage_low' in types
    assert 'factor_missing' in types
    assert 'drift' in types
    assert report['coverage_trend']['n_factors'] == 2
    # 分区与交易日历一致 → 无缺口
    assert report['partition_gaps'] == []
