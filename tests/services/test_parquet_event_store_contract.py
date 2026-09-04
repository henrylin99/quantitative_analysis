from datetime import datetime
from pathlib import Path


from app.services.parquet_event_store import ParquetEventStore


def test_indicator_events_are_appended_and_read_back(tmp_path):
    store = ParquetEventStore(base_dir=tmp_path)
    rows = [
        {
            'ts_code': '000001.SZ',
            'datetime': datetime(2026, 6, 4, 9, 35),
            'period_type': '5min',
            'indicator_name': 'MA',
            'value1': 10.1,
            'value2': None,
            'value3': None,
            'value4': None,
        },
        {
            'ts_code': '000001.SZ',
            'datetime': datetime(2026, 6, 4, 9, 40),
            'period_type': '5min',
            'indicator_name': 'MA',
            'value1': 10.3,
            'value2': None,
            'value3': None,
            'value4': None,
        },
    ]

    written = store.append_indicators(rows)
    assert written == 2
    assert (Path(tmp_path) / 'realtime_events').exists()

    latest = store.get_latest_indicators('000001.SZ', '5min', limit=1)
    assert len(latest) == 1
    assert latest.iloc[0]['value1'] == 10.3

    history = store.get_indicator_history('000001.SZ', '5min', 'MA')
    assert len(history) == 2
    assert history.iloc[0]['datetime'] < history.iloc[1]['datetime']


def test_signal_events_are_appended_and_filtered(tmp_path):
    store = ParquetEventStore(base_dir=tmp_path)
    rows = [
        {
            'ts_code': '000001.SZ',
            'datetime': datetime(2026, 6, 4, 9, 45),
            'period_type': '5min',
            'strategy_name': 'ma_crossover',
            'signal_type': 'BUY',
            'signal_strength': 0.7,
            'confidence': 0.8,
            'trigger_price': 10.4,
            'target_price': 10.9,
            'stop_loss_price': 10.1,
            'strategy_params': '{}',
            'indicators_used': '["MA"]',
            'status': 'ACTIVE',
            'expiry_time': datetime(2026, 6, 4, 13, 45),
        },
        {
            'ts_code': '000001.SZ',
            'datetime': datetime(2026, 6, 3, 9, 45),
            'period_type': '5min',
            'strategy_name': 'ma_crossover',
            'signal_type': 'SELL',
            'signal_strength': -0.7,
            'confidence': 0.8,
            'trigger_price': 10.2,
            'target_price': 9.8,
            'stop_loss_price': 10.5,
            'strategy_params': '{}',
            'indicators_used': '["MA"]',
            'status': 'EXPIRED',
            'expiry_time': datetime(2026, 6, 3, 13, 45),
        },
    ]

    written = store.append_signals(rows)
    assert written == 2

    active = store.get_active_signals('000001.SZ', strategy_name='ma_crossover')
    assert len(active) == 1
    assert active.iloc[0]['signal_type'] == 'BUY'

    history = store.get_signals_by_time_range(
        datetime(2026, 6, 3, 0, 0),
        datetime(2026, 6, 4, 23, 59),
        ts_code='000001.SZ',
    )
    assert len(history) == 2


def test_indicator_and_signal_stats_reflect_parquet_data(tmp_path):
    store = ParquetEventStore(base_dir=tmp_path)
    store.append_indicators([
        {
            'ts_code': '000001.SZ',
            'datetime': datetime(2026, 6, 4, 9, 35),
            'period_type': '5min',
            'indicator_name': 'MA',
            'value1': 10.1,
            'value2': None,
            'value3': None,
            'value4': None,
        },
        {
            'ts_code': '000002.SZ',
            'datetime': datetime(2026, 6, 4, 9, 40),
            'period_type': '15min',
            'indicator_name': 'RSI',
            'value1': 61.0,
            'value2': None,
            'value3': None,
            'value4': None,
        },
    ])
    store.append_signals([
        {
            'ts_code': '000001.SZ',
            'datetime': datetime(2026, 6, 4, 9, 45),
            'period_type': '5min',
            'strategy_name': 'ma_crossover',
            'signal_type': 'BUY',
            'signal_strength': 0.7,
            'confidence': 0.8,
            'trigger_price': 10.4,
            'target_price': 10.9,
            'stop_loss_price': 10.1,
            'strategy_params': '{}',
            'indicators_used': '["MA"]',
            'status': 'EXECUTED',
            'profit_loss': 1.2,
            'expiry_time': datetime(2026, 6, 4, 13, 45),
        }
    ])

    indicator_stats = store.get_indicator_stats()
    assert indicator_stats['total_records'] == 2
    assert indicator_stats['indicator_stats']['MA'] == 1

    signal_stats = store.get_signal_stats()
    assert signal_stats['total_signals'] == 1
    assert signal_stats['status_stats']['EXECUTED'] == 1
