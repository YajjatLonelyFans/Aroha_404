from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SourceInfo:
    """Where a piece of external data came from, stamped when it was retrieved."""

    name: str
    url: str
    retrieved_at: datetime
    is_mock: bool = False
