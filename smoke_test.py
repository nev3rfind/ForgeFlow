import asyncio
from app.state import Database, Repository
from app.events.bus import EventBus
from app.services import ProjectService, TaskService
from app.git.service import GitService
from app.qa.runner import CommandRunner
from app.integrations.provider import AgentProvider
from app.orchestration.engine import Orchestrator
from pydantic import BaseModel
from typing import AsyncGenerator, Dict, Any

class MockWorkerProvider(AgentProvider):
    def __init__(self):
        self.name = "Antigravity Worker"

    async def chat(self, prompt: str, schema: type[BaseModel], system_instruction: str, workspaces: list[str]) -> Any:
        pass
        
    async def stream_chat(self, prompt: str, schema: type[BaseModel], system_instruction: str, workspaces: list[str]) -> AsyncGenerator[Dict[str, Any], None]:
        if "Investigator" in system_instruction:
            yield {"type": "text", "content": "I found the root cause."}
            yield {"type": "structured_output", "data": {
                "root_cause_found": True,
                "summary": "Mock root cause",
                "evidence": "Mock evidence",
                "recommended_changes": "Mock changes"
            }}
        elif "Implementer" in system_instruction:
            yield {"type": "text", "content": "I implemented the changes."}
            yield {"type": "structured_output", "data": {
                "success": True,
                "summary": "Mock implementation",
                "files_modified": ["test_app.py"]
            }}
        elif "Reviewer" in system_instruction:
            yield {"type": "text", "content": "Worker reviewed"}
            yield {"type": "structured_output", "data": {
                "decision": "APPROVED",
                "summary": "Worker review approved",
                "findings": [],
                "required_changes": [],
                "confidence": 1.0
            }}
        else:
            yield {"type": "structured_output", "data": {}}

class MockAbacusReviewer(AgentProvider):
    def __init__(self):
        self.name = "Abacus Reviewer"

    async def chat(self, prompt: str, schema: type[BaseModel], system_instruction: str, workspaces: list[str]) -> Any:
        pass

    async def stream_chat(self, prompt: str, schema: type[BaseModel], system_instruction: str, workspaces: list[str]) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"type": "text", "content": "Abacus AI Senior Reviewer evaluated worktree context and diff."}
        yield {"type": "structured_output", "data": {
            "decision": "APPROVED",
            "summary": "Abacus independent review: Approved without regressions.",
            "findings": ["Clean implementation", "Tests passed"],
            "required_changes": [],
            "confidence": 0.98
        }}

async def run_smoke_test():
    print("=== FORGEFLOW SMOKE TEST ===")
    print("Initializing test database...")
    db = Database("test_forgeflow.db")
    repo = Repository(db)
    bus = EventBus()
    
    project_svc = ProjectService(repo)
    task_svc = TaskService(repo, bus)
    git_svc = GitService(workspace_root="./runtime/test_worktrees")
    qa = CommandRunner()
    
    worker = MockWorkerProvider()
    abacus_reviewer = MockAbacusReviewer()

    orchestrator = Orchestrator(
        task_service=task_svc,
        project_service=project_svc,
        git_service=git_svc,
        event_bus=bus,
        provider=worker,
        qa_runner=qa,
        reviewer_provider=abacus_reviewer
    )
    
    print("Creating project...")
    p = project_svc.create_project("Smoke Test Project", "C:\\Users\\ddona\\TestRepo", "python", test_command="pytest", default_branch="master")
    
    print("Creating task...")
    t = await task_svc.create_task(p.id, "Fix addition bug", "Make it return correct values")
    
    print("Starting task with independent Abacus reviewer...")
    await orchestrator.start_task(t.id)
    
    # Wait for completion
    for _ in range(50):
        await asyncio.sleep(0.5)
        curr = task_svc.get_task(t.id)
        print(f"Task status: {curr.status} | Agent: {curr.current_agent}")
        if curr.status in ["COMPLETED", "FAILED", "BLOCKED", "STOPPED"]:
            break

    print(f"Final status: {curr.status}")
    if curr.status != "COMPLETED":
        print(f"Error: {curr.error_information}")
        raise Exception("Task did not complete successfully")

    # Verify event audit trail
    events = repo.get_events(t.id)
    agents_seen = {e.payload.get("agent") for e in events if e.payload.get("agent")}
    print(f"Agents observed in event trail: {agents_seen}")
    assert "Antigravity / Investigator" in agents_seen
    assert "Antigravity / Implementer" in agents_seen
    assert "Abacus Reviewer" in agents_seen

    print("=== SMOKE TEST PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
