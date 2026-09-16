from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid

class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    name: str
    path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
