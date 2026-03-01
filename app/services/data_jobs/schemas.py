from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class JobSubmitRequest:
    """Request payload for submitting a data job."""

    job_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    full_refresh: bool = False
