import pandas as pd

from app.services.stock_scoring import StockScoringEngine


def test_ml_ensemble_scoring_respects_weights():
    factor_scores = pd.DataFrame(
        {
            "m1": [1.0, 0.0],
            "m2": [0.0, 1.0],
        },
        index=["A", "B"],
    )
    engine = StockScoringEngine()

    scores = engine._ml_ensemble_scoring(factor_scores, {"m1": 0.8, "m2": 0.2})

    assert scores["A"] > scores["B"]


def test_rank_ic_scoring_differs_from_equal_weight():
    factor_scores = pd.DataFrame(
        {
            "f1": [1.0, 2.0, 3.0, 4.0],
            "f2": [1.0, 2.0, 2.0, 3.0],
            "f3": [4.0, 3.0, 2.0, 1.0],
        },
        index=["A", "B", "C", "D"],
    )
    engine = StockScoringEngine()

    rank_ic_scores = engine._rank_ic_scoring(factor_scores, {})
    equal_scores = engine._equal_weight_scoring(factor_scores, {})

    assert not rank_ic_scores.equals(equal_scores)


def test_calculate_composite_score_rank_ic_not_fallback_equal_weight():
    factor_scores = pd.DataFrame(
        {
            "f1": [1.0, 2.0, 3.0, 4.0],
            "f2": [1.0, 2.0, 2.0, 3.0],
            "f3": [4.0, 3.0, 2.0, 1.0],
        },
        index=["A", "B", "C", "D"],
    )
    engine = StockScoringEngine()

    rank_ic_df = engine.calculate_composite_score(factor_scores, {}, method="rank_ic")
    equal_df = engine.calculate_composite_score(factor_scores, {}, method="equal_weight")

    rank_ic_series = rank_ic_df.set_index("ts_code").loc[factor_scores.index, "composite_score"]
    equal_series = equal_df.set_index("ts_code").loc[factor_scores.index, "composite_score"]

    assert not rank_ic_series.equals(equal_series)
