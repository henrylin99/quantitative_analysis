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
            if start_date:
                merged_env["DATA_JOB_START_DATE"] = str(start_date)
            if end_date:
                merged_env["DATA_JOB_END_DATE"] = str(end_date)
            if trade_date:
                merged_env["DATA_JOB_TRADE_DATE"] = str(trade_date)
            if full_refresh is not None:
                merged_env["DATA_JOB_FULL_REFRESH"] = str(full_refresh)

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
