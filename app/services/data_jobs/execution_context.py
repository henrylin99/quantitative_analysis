from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class JobExecutionContext:
    """Runtime execution context for a data job."""

    run_id: int
    job_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    full_refresh: bool = False
