"""Real end-to-end test for ForgeFlow with AgyProvider.

Runs against C:\\Users\\ddona\\ForgeFlow-test-project.
Uses FORGEFLOW_IMPLEMENTATION_PROVIDER=agy with local Antigravity authentication.
No GEMINI_API_KEY required.

Usage:
    $env:FORGEFLOW_IMPLEMENTATION_PROVIDER = "agy"
    .venv\\Scripts\\python.exe -u e2e_test.py
"""
import asyncio
import os
import sys

# Add repo root to path so imports resolve without installing the package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("FORGEFLOW_IMPLEMENTATION_PROVIDER", "agy")

from app.config import settings
from app.state import Database, Repository
from app.events.bus import EventBus
from app.services import ProjectService, TaskService
from app.git.service import GitService
from app.qa.runner import CommandRunner
from app.orchestration.engine import Orchestrator, TERMINAL_STATES
from app.integrations.agy_adapter import AgyProvider
from app.integrations.abacus_adapter import AbacusReviewerProvider
from app.models import TaskState

TEST_REPO = r"C:\Users\ddona\ForgeFlow-test-project"
UNTOUCHED_WORKTREE = r"C:\Users\ddona\ForgeFlow-test-worktree"


async def run_e2e():
    print(f"Provider: {settings.implementation_provider}")

    db = Database(settings.database_path)
    repo = Repository(db)
    event_bus = EventBus()
    project_service = ProjectService(repo)
    task_service = TaskService(repo, event_bus)
    git_service = GitService(workspace_root=settings.workspace_root)
    qa_runner = CommandRunner()
    provider = AgyProvider()

    reviewer_provider = None
    if settings.abacus_reviewer_enabled:
        reviewer_provider = AbacusReviewerProvider(
            cli_path=settings.abacusai_path or None,
            timeout=settings.abacus_timeout,
            fallback_enabled=settings.abacus_reviewer_fallback_enabled,
            review_mode=settings.abacus_review_mode,
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
        review_mode=settings.abacus_review_mode,
    )

    # Locate or create the test project
    projects = project_service.list_projects()
    test_project = next((p for p in projects if TEST_REPO in (p.repository or "")), None)
    if not test_project:
        print("Creating test project...")
        test_project = project_service.create_project(
            name="E2E Test Project",
            repository_path=TEST_REPO,
            type="python",
            test_command="pytest",
        )
    print(f"Project id: {test_project.id}")

    # Create a new task that requires an actual code change (not just a text file)
    task = await task_service.create_task(
        project_id=test_project.id,
        title="Add a multiply utility",
        description=(
            "Create a new Python file named 'multiply.py' containing a single function "
            "'multiply(a, b)' that returns the product of a and b. "
            "Also create 'test_multiply.py' with at least one pytest test that verifies "
            "multiply(3, 4) == 12."
        ),
        requirements="Python only. Use pytest. No third-party packages.",
    )
    print(f"Task id: {task.id}")

    # Track events with an async callback (required by EventBus)
    events_received: list = []

    async def on_event(event):
        events_received.append(event)
        etype = event.event_type
        if etype == "AGENT_CHUNK":
            chunk = event.payload or {}
            if chunk.get("type") == "text":
                snippet = (chunk.get("content") or "")[:80]
                print(f"  [AGENT TEXT] {snippet}")
            elif chunk.get("type") == "tool_call":
                print(f"  [TOOL CALL] {chunk.get('name')}")
        elif etype == "STATE_CHANGED":
            print(f"  [STATE] {event.payload.get('status')}")
        elif etype in ("TEST_RESULT", "REVIEWER_FALLBACK", "ARTIFACT"):
            print(f"  [{etype}]")

    event_bus.subscribe(task.id, on_event)

    print("\nStarting task...")
    await orchestrator.start_task(task.id)

    # Poll until terminal
    while True:
        current = task_service.get_task(task.id)
        if not current or current.status in TERMINAL_STATES:
            task = current
            break
        await asyncio.sleep(2)

    event_bus.unsubscribe(task.id, on_event)

    print(f"\nFinal status: {task.status}")
    print(f"Iterations: {task.iteration}/{task.max_iterations}")
    if task.error_information:
        print(f"Error: {task.error_information}")

    # Event summary
    print(f"\nTotal events received: {len(events_received)}")
    for et in ("STATE_CHANGED", "AGENT_CHUNK", "TOOL_CALL", "TEST_RESULT", "ARTIFACT"):
        count = sum(1 for e in events_received if e.event_type == et)
        if count:
            print(f"  {et}: {count}")

    # Verify manual worktree was not touched
    if os.path.exists(UNTOUCHED_WORKTREE):
        print(f"\nUntouched worktree exists: {UNTOUCHED_WORKTREE} ✓")
    else:
        print(f"\nWarning: {UNTOUCHED_WORKTREE} not found (may have been removed externally)")

    if task.status == TaskState.COMPLETED:
        print("\n✓ E2E test PASSED")
        return 0
    else:
        print("\n✗ E2E test FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_e2e())
    sys.exit(exit_code)
