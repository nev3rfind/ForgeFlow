import pytest
import asyncio
import os
from typing import AsyncGenerator, Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Task, TaskState, Project
from app.state import Database, Repository
from app.events.bus import EventBus
from app.services import ProjectService, TaskService
from app.git.service import GitService
from app.qa.runner import CommandRunner, CommandResult
from app.integrations.provider import AgentProvider
from app.integrations.abacus_adapter import AbacusReviewerProvider, AbacusReviewerError
from app.orchestration.engine import Orchestrator
from pydantic import BaseModel

class DummyAgentProvider(AgentProvider):
    def __init__(self, name="Worker"):
        self.name = name
        self.call_history: List[str] = []

    async def chat(self, prompt: str, schema: type[BaseModel], system_instruction: str, workspaces: list[str], model: str = None) -> Any:
        return None

    async def stream_chat(self, prompt: str, schema: type[BaseModel], system_instruction: str, workspaces: list[str], model: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        self.call_history.append(system_instruction)
        if "Investigator" in system_instruction:
            yield {"type": "structured_output", "data": {
                "root_cause_found": True,
                "summary": "Root cause",
                "evidence": "Evidence",
                "recommended_changes": "Changes"
            }}
        elif "Implementer" in system_instruction:
            yield {"type": "structured_output", "data": {
                "success": True,
                "summary": "Implemented",
                "files_modified": ["file.py"]
            }}
        elif "Reviewer" in system_instruction:
            yield {"type": "structured_output", "data": {
                "decision": "APPROVED",
                "summary": "Worker Approved",
                "findings": [],
                "required_changes": [],
                "confidence": 1.0
            }}

class MockReviewerProvider(AgentProvider):
    def __init__(self, decisions: List[str] = None, fail=False, malformed=False, timeout=False):
        self.name = "Abacus Reviewer"
        self.decisions = decisions or ["APPROVED"]
        self.call_count = 0
        self.fail = fail
        self.malformed = malformed
        self.timeout = timeout

    async def chat(self, prompt: str, schema: type[BaseModel], system_instruction: str, workspaces: list[str], model: str = None) -> Any:
        return None

    async def stream_chat(self, prompt: str, schema: type[BaseModel], system_instruction: str, workspaces: list[str], model: str = None) -> AsyncGenerator[Dict[str, Any], None]:
        self.call_count += 1
        if self.timeout:
            raise asyncio.TimeoutError("Reviewer timeout")
        if self.fail:
            raise AbacusReviewerError("Abacus CLI crashed with error")
        if self.malformed:
            raise AbacusReviewerError("Malformed JSON output from Abacus reviewer")

        idx = min(self.call_count - 1, len(self.decisions) - 1)
        decision = self.decisions[idx]
        yield {"type": "text", "content": f"Decision: {decision}"}
        yield {"type": "structured_output", "data": {
            "decision": decision,
            "summary": f"Review decision {decision}",
            "findings": [] if decision == "APPROVED" else ["Needs work"],
            "required_changes": [] if decision == "APPROVED" else ["Refactor code"],
            "confidence": 0.9
        }}

@pytest.fixture
def env(tmp_path):
    db_file = str(tmp_path / "test.db")
    db = Database(db_file)
    repo = Repository(db)
    bus = EventBus()
    project_svc = ProjectService(repo)
    task_svc = TaskService(repo, bus)
    
    git_svc = MagicMock(spec=GitService)
    git_svc.create_worktree = AsyncMock(return_value=str(tmp_path / "worktree"))
    git_svc.remove_worktree = AsyncMock()

    qa_runner = MagicMock(spec=CommandRunner)
    qa_runner.run = AsyncMock(return_value=CommandResult("test", 0, "OK", "", 0.1))

    return {
        "repo": repo,
        "bus": bus,
        "project_svc": project_svc,
        "task_svc": task_svc,
        "git_svc": git_svc,
        "qa_runner": qa_runner,
        "tmp_path": tmp_path
    }

async def run_and_wait(orchestrator: Orchestrator, task_id: str):
    await orchestrator.start_task(task_id)
    handle = orchestrator.active_tasks.get(task_id)
    if handle:
        await handle

# A. Antigravity remains implementation provider
# B. Abacus is used for REVIEW when enabled
@pytest.mark.asyncio
async def test_antigravity_implements_and_abacus_reviews(env):
    worker = DummyAgentProvider(name="Antigravity Worker")
    reviewer = MockReviewerProvider(decisions=["APPROVED"])

    orchestrator = Orchestrator(
        task_service=env["task_svc"],
        project_service=env["project_svc"],
        git_service=env["git_svc"],
        event_bus=env["bus"],
        provider=worker,
        qa_runner=env["qa_runner"],
        reviewer_provider=reviewer
    )

    project = env["project_svc"].create_project("TestProj", str(env["tmp_path"]), "python")
    task = await env["task_svc"].create_task(project.id, "Title", "Desc")

    await run_and_wait(orchestrator, task.id)

    # Verify worker was called for investigation and implementation
    assert any("Investigator" in c for c in worker.call_history)
    assert any("Implementer" in c for c in worker.call_history)
    # Verify worker was NOT called for review
    assert not any("Reviewer" in c for c in worker.call_history)
    # Verify Abacus reviewer was called for review
    assert reviewer.call_count == 1

# C. REVIEW_RESULT = APPROVED reaches APPROVED then COMPLETED
@pytest.mark.asyncio
async def test_review_approved_completes(env):
    worker = DummyAgentProvider()
    reviewer = MockReviewerProvider(decisions=["APPROVED"])

    orchestrator = Orchestrator(
        task_service=env["task_svc"],
        project_service=env["project_svc"],
        git_service=env["git_svc"],
        event_bus=env["bus"],
        provider=worker,
        qa_runner=env["qa_runner"],
        reviewer_provider=reviewer
    )

    project = env["project_svc"].create_project("P", str(env["tmp_path"]), "python")
    task = await env["task_svc"].create_task(project.id, "T", "D")

    await run_and_wait(orchestrator, task.id)

    final_task = env["task_svc"].get_task(task.id)
    assert final_task.status == TaskState.COMPLETED

    # Check events to ensure APPROVED was entered
    events = env["repo"].get_events(task.id)
    statuses = [e.payload.get("new_status") for e in events if e.event_type == "STATE_CHANGED"]
    assert "APPROVED" in statuses
    assert "COMPLETED" in statuses
    assert statuses.index("APPROVED") < statuses.index("COMPLETED")

# D. REVIEW_RESULT = NEEDS_CHANGES returns to IMPLEMENTING
# E. Multiple review cycles work
@pytest.mark.asyncio
async def test_multiple_review_cycles_until_approved(env):
    worker = DummyAgentProvider()
    # Reject once, then approve
    reviewer = MockReviewerProvider(decisions=["NEEDS_CHANGES", "APPROVED"])

    orchestrator = Orchestrator(
        task_service=env["task_svc"],
        project_service=env["project_svc"],
        git_service=env["git_svc"],
        event_bus=env["bus"],
        provider=worker,
        qa_runner=env["qa_runner"],
        reviewer_provider=reviewer
    )

    project = env["project_svc"].create_project("P", str(env["tmp_path"]), "python")
    task = await env["task_svc"].create_task(project.id, "T", "D", max_iterations=3)

    await run_and_wait(orchestrator, task.id)

    final_task = env["task_svc"].get_task(task.id)
    assert final_task.status == TaskState.COMPLETED
    assert final_task.iteration == 2
    assert reviewer.call_count == 2

# F. max_iterations eventually produces BLOCKED
@pytest.mark.asyncio
async def test_max_iterations_produces_blocked(env):
    worker = DummyAgentProvider()
    # Always reject
    reviewer = MockReviewerProvider(decisions=["NEEDS_CHANGES", "NEEDS_CHANGES", "NEEDS_CHANGES"])

    orchestrator = Orchestrator(
        task_service=env["task_svc"],
        project_service=env["project_svc"],
        git_service=env["git_svc"],
        event_bus=env["bus"],
        provider=worker,
        qa_runner=env["qa_runner"],
        reviewer_provider=reviewer
    )

    project = env["project_svc"].create_project("P", str(env["tmp_path"]), "python")
    task = await env["task_svc"].create_task(project.id, "T", "D", max_iterations=2)

    await run_and_wait(orchestrator, task.id)

    final_task = env["task_svc"].get_task(task.id)
    assert final_task.status == TaskState.BLOCKED
    assert "max iterations" in (final_task.error_information or "")

# G. Abacus CLI failure does not falsely approve (with fallback disabled)
@pytest.mark.asyncio
async def test_abacus_cli_failure_no_fallback_fails(env):
    worker = DummyAgentProvider()
    reviewer = MockReviewerProvider(fail=True)

    orchestrator = Orchestrator(
        task_service=env["task_svc"],
        project_service=env["project_svc"],
        git_service=env["git_svc"],
        event_bus=env["bus"],
        provider=worker,
        qa_runner=env["qa_runner"],
        reviewer_provider=reviewer,
        fallback_enabled=False
    )

    project = env["project_svc"].create_project("P", str(env["tmp_path"]), "python")
    task = await env["task_svc"].create_task(project.id, "T", "D")

    await run_and_wait(orchestrator, task.id)

    final_task = env["task_svc"].get_task(task.id)
    assert final_task.status == TaskState.FAILED
    assert "Reviewer failed" in (final_task.error_information or "")

# H. Abacus malformed JSON does not falsely approve
@pytest.mark.asyncio
async def test_abacus_malformed_json_fails_without_fallback(env):
    worker = DummyAgentProvider()
    reviewer = MockReviewerProvider(malformed=True)

    orchestrator = Orchestrator(
        task_service=env["task_svc"],
        project_service=env["project_svc"],
        git_service=env["git_svc"],
        event_bus=env["bus"],
        provider=worker,
        qa_runner=env["qa_runner"],
        reviewer_provider=reviewer,
        fallback_enabled=False
    )

    project = env["project_svc"].create_project("P", str(env["tmp_path"]), "python")
    task = await env["task_svc"].create_task(project.id, "T", "D")

    await run_and_wait(orchestrator, task.id)

    final_task = env["task_svc"].get_task(task.id)
    assert final_task.status == TaskState.FAILED
    assert "Malformed JSON" in (final_task.error_information or "")

# I. Abacus timeout is handled
@pytest.mark.asyncio
async def test_abacus_timeout_fails_without_fallback(env):
    worker = DummyAgentProvider()
    reviewer = MockReviewerProvider(timeout=True)

    orchestrator = Orchestrator(
        task_service=env["task_svc"],
        project_service=env["project_svc"],
        git_service=env["git_svc"],
        event_bus=env["bus"],
        provider=worker,
        qa_runner=env["qa_runner"],
        reviewer_provider=reviewer,
        fallback_enabled=False
    )

    project = env["project_svc"].create_project("P", str(env["tmp_path"]), "python")
    task = await env["task_svc"].create_task(project.id, "T", "D")

    await run_and_wait(orchestrator, task.id)

    final_task = env["task_svc"].get_task(task.id)
    assert final_task.status == TaskState.FAILED
    assert "Reviewer timeout" in (final_task.error_information or "")

# J. Non-zero test command causes the correct failure/fix path
@pytest.mark.asyncio
async def test_failed_tests_reroutes_to_needs_changes(env):
    worker = DummyAgentProvider()
    reviewer = MockReviewerProvider()

    env["qa_runner"].run = AsyncMock(side_effect=[
        CommandResult("pytest", 1, "FAILED test_foo.py", "AssertionError", 0.1),
        CommandResult("pytest", 0, "PASSED", "", 0.1)
    ])

    orchestrator = Orchestrator(
        task_service=env["task_svc"],
        project_service=env["project_svc"],
        git_service=env["git_svc"],
        event_bus=env["bus"],
        provider=worker,
        qa_runner=env["qa_runner"],
        reviewer_provider=reviewer
    )

    project = env["project_svc"].create_project("P", str(env["tmp_path"]), "python", test_command="pytest")
    task = await env["task_svc"].create_task(project.id, "T", "D", max_iterations=3)

    await run_and_wait(orchestrator, task.id)

    final_task = env["task_svc"].get_task(task.id)
    assert final_task.status == TaskState.COMPLETED
    assert final_task.iteration == 2

    # Verify event stream records TEST_RESULT with exit_code 1
    events = env["repo"].get_events(task.id)
    test_events = [e for e in events if e.event_type == "TEST_RESULT"]
    assert len(test_events) == 2
    assert test_events[0].payload["exit_code"] == 1
    assert test_events[1].payload["exit_code"] == 0

# K. stop_task cannot raise the identified KeyError/race
@pytest.mark.asyncio
async def test_stop_task_no_keyerror(env):
    worker = DummyAgentProvider()
    orchestrator = Orchestrator(
        task_service=env["task_svc"],
        project_service=env["project_svc"],
        git_service=env["git_svc"],
        event_bus=env["bus"],
        provider=worker,
        qa_runner=env["qa_runner"]
    )

    project = env["project_svc"].create_project("P", str(env["tmp_path"]), "python")
    task = await env["task_svc"].create_task(project.id, "T", "D")

    await orchestrator.start_task(task.id)
    await orchestrator.stop_task(task.id)

    final_task = env["task_svc"].get_task(task.id)
    assert final_task.status == TaskState.STOPPED
    # Calling stop_task again should be a clean no-op, never raising KeyError
    await orchestrator.stop_task(task.id)
