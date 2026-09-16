import asyncio
import os
import subprocess
import pytest

from app.models import TaskState, Project
from app.state import Database, Repository
from app.events.bus import EventBus
from app.services import ProjectService, TaskService
from app.git.service import GitService
from app.qa.runner import CommandRunner
from app.orchestration.engine import Orchestrator
from tests.test_orchestration_review import DummyAgentProvider


@pytest.fixture
def setup_engine(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    ws_root = tmp_path / "worktrees"
    ws_root.mkdir()
    db_file = tmp_path / "test.db"

    # Initialize git repo
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)

    readme = repo_dir / "README.md"
    readme.write_text("# Main\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit on main"], cwd=str(repo_dir), check=True)

    db = Database(str(db_file))
    repo = Repository(db)
    bus = EventBus()
    task_svc = TaskService(repo, bus)
    project_svc = ProjectService(repo)
    git_svc = GitService(workspace_root=str(ws_root))
    runner = CommandRunner()
    provider = DummyAgentProvider()

    project = Project(
        id="proj-test",
        name="Test Project",
        type="generic",
        repository=str(repo_dir),
        default_branch="main"
    )
    project_svc.repo.save_project(project)

    engine = Orchestrator(
        task_service=task_svc,
        project_service=project_svc,
        git_service=git_svc,
        event_bus=bus,
        provider=provider,
        qa_runner=runner,
    )

    return {
        "engine": engine,
        "git_svc": git_svc,
        "task_svc": task_svc,
        "repo_dir": str(repo_dir),
        "ws_root": str(ws_root),
    }


@pytest.mark.asyncio
async def test_retry_task_propagates_reset_branch_flag(setup_engine):
    """retry_task(reset_branch=True/False) actually propagates reset_branch to git_service.create_worktree."""
    engine: Orchestrator = setup_engine["engine"]
    task_svc: TaskService = setup_engine["task_svc"]
    git_svc: GitService = setup_engine["git_svc"]

    task = await task_svc.create_task(
        project_id="proj-test",
        title="Propagation Test",
        description="Verify reset_branch reaches create_worktree"
    )

    original_create = git_svc.create_worktree
    call_log = []

    async def spy_create_worktree(repo_path, task_id, base_branch=None, reset_branch=False):
        call_log.append(reset_branch)
        return await original_create(repo_path, task_id, base_branch, reset_branch)

    git_svc.create_worktree = spy_create_worktree

    # 1. First run (defaults to reset_branch=False)
    await engine.start_task(task.id)
    # Wait until past PREPARING
    for _ in range(30):
        t = task_svc.get_task(task.id)
        if t and t.status not in (TaskState.PENDING, TaskState.PREPARING):
            break
        await asyncio.sleep(0.1)

    await engine.stop_task(task.id)
    assert len(call_log) >= 1
    assert call_log[0] is False  # Safe default on start

    # 2. Retry with reset_branch=True
    call_log.clear()
    await engine.retry_task(task.id, reset_branch=True)

    for _ in range(30):
        t = task_svc.get_task(task.id)
        if t and t.status not in (TaskState.PENDING, TaskState.PREPARING):
            break
        await asyncio.sleep(0.1)

    await engine.stop_task(task.id)
    assert len(call_log) >= 1
    assert call_log[0] is True  # Successfully propagated True!

    # 3. Retry with default reset_branch=False
    call_log.clear()
    await engine.retry_task(task.id, reset_branch=False)

    for _ in range(30):
        t = task_svc.get_task(task.id)
        if t and t.status not in (TaskState.PENDING, TaskState.PREPARING):
            break
        await asyncio.sleep(0.1)

    await engine.stop_task(task.id)
    assert len(call_log) >= 1
    assert call_log[0] is False  # Successfully preserved False!


@pytest.mark.asyncio
async def test_retry_task_preserves_commits_by_default(setup_engine):
    """retry_task(..., reset_branch=False) preserves existing task branch commits."""
    engine: Orchestrator = setup_engine["engine"]
    task_svc: TaskService = setup_engine["task_svc"]

    task = await task_svc.create_task(
        project_id="proj-test",
        title="Commit Preservation Test",
        description="Verify existing commits are preserved by default"
    )

    await engine.start_task(task.id)
    for _ in range(30):
        t = task_svc.get_task(task.id)
        if t and t.current_worktree:
            break
        await asyncio.sleep(0.1)

    await engine.stop_task(task.id)

    wt = task_svc.get_task(task.id).current_worktree
    assert os.path.exists(wt)

    # Commit an intermediate file on the task branch
    intermediate_file = os.path.join(wt, "wip_feature.py")
    with open(intermediate_file, "w", encoding="utf-8") as f:
        f.write("# WIP commit to preserve\n")
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "WIP on task branch"], cwd=wt, check=True)

    # Retry with default reset_branch=False
    await engine.retry_task(task.id, reset_branch=False)
    for _ in range(30):
        t = task_svc.get_task(task.id)
        if t and t.status not in (TaskState.PENDING, TaskState.PREPARING):
            break
        await asyncio.sleep(0.1)

    await engine.stop_task(task.id)

    # Verify the committed file is still present and intact
    reloaded_wt = task_svc.get_task(task.id).current_worktree
    assert os.path.exists(os.path.join(reloaded_wt, "wip_feature.py"))
    with open(os.path.join(reloaded_wt, "wip_feature.py"), "r", encoding="utf-8") as f:
        assert "WIP commit to preserve" in f.read()


