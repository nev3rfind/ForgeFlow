import os
import asyncio
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import settings
from app.state import Database, Repository
from app.events.bus import EventBus
from app.services import ProjectService, TaskService
from app.git.service import GitService
from app.qa.runner import CommandRunner, validate_command, CommandValidationError
from app.integrations.antigravity_adapter import AntigravityProvider
from app.integrations.agy_adapter import AgyProvider
from app.integrations.abacus_adapter import AbacusReviewerProvider
from app.orchestration.engine import Orchestrator, TERMINAL_STATES
from app.models import Project, Task, TaskState
from app.registry import provider_registry
from app.roles import role_router, RoleConfig

db = Database(settings.database_path)
repo = Repository(db)
event_bus = EventBus()
project_service = ProjectService(repo)
task_service = TaskService(repo, event_bus)
git_service = GitService(workspace_root=settings.workspace_root)
qa_runner = CommandRunner()

if settings.implementation_provider == "agy":
    provider = AgyProvider()
    # Honour the configured timeout (env var already read by AgyProvider.__init__)
else:
    provider = AntigravityProvider()

# Conditionally configure Abacus reviewer provider
reviewer_provider = None
if settings.abacus_reviewer_enabled:
    reviewer_provider = AbacusReviewerProvider(
        cli_path=settings.abacusai_path or None,
        timeout=settings.abacus_timeout,
        fallback_enabled=settings.abacus_reviewer_fallback_enabled,
        review_mode=settings.abacus_review_mode
    )

orchestrator = Orchestrator(
    task_service=task_service,
    project_service=project_service,
    git_service=git_service,
    event_bus=event_bus,
    provider=provider,
    qa_runner=qa_runner,
    reviewer_provider=reviewer_provider,
    fallback_enabled=settings.abacus_reviewer_fallback_enabled,
    review_mode=settings.abacus_review_mode
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for task_id in list(orchestrator.active_tasks.keys()):
        await orchestrator.stop_task(task_id)

app = FastAPI(title="ForgeFlow API", lifespan=lifespan)

DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "dashboard")
app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")

class ProjectCreate(BaseModel):
    name: str
    repository: str
    type: str
    description: Optional[str] = None
    test_command: Optional[str] = None
    build_command: Optional[str] = None
    lint_command: Optional[str] = None
    format_command: Optional[str] = None
    default_branch: Optional[str] = None
    project_instructions: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    repository: Optional[str] = None
    type: Optional[str] = None
    test_command: Optional[str] = None
    build_command: Optional[str] = None
    lint_command: Optional[str] = None
    format_command: Optional[str] = None
    default_branch: Optional[str] = None
    project_instructions: Optional[str] = None
    active: Optional[bool] = None

class TaskCreate(BaseModel):
    project_id: str
    title: str
    description: str
    requirements: Optional[str] = None
    priority: str = "medium"
    max_iterations: int = 5

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    priority: Optional[str] = None
    max_iterations: Optional[int] = None

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "active_tasks": len(orchestrator.active_tasks),
        "abacus_reviewer_enabled": bool(reviewer_provider),
        "abacus_reviewer_available": reviewer_provider.is_available() if reviewer_provider else False,
        "abacus_review_mode": settings.abacus_review_mode,
        "abacus_fallback_enabled": settings.abacus_reviewer_fallback_enabled
    }

@app.get("/config")
def get_config():
    return settings.public_dict()

@app.get("/overview")
def overview():
    tasks = task_service.list_tasks()
    projects = project_service.list_projects()
    active_ids = set(orchestrator.active_tasks.keys())

    def count(pred) -> int:
        return sum(1 for t in tasks if pred(t))

    running = [t for t in tasks if t.id in active_ids]
    passing, failing = _test_metrics()

    return {
        "active_tasks": len(active_ids),
        "queued_tasks": count(lambda t: t.status == TaskState.PENDING),
        "completed_tasks": count(lambda t: t.status == TaskState.COMPLETED),
        "blocked_tasks": count(lambda t: t.status == TaskState.BLOCKED),
        "failed_tasks": count(lambda t: t.status in (TaskState.FAILED, TaskState.STOPPED)),
        "projects": len(projects),
        "awaiting_review": count(lambda t: t.status == TaskState.REVIEW),
        "tests_passing": passing,
        "tests_failing": failing,
        "currently_running": [t.model_dump() for t in running],
        "recent_activity": [e.model_dump() for e in repo.get_all_events(limit=20)]
    }

