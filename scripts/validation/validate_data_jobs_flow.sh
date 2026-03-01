#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:5001}"

resp=$(curl -sS "${BASE_URL}/api/data-jobs/list")
python -c 'import json,sys; data=json.loads(sys.argv[1]); assert data.get("success") is True; print("true")' "$resp"