@pytest.mark.asyncio
async def test_retry_task_reset_branch_creates_backup_ref(setup_engine):
    """Explicit reset_branch=True with unmerged commits creates a backup ref before reset."""
    engine: Orchestrator = setup_engine["engine"]
    task_svc: TaskService = setup_engine["task_svc"]
    repo_dir = setup_engine["repo_dir"]

    task = await task_svc.create_task(
        project_id="proj-test",
        title="Reset Backup Test",
        description="Verify backup ref creation on reset"
    )

    await engine.start_task(task.id)
    for _ in range(30):
        t = task_svc.get_task(task.id)
        if t and t.current_worktree:
            break
        await asyncio.sleep(0.1)

    await engine.stop_task(task.id)

    wt = task_svc.get_task(task.id).current_worktree
    # Add unique commit on task branch
    feature_file = os.path.join(wt, "unique_work.txt")
    with open(feature_file, "w", encoding="utf-8") as f:
        f.write("Important work to be backed up\n")
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-m", "Unique work"], cwd=wt, check=True)

    # Retry with reset_branch=True
    await engine.retry_task(task.id, reset_branch=True)
    for _ in range(30):
        t = task_svc.get_task(task.id)
        if t and t.status not in (TaskState.PENDING, TaskState.PREPARING):
            break
        await asyncio.sleep(0.1)

    await engine.stop_task(task.id)

    # Active branch was reset to main, so unique_work.txt is no longer on active branch
    reloaded_wt = task_svc.get_task(task.id).current_worktree
    assert not os.path.exists(os.path.join(reloaded_wt, "unique_work.txt"))

    # But a backup ref exists under refs/forgeflow/backups/
    res = subprocess.run(
        ["git", "for-each-ref", "refs/forgeflow/backups/", "--format=%(refname)"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True
    )
    assert f"refs/forgeflow/backups/task_{task.id}_" in res.stdout


@pytest.mark.asyncio
async def test_retry_task_reset_branch_no_unique_commits(setup_engine):
    """reset_branch=True with no unique commits behaves correctly without error."""
    engine: Orchestrator = setup_engine["engine"]
    task_svc: TaskService = setup_engine["task_svc"]

    task = await task_svc.create_task(
        project_id="proj-test",
        title="Reset Clean Test",
        description="Verify reset without commits behaves correctly"
    )

    await engine.start_task(task.id)
    for _ in range(30):
        t = task_svc.get_task(task.id)
        if t and t.current_worktree:
            break
        await asyncio.sleep(0.1)

    await engine.stop_task(task.id)

    # Retry with reset_branch=True when no commits were made on task branch
    await engine.retry_task(task.id, reset_branch=True)
    for _ in range(30):
        t = task_svc.get_task(task.id)
        if t and t.status not in (TaskState.PENDING, TaskState.PREPARING):
            break
        await asyncio.sleep(0.1)

    await engine.stop_task(task.id)
    reloaded_t = task_svc.get_task(task.id)
    assert reloaded_t.status not in (TaskState.FAILED, TaskState.BLOCKED)


@pytest.mark.asyncio
async def test_iterative_repair_loop_does_not_reset_branch(setup_engine):
    """Normal iterative NEEDS_CHANGES -> IMPLEMENTING flow does NOT call create_worktree or reset branch."""
    engine: Orchestrator = setup_engine["engine"]
    task_svc: TaskService = setup_engine["task_svc"]
    git_svc: GitService = setup_engine["git_svc"]

    task = await task_svc.create_task(
        project_id="proj-test",
        title="Iterative Repair Test",
        description="Verify iterative loops preserve branch without re-preparing"
    )

    call_count = 0
    original_create = git_svc.create_worktree

    async def count_create_worktree(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_create(*args, **kwargs)

    git_svc.create_worktree = count_create_worktree

    # Transition task to NEEDS_CHANGES simulating failed test or reviewer request
    task = await task_svc.update_status(task.id, TaskState.NEEDS_CHANGES)
    task.iteration = 1
    task.max_iterations = 3
    task.current_worktree = os.path.join(setup_engine["ws_root"], f"forgeflow_task_{task.id}")
    task_svc.repo.save_task(task)

    # Process one state transition from NEEDS_CHANGES
    t = task_svc.get_task(task.id)
    handled = await engine._process_state(t)
    assert handled is True

    # Task transitions to IMPLEMENTING
    reloaded = task_svc.get_task(task.id)
    assert reloaded.status == TaskState.IMPLEMENTING

    # create_worktree was NEVER called during NEEDS_CHANGES -> IMPLEMENTING transition!
    assert call_count == 0
