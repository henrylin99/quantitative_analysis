"""
One-shot script to compute and store the 10 previously-uncomputed built-in factors.

Usage:
    python scripts/compute_missing_factors.py
    python scripts/compute_missing_factors.py --factors pe_percentile,pb_percentile
    python scripts/compute_missing_factors.py --dry-run

Safe to re-run: save_factor_values() deletes existing (trade_date, factor_id) rows before insert.
"""
import sys
import argparse
import logging
from datetime import datetime, timedelta

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Factors that are DAILY (use date-range iteration)
DAILY_FACTORS = [
    "pe_percentile",
    "pb_percentile",
    "ps_percentile",
    "big_order_ratio",
    "money_flow_momentum",
    "winner_rate_change",
]

# Factors that are QUARTERLY (compute once over full history, no date iteration)
QUARTERLY_FACTORS = [
    "roe_ttm",
    "roa_ttm",
    "revenue_growth",
    "profit_growth",
]

ALL_MISSING_FACTORS = DAILY_FACTORS + QUARTERLY_FACTORS


def compute_daily_factor(engine, factor_id: str, ts_codes: list,
                         start_date: str, end_date: str, dry_run: bool):
    """Compute a daily factor in monthly batches and save."""
    from app.services.factor_engine import FactorEngine

    fe = FactorEngine()
    current = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    total_saved = 0

    while current <= end:
        batch_end = min(current + timedelta(days=30), end)
        batch_start_str = current.strftime("%Y-%m-%d")
        batch_end_str = batch_end.strftime("%Y-%m-%d")

        try:
            result = fe.calculate_factor(factor_id, ts_codes, batch_start_str, batch_end_str)
            if not result.empty:
                if not dry_run:
                    fe.save_factor_values(result)
                total_saved += len(result)
                log.info(f"  {factor_id} [{batch_start_str}→{batch_end_str}]: {len(result)} rows")
            else:
                log.info(f"  {factor_id} [{batch_start_str}→{batch_end_str}]: 0 rows (no data)")
        except Exception as e:
            log.error(f"  {factor_id} [{batch_start_str}→{batch_end_str}] FAILED: {e}")

        current = batch_end + timedelta(days=1)

    log.info(f"  {factor_id}: total {total_saved} rows {'(dry-run, not saved)' if dry_run else 'saved'}")


def compute_quarterly_factor(engine, factor_id: str, ts_codes: list, dry_run: bool):
    """Compute a quarterly factor once over full available history."""
    from app.services.factor_engine import FactorEngine

    fe = FactorEngine()
    try:
        result = fe.calculate_factor(factor_id, ts_codes, "2015-01-01", datetime.today().strftime("%Y-%m-%d"))
        if not result.empty:
            if not dry_run:
                fe.save_factor_values(result)
            log.info(f"  {factor_id}: {len(result)} rows {'(dry-run)' if dry_run else 'saved'}")
        else:
            log.warning(f"  {factor_id}: returned 0 rows — check data availability")
    except Exception as e:
        log.error(f"  {factor_id} FAILED: {e}")


def main():
    parser = argparse.ArgumentParser(description="Compute missing built-in factors")
    parser.add_argument("--factors", default=",".join(ALL_MISSING_FACTORS),
                        help="Comma-separated factor IDs to compute")
    parser.add_argument("--start-date", default="2023-01-01",
                        help="Start date for daily factors (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=datetime.today().strftime("%Y-%m-%d"),
                        help="End date for daily factors (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write to DB")
    args = parser.parse_args()

    factors_to_run = [f.strip() for f in args.factors.split(",")]

    from app import create_app, db
    from app.models import StockBasic

    app = create_app()
    with app.app_context():
        ts_codes = [s.ts_code for s in StockBasic.query.all()]
        log.info(f"Loaded {len(ts_codes)} stocks")
        log.info(f"Factors to compute: {factors_to_run}")
        log.info(f"Date range: {args.start_date} -> {args.end_date}")
        if args.dry_run:
            log.info("DRY RUN -- no writes")

        for factor_id in factors_to_run:
            log.info(f"\n=== {factor_id} ===")
            if factor_id in QUARTERLY_FACTORS:
                compute_quarterly_factor(db.engine, factor_id, ts_codes, args.dry_run)
            elif factor_id in DAILY_FACTORS:
                compute_daily_factor(db.engine, factor_id, ts_codes,
                                     args.start_date, args.end_date, args.dry_run)
            else:
                log.warning(f"  {factor_id}: unknown factor ID, skipping")

        log.info("\nDone.")


if __name__ == "__main__":
    main()
