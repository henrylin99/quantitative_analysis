#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:5001}"

echo "[1/3] check /api/data-jobs/jobs"
jobs_resp=$(curl -sS "${BASE_URL}/api/data-jobs/jobs")
python - "$jobs_resp" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload.get("success") is True, payload
assert isinstance(payload.get("jobs"), list), payload
print("jobs endpoint ok")
PY

echo "[2/3] check /api/data-jobs/list"
list_resp=$(curl -sS "${BASE_URL}/api/data-jobs/list")
python - "$list_resp" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload.get("success") is True, payload
assert isinstance(payload.get("runs"), list), payload
print("list endpoint ok")
PY

echo "[3/3] check unknown job submit returns 400"
body_file=$(mktemp)
status_code=$(curl -sS -o "$body_file" -w "%{http_code}" \
  -X POST "${BASE_URL}/api/data-jobs/submit" \
  -H 'Content-Type: application/json' \
  -d '{"job_type":"unknown_job_type","params":{}}')
body=$(cat "$body_file")
rm -f "$body_file"

python - "$status_code" "$body" <<'PY'
import json
import sys

status_code = int(sys.argv[1])
payload = json.loads(sys.argv[2])
assert status_code == 400, (status_code, payload)
assert payload.get("success") is False, payload
print("unknown job validation ok")
PY

echo "validation passed"
