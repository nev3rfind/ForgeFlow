from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid


class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    repository: str
    type: str
    test_command: Optional[str] = None
    build_command: Optional[str] = None
    lint_command: Optional[str] = None
    format_command: Optional[str] = None
    default_branch: str = "main"
    allowed_working_directories: list[str] = Field(default_factory=list)
    project_instructions: Optional[str] = None
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
