"""
IC/IR auto-measurement for all factors in factor_values.

Soft assertions: prints IC/IR table via warnings.warn — never blocks CI.
Hard assertion: fails only if ALL factors show |IC| < 0.005 (full signal collapse).

Marker: module_factor_engine
"""
import warnings
import statistics
from collections import defaultdict

import pytest
from scipy.stats import spearmanr

pytestmark = pytest.mark.module_factor_engine


def _get_ic_ir_table(db_engine):
    """Query factor_values + stock_daily_history, compute IC/IR per factor."""
    from sqlalchemy import text

    # 1. Distinct factor_ids currently in DB
    with db_engine.connect() as conn:
        factor_rows = conn.execute(text(
            "SELECT DISTINCT factor_id FROM factor_values"
        )).fetchall()
    factor_ids = [r[0] for r in factor_rows]

    results = {}

    for factor_id in factor_ids:
        with db_engine.connect() as conn:
            # Get factor values joined to next-day forward return
            rows = conn.execute(text("""
                SELECT fv.ts_code, fv.trade_date, fv.factor_value,
                       h.pct_chg AS forward_return
                FROM factor_values fv
                JOIN stock_daily_history h
                  ON h.ts_code = fv.ts_code
                 AND h.trade_date = (
                     SELECT MIN(trade_date)
                     FROM stock_daily_history
                     WHERE ts_code = fv.ts_code
                       AND trade_date > fv.trade_date
                 )
                WHERE fv.factor_id = :fid
                  AND fv.trade_date >= (
                      SELECT DATE_SUB(MAX(trade_date), INTERVAL 90 DAY)
                      FROM factor_values
                      WHERE factor_id = :fid
                  )
                  AND fv.factor_value IS NOT NULL
                  AND h.pct_chg IS NOT NULL
            """), {"fid": factor_id}).fetchall()

        if len(rows) < 30:
            results[factor_id] = {"IC_mean": None, "IC_std": None, "IC_IR": None, "n_dates": 0}
            continue

        # Group by trade_date, compute per-date Spearman IC
        date_groups = defaultdict(list)
        for ts_code, trade_date, fval, fwd in rows:
            date_groups[trade_date].append((float(fval), float(fwd)))

        ic_series = []
        for date, pairs in date_groups.items():
            if len(pairs) < 10:
                continue
            fvals, fwds = zip(*pairs)
            corr, _ = spearmanr(fvals, fwds)
            if corr == corr:  # not NaN
                ic_series.append(corr)

        if len(ic_series) < 5:
            results[factor_id] = {"IC_mean": None, "IC_std": None, "IC_IR": None, "n_dates": len(ic_series)}
            continue

        ic_mean = sum(ic_series) / len(ic_series)
        ic_std = statistics.stdev(ic_series) if len(ic_series) > 1 else 0
        ic_ir = ic_mean / ic_std if ic_std > 0 else 0

        results[factor_id] = {
            "IC_mean": ic_mean,
            "IC_std": ic_std,
            "IC_IR": ic_ir,
            "n_dates": len(ic_series),
        }

    return results


def test_factor_ic_ir_report():
    """Compute and print IC/IR for all factors. Hard-fail only on full signal collapse."""
    from app import create_app, db

    app = create_app()
    with app.app_context():
        results = _get_ic_ir_table(db.engine)

    if not results:
        pytest.skip("factor_values table is empty — run compute_missing_factors.py first")

    TARGET_IC_IR = 0.5
    TARGET_IC = 0.03

    # Build report string
    lines = ["\nfactor_ic_ir_report:"]
    lines.append(f"  {'factor_id':<25} {'IC_mean':>8} {'IC_std':>8} {'IC_IR':>8} {'n_dates':>8}  {'IC':>4}  {'IR':>4}")
    lines.append("  " + "-" * 72)

    factors_with_data = []
    for factor_id, m in sorted(results.items()):
        if m["IC_mean"] is None:
            lines.append(f"  {factor_id:<25} {'N/A':>8} {'N/A':>8} {'N/A':>8} {m['n_dates']:>8}  {'?':>4}  {'?':>4}")
            continue
        ic_ok = "OK" if abs(m["IC_mean"]) >= TARGET_IC else "low"
        ir_ok = "OK" if abs(m["IC_IR"]) >= TARGET_IC_IR else "low"
        lines.append(
            f"  {factor_id:<25} {m['IC_mean']:>8.4f} {m['IC_std']:>8.4f} {m['IC_IR']:>8.3f} {m['n_dates']:>8}  {ic_ok:>4}  {ir_ok:>4}"
        )
        factors_with_data.append((factor_id, m))

    warnings.warn("\n".join(lines), UserWarning, stacklevel=2)

    # Hard assertion: signal collapse = ALL factors |IC| < 0.005
    if factors_with_data:
        max_abs_ic = max(abs(m["IC_mean"]) for _, m in factors_with_data)
        assert max_abs_ic >= 0.005, (
            f"Signal collapse detected: max |IC| across all factors = {max_abs_ic:.4f} < 0.005. "
            "Factor values may be corrupted or returns data is missing."
        )