def _test_metrics():
    latest = {}
    for e in repo.get_all_events(limit=10000):
        if e.event_type == "TEST_RESULT" and e.task_id not in latest:
            latest[e.task_id] = e.payload.get("exit_code")
    passing = sum(1 for v in latest.values() if v == 0)
    failing = sum(1 for v in latest.values() if v != 0)
    return passing, failing

@app.get("/projects", response_model=List[Project])
def list_projects():
    return project_service.list_projects()

@app.post("/projects", response_model=Project)
def create_project(req: ProjectCreate):
    for label, cmd in (
        ("test_command", req.test_command),
        ("build_command", req.build_command),
        ("lint_command", req.lint_command),
        ("format_command", req.format_command),
    ):
        if cmd:
            try:
                validate_command(cmd)
            except CommandValidationError as e:
                raise HTTPException(status_code=400, detail=f"Invalid {label}: {e}")
    return project_service.create_project(
        name=req.name,
        repository_path=req.repository,
        type=req.type,
        description=req.description,
        test_command=req.test_command,
        build_command=req.build_command,
        lint_command=req.lint_command,
        format_command=req.format_command,
        default_branch=req.default_branch,
        project_instructions=req.project_instructions
    )

@app.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str):
    project = project_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@app.put("/projects/{project_id}", response_model=Project)
def update_project(project_id: str, req: ProjectUpdate):
    project = project_service.update_project(project_id, **req.model_dump(exclude_unset=True))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    if not project_service.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"status": "deleted"}

@app.get("/tasks", response_model=List[Task])
def list_tasks():
    return task_service.list_tasks()

@app.post("/tasks", response_model=Task)
async def create_task(req: TaskCreate):
    return await task_service.create_task(
        project_id=req.project_id,
        title=req.title,
        description=req.description,
        requirements=req.requirements,
        priority=req.priority,
        max_iterations=req.max_iterations
    )

@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: str):
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.put("/tasks/{task_id}", response_model=Task)
def update_task(task_id: str, req: TaskUpdate):
    task = task_service.update_task(task_id, **req.model_dump(exclude_unset=True))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    if not task_service.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted"}

@app.post("/tasks/{task_id}/start")
async def start_task(task_id: str):
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status in TERMINAL_STATES:
        await orchestrator.retry_task(task_id)
    else:
        await orchestrator.start_task(task_id)
    return {"status": "started"}

@app.post("/tasks/{task_id}/stop")
async def stop_task(task_id: str):
    await orchestrator.stop_task(task_id)
    return {"status": "stopped"}

@app.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    await orchestrator.pause_task(task_id)
    return {"status": "paused"}

@app.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    await orchestrator.resume_task(task_id)
    return {"status": "resumed"}

@app.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str, reset_branch: bool = False):
    try:
        await orchestrator.retry_task(task_id, reset_branch=reset_branch)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"status": "retrying"}

@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    await orchestrator.stop_task(task_id)
    return {"status": "cancelled"}

@app.get("/tasks/{task_id}/events")
def get_events(task_id: str):
    return repo.get_events(task_id)

@app.get("/tasks/{task_id}/state-history")
def get_state_history(task_id: str):
    """Compute per-state durations from STATE_CHANGED events."""
    events = repo.get_events(task_id)
    state_events = [e for e in events if e.event_type == "STATE_CHANGED"]
    
    history = []
    for i, ev in enumerate(state_events):
        state = ev.payload.get("new_status", "")
        agent = ev.payload.get("agent")
        entered_at = ev.timestamp.isoformat() if ev.timestamp else None
        
        # Duration = time until next state change
        exited_at = None
        duration_seconds = None
        if i + 1 < len(state_events):
            next_ts = state_events[i + 1].timestamp
            if next_ts and ev.timestamp:
                exited_at = next_ts.isoformat()
                duration_seconds = round((next_ts - ev.timestamp).total_seconds(), 1)
        
        history.append({
            "state": state,
            "agent": agent,
            "entered_at": entered_at,
            "exited_at": exited_at,
            "duration_seconds": duration_seconds,
        })
    
    return history

