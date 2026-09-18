from typing import List, Optional
from datetime import datetime, timezone
from app.models import Task, TaskState, Event
from app.state import Repository
from app.events import EventBus

class TaskService:
    def __init__(self, repository: Repository, event_bus: EventBus):
        self.repo = repository
        self.event_bus = event_bus

    async def create_task(self, project_id: str, title: str, description: str, max_iterations: int = 5, requirements: Optional[str] = None, priority: str = "medium") -> Task:
        task = Task(
            project_id=project_id,
            title=title,
            description=description,
            max_iterations=max_iterations,
            requirements=requirements,
            priority=priority
        )
        saved = self.repo.save_task(task)
        await self._emit(saved.id, "TASK_CREATED", {"task_id": saved.id, "title": saved.title})
        return saved

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.repo.get_task(task_id)

    def list_tasks(self, project_id: Optional[str] = None) -> List[Task]:
        return self.repo.get_tasks(project_id)

    def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        task = self.repo.get_task(task_id)
        if not task:
            return None
        for k, v in kwargs.items():
            if v is not None and hasattr(task, k):
                setattr(task, k, v)
        task.updated_at = datetime.now(timezone.utc)
        return self.repo.save_task(task)

    def delete_task(self, task_id: str) -> bool:
        return self.repo.delete_task(task_id)

    async def update_status(self, task_id: str, status: TaskState, agent: Optional[str] = None, error: Optional[str] = None) -> Optional[Task]:
        task = self.repo.get_task(task_id)
        if not task:
            return None
        
        old_status = task.status
        task.status = status
        task.updated_at = datetime.now(timezone.utc)
        if agent:
            task.current_agent = agent
        if error:
            task.error_information = error

        # Set started_at on first transition from PENDING
        if old_status == TaskState.PENDING and status != TaskState.PENDING and not task.started_at:
            task.started_at = datetime.now(timezone.utc)

        if status in (TaskState.COMPLETED, TaskState.FAILED, TaskState.STOPPED):
            task.completed_at = datetime.now(timezone.utc)

        saved = self.repo.save_task(task)
        await self._emit(task_id, "STATE_CHANGED", {
            "old_status": old_status.value,
            "new_status": status.value,
            "agent": task.current_agent,
            "error": task.error_information
        })
        return saved

    async def emit_event(self, task_id: str, event_type: str, payload: dict) -> Event:
        return await self._emit(task_id, event_type, payload)

    async def _emit(self, task_id: str, event_type: str, payload: dict) -> Event:
        event = Event(task_id=task_id, event_type=event_type, payload=payload, timestamp=datetime.now(timezone.utc))
        self.repo.save_event(event)
        await self.event_bus.publish(event)
        return event
