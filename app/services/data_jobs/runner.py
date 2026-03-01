from pathlib import Path
import subprocess
from typing import Dict, Optional, Tuple


class ScriptRunner:
    """Adapter to execute legacy app/utils scripts in a managed way."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).resolve().parents[3]

    def validate_script(self, script_path: str) -> Tuple[bool, str]:
        full_path = self.project_root / script_path
        if not full_path.exists() or not full_path.is_file():
            return False, f"script not found: {script_path}"
        return True, "ok"

    def run_script(self, script_path: str, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        ok, msg = self.validate_script(script_path)
        if not ok:
            raise FileNotFoundError(msg)

        full_path = self.project_root / script_path
        return subprocess.run(
            ["python", str(full_path)],
            cwd=str(self.project_root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
