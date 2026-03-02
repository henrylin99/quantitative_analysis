def test_dual_track_core_endpoints_registered(app):
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert '/api/data-jobs/submit' in rules
    assert '/api/ml-factor/backtest/run' in rules
