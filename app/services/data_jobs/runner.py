from pathlib import Path
import os
import subprocess
from typing import Any, Dict, Optional, Tuple


class ScriptRunner:
    """Adapter to execute legacy app/utils scripts in a managed way."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).resolve().parents[3]

    def validate_script(self, script_path: str) -> Tuple[bool, str]:
        full_path = self.project_root / script_path
        if not full_path.exists() or not full_path.is_file():
            return False, f"script not found: {script_path}"
        return True, "ok"

    def run_script(
        self,
        script_path: str,
        params: Optional[Dict[str, Any]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> subprocess.CompletedProcess:
        ok, msg = self.validate_script(script_path)
        if not ok:
            raise FileNotFoundError(msg)

        full_path = self.project_root / script_path
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        if params:
            start_date = params.get("start_date")
            end_date = params.get("end_date")
            trade_date = params.get("trade_date")
            full_refresh = params.get("full_refresh")
            source_name = params.get("source_name")
            source_mode = params.get("source_mode")
            snapshot_tag = params.get("snapshot_tag")
            if start_date:
                merged_env["DATA_JOB_START_DATE"] = str(start_date)
            if end_date:
                merged_env["DATA_JOB_END_DATE"] = str(end_date)
            if trade_date:
                merged_env["DATA_JOB_TRADE_DATE"] = str(trade_date)
            if full_refresh is not None:
                merged_env["DATA_JOB_FULL_REFRESH"] = str(full_refresh)
            if source_name:
                merged_env["DATA_JOB_SOURCE_NAME"] = str(source_name)
            if source_mode:
                merged_env["DATA_JOB_SOURCE_MODE"] = str(source_mode)
            if snapshot_tag:
                merged_env["DATA_JOB_SNAPSHOT_TAG"] = str(snapshot_tag)

            for key, value in params.items():
                if value is None:
                    continue
                env_key = f"DATA_JOB_PARAM_{str(key).upper()}"
                merged_env[env_key] = str(value)
        return subprocess.run(
            ["python", str(full_path)],
            cwd=str(self.project_root),
            env=merged_env,
            capture_output=True,
            text=True,
            check=False,
        )
