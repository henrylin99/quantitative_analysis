"""按新 point-in-time 逻辑逐个重算基本面因子（每因子独立子进程，防止单进程内存累积）。

用法: bash scripts/refresh_fundamental_factors.sh
"""
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=logs/refresh_fundamental_factors.log
echo "==== refresh start $(date '+%H:%M:%S') ====" >> "$LOG"

for FID in roe_ttm roa_ttm revenue_growth profit_growth; do
  echo "[$(date '+%H:%M:%S')] >>> $FID start" >> "$LOG"
  "$PY" - "$FID" >> "$LOG" 2>&1 << 'INNER'
import sys
import time

import pandas as pd

factor_id = sys.argv[1]
from loguru import logger

logger.remove()

from app.services.factor_engine import FactorEngine

fe = FactorEngine()
t0 = time.time()
result = fe.calculate_factor(factor_id, None, "2024-01-01", pd.Timestamp.today().strftime("%Y-%m-%d"))
if result.empty:
    print(f"[{factor_id}] EMPTY result", flush=True)
    sys.exit(0)
written = fe.save_factor_values(result)
print(f"[{factor_id}] OK rows={len(result)} saved={written} elapsed={time.time()-t0:.0f}s", flush=True)
INNER
  echo "[$(date '+%H:%M:%S')] <<< $FID exit=$?" >> "$LOG"
done
echo "==== refresh done $(date '+%H:%M:%S') ====" >> "$LOG"
