from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class JobSubmitRequest:
    """Request payload for submitting a data job."""

    job_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    full_refresh: bool = False


@dataclass(frozen=True)
class JobDefinition:
    """Metadata for a supported data job."""

    job_type: str
    group: str
    script_path: str
    display_name: str = ""
    description: str = ""
    dangerous: bool = False
    dependencies: List[str] = field(default_factory=list)
    default_params: Dict[str, Any] = field(default_factory=dict)
    recommended_order: int = 999
    source_name: str = "unknown"
    source_mode: str = "full"
    supports_incremental: bool = False