@app.get("/tasks/{task_id}/artifacts")
def list_artifacts(task_id: str):
    return repo.get_artifacts(task_id)

@app.get("/artifacts/{artifact_id}/content")
def get_artifact_content(artifact_id: str):
    artifact = repo.get_artifact(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"name": artifact.name, "content": _safe_read_artifact(artifact.path)}

@app.get("/activity")
def activity(limit: int = 200):
    return [e.model_dump() for e in repo.get_all_events(limit=limit)]

def _safe_read_artifact(path: str) -> str:
    if not path:
        raise HTTPException(status_code=404, detail="Artifact has no file path")
    abs_path = os.path.abspath(path)
    workspace_root = os.path.abspath(settings.workspace_root)
    if not (abs_path == workspace_root or abs_path.startswith(workspace_root + os.sep)):
        raise HTTPException(status_code=403, detail="Artifact path outside allowed workspace")
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Artifact file not found")
    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard", "index.html")
    with open(dashboard_path, "r", encoding="utf-8") as f:
        return f.read()

@app.websocket("/ws/tasks/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await websocket.accept()
    queue = asyncio.Queue()

    async def callback(event):
        await queue.put(event)

    event_bus.subscribe(task_id, callback)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json({
                "event_type": event.event_type,
                "task_id": event.task_id,
                "created_at": event.timestamp.isoformat(),
                "payload": event.payload
            })
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(task_id, callback)


@app.get("/providers")
def get_providers():
    return [p.model_dump() for p in provider_registry.get_all()]

@app.get("/settings/roles")
def get_roles():
    return {k: v.model_dump() for k, v in role_router.roles.items()}

@app.put("/settings/roles/{role_name}")
def update_role(role_name: str, config: RoleConfig):
    if role_name not in role_router.roles:
        raise HTTPException(status_code=404, detail="Role not found")
    role_router.update_role(role_name, config.provider, config.model)
    return role_router.get_role(role_name).model_dump()

@app.post("/settings/reset-data")
async def reset_data():
    active_states = [
        TaskState.PENDING, TaskState.PREPARING, TaskState.INVESTIGATING,
        TaskState.ROOT_CAUSE_READY, TaskState.ROOT_CAUSE_REVIEW,
        TaskState.IMPLEMENTING, TaskState.IMPLEMENTATION_READY,
        TaskState.TESTING, TaskState.QA, TaskState.REVIEW,
        TaskState.NEEDS_CHANGES, TaskState.APPROVED
    ]
    all_tasks = repo.get_tasks()
    active_tasks = [t for t in all_tasks if t.status in active_states]
    if active_tasks:
        raise HTTPException(status_code=400, detail=f"Cannot reset. {len(active_tasks)} tasks are active.")
    
    import os, shutil, subprocess
    if settings.workspace_root and os.path.exists(settings.workspace_root):
        for item in os.listdir(settings.workspace_root):
            item_path = os.path.join(settings.workspace_root, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
                
    projects = repo.get_projects()
    for p in projects:
        if os.path.isdir(p.repository):
            try:
                subprocess.run(["git", "worktree", "prune"], cwd=p.repository, capture_output=True, check=False)
            except Exception:
                pass

    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_events")
        cursor.execute("DELETE FROM artifacts")
        cursor.execute("DELETE FROM tasks")
        conn.commit()

    return {"status": "success"}


@app.post("/system/restart")
async def restart_system():
    # We return a success response, then trigger a background task to exit with code 42
    import asyncio
    import os
    
    async def _do_restart():
        await asyncio.sleep(1)
        os._exit(42)
        
    asyncio.create_task(_do_restart())
    return {"status": "success"}

@app.post("/settings/reset-config")
async def reset_config():
    from app.config import Settings
    global settings
    settings.__init__() # Reset to defaults
    return {"status": "success"}
