from app.services.tongdaxin.bars import normalize_tdx_minute_bars


def test_tdx_minute_payload_normalizes_to_minute_parquet_schema():
    payload = [
        {
            "datetime": "2026-06-05 09:35",
            "open": 10.0,
            "high": 10.2,
            "low": 9.9,
            "close": 10.1,
            "vol": 1000,
            "amount": 10100.0,
        },
        {
            "datetime": "2026-06-05 09:40",
            "open": 10.1,
            "high": 10.3,
            "low": 10.0,
            "close": 10.2,
            "vol": 1200,
            "amount": 12240.0,
        },
    ]

    frame = normalize_tdx_minute_bars(payload, market=1, code="600000", period_type="5min")

    assert frame["ts_code"].tolist() == ["sh.600000", "sh.600000"]
    assert frame["period_type"].tolist() == ["5min", "5min"]
    assert "pre_close" in frame.columns
    assert frame.iloc[0]["change"] == 0
    assert frame.iloc[1]["volume"] == 1200
