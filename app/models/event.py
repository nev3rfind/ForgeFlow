from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime, timezone
import uuid

class Event(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
