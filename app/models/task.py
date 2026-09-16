from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid
from app.models.state import TaskState

class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    title: str
    description: str
    requirements: Optional[str] = None
    priority: str = "medium"
    status: TaskState = TaskState.PENDING
    iteration: int = 1
    max_iterations: int = 5
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    current_agent: Optional[str] = None
    current_worktree: Optional[str] = None
    error_information: Optional[str] = None
