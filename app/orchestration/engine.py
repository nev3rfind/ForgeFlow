import asyncio
import logging
import os
from typing import Dict, Optional
from app.models import Task, TaskState, Artifact
from app.roles import role_router
from app.services.task_service import TaskService
from app.services.project_service import ProjectService
from app.git.service import GitService
from app.events.bus import EventBus
from app.integrations.provider import AgentProvider
from app.agents.roles import (
    INVESTIGATOR_SYSTEM, IMPLEMENTER_SYSTEM, REVIEWER_SYSTEM,
    InvestigationResult, ImplementationResult, ReviewResult
)
from app.qa.runner import CommandRunner

logger = logging.getLogger("forgeflow.orchestration")

TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.STOPPED, TaskState.BLOCKED}

class Orchestrator:
    
    def get_routed_provider(self, role: str):
        cfg = role_router.get_role(role)
        provider_name = cfg.provider
        model = cfg.model
        
        provider_obj = self.provider
        if provider_name == "abacus":
            provider_obj = self.reviewer_provider or self.provider
        elif provider_name == "agy_desktop":
            from app.integrations.agy_desktop_adapter import AgyDesktopAdapter
            provider_obj = AgyDesktopAdapter()
            
        # Emit a quick internal event to notify the frontend which agent/role/model is active
        # The frontend can capture this to update the UI
        agent_name = "Abacus AI" if provider_name == "abacus" else ("Google Antigravity (RPA)" if provider_name == "agy_desktop" else "Google Antigravity")
        return provider_obj, model, agent_name

    def __init__(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        git_service: GitService,
        event_bus: EventBus,
        provider: AgentProvider,
        qa_runner: CommandRunner,
        reviewer_provider: Optional[AgentProvider] = None,
        fallback_enabled: bool = True,
        review_mode: str = "every_iteration"
    ):
        self.task_service = task_service
        self.project_service = project_service
        self.git_service = git_service
        self.event_bus = event_bus
        self.provider = provider
        self.reviewer_provider = reviewer_provider or provider
        self.fallback_enabled = fallback_enabled
        self.review_mode = review_mode
        self.qa_runner = qa_runner
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.cancellation_tokens: Dict[str, asyncio.Event] = {}
        self.paused: set = set()
        self.paused_status: Dict[str, TaskState] = {}
        self.reset_branch_tasks: set = set()

    async def start_task(self, task_id: str):
        if task_id in self.active_tasks:
            return
        
        self.cancellation_tokens[task_id] = asyncio.Event()
        task_coro = self._run_task_loop(task_id)
        self.active_tasks[task_id] = asyncio.create_task(task_coro)

    async def stop_task(self, task_id: str):
        if task_id in self.cancellation_tokens:
            self.cancellation_tokens[task_id].set()
        task_handle = self.active_tasks.get(task_id)
        if task_handle:
            try:
                await task_handle
            except Exception:
                pass
        self.active_tasks.pop(task_id, None)
        self.cancellation_tokens.pop(task_id, None)
        self.paused.discard(task_id)
        self.paused_status.pop(task_id, None)
        # Only mark STOPPED if the task is not already in a terminal state.
        task = self.task_service.get_task(task_id)
        if task and task.status not in TERMINAL_STATES:
            await self.task_service.update_status(task_id, TaskState.STOPPED)

    async def pause_task(self, task_id: str):
        task = self.task_service.get_task(task_id)
        if not task or task.status in TERMINAL_STATES:
            return
        self.paused.add(task_id)
        self.paused_status[task_id] = task.status
        await self.task_service.update_status(task_id, TaskState.PAUSED)

    async def resume_task(self, task_id: str):
        if task_id in self.paused:
            self.paused.discard(task_id)
            prev = self.paused_status.pop(task_id, TaskState.PENDING)
            await self.task_service.update_status(task_id, prev)

    async def retry_task(self, task_id: str, reset_branch: bool = False):
        task = self.task_service.get_task(task_id)
        if not task:
            return
        if task_id in self.active_tasks:
            # Task is still running; retrying would silently no-op.
            raise RuntimeError(f"Task {task_id} is still active; stop it before retrying")

        if reset_branch:
            self.reset_branch_tasks.add(task_id)
        else:
            self.reset_branch_tasks.discard(task_id)

        # Archive historical disk artifacts before the new run
        workspace_root = getattr(self.git_service, "workspace_root", None) or "./runtime/worktrees"
        artifacts_dir = os.path.join(workspace_root, "artifacts", task.id)
        if os.path.exists(artifacts_dir):
            import time
            import shutil
            history_dir = os.path.join(artifacts_dir, "history", str(int(time.time())))
            for fname in os.listdir(artifacts_dir):
                fpath = os.path.join(artifacts_dir, fname)
                if os.path.isfile(fpath):
                    os.makedirs(history_dir, exist_ok=True)
                    try:
                        shutil.copy2(fpath, os.path.join(history_dir, fname))
                    except Exception:
                        pass

        task.status = TaskState.PENDING
        task.iteration = 1
        task.error_information = None
        task.completed_at = None
        task.started_at = None
        task.current_agent = None
        task.current_worktree = None
        self.task_service.repo.save_task(task)
        await self.start_task(task_id)

    async def _run_task_loop(self, task_id: str):
        try:
            while True:
                if self.cancellation_tokens.get(task_id) and self.cancellation_tokens[task_id].is_set():
                    break

                if task_id in self.paused:
                    await asyncio.sleep(0.2)
                    continue
                    
                task = self.task_service.get_task(task_id)
                if not task or task.status in TERMINAL_STATES:
                    break

                handled = await self._process_state(task)
                if not handled:
                    # No branch matched (e.g. PAUSED/STOPPED set externally).
                    # Break instead of spinning the loop at full speed.
                    logger.warning(
                        f"Task {task_id} is in unhandled state {task.status}; stopping loop"
                    )
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Unhandled error in task loop {task_id}: {e}")
            await self.task_service.update_status(task_id, TaskState.FAILED, error=str(e))
        finally:
            self.active_tasks.pop(task_id, None)
            self.cancellation_tokens.pop(task_id, None)
            self.paused.discard(task_id)
            self.paused_status.pop(task_id, None)
            self.reset_branch_tasks.discard(task_id)

    async def _write_artifact(self, task: Task, name: str, content: str) -> Artifact:
        workspace_root = getattr(self.git_service, "workspace_root", None) or "./runtime/worktrees"
        artifacts_dir = os.path.join(workspace_root, "artifacts", task.id)
        os.makedirs(artifacts_dir, exist_ok=True)
        path = os.path.join(artifacts_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        # Also mirror into the worktree so the reviewer can read it as context.
        if task.current_worktree and os.path.isdir(task.current_worktree):
            try:
                with open(os.path.join(task.current_worktree, name), "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception:
                pass
        artifact = Artifact(task_id=task.id, name=name, path=path)
        self.task_service.repo.save_artifact(artifact)
        await self.task_service.emit_event(task.id, "ARTIFACT", {"name": name, "path": path})
        return artifact

    async def _append_artifact(self, task: Task, name: str, content: str) -> Artifact:
        workspace_root = getattr(self.git_service, "workspace_root", None) or "./runtime/worktrees"
        artifacts_dir = os.path.join(workspace_root, "artifacts", task.id)
        os.makedirs(artifacts_dir, exist_ok=True)
        path = os.path.join(artifacts_dir, name)
        
        mode = "a" if os.path.exists(path) else "w"
        with open(path, mode, encoding="utf-8") as f:
            if mode == "a":
                f.write("\n\n")
            f.write(content)
            
        # Also mirror into the worktree
        if task.current_worktree and os.path.isdir(task.current_worktree):
            try:
                wt_path = os.path.join(task.current_worktree, name)
                wt_mode = "a" if os.path.exists(wt_path) else "w"
                with open(wt_path, wt_mode, encoding="utf-8") as f:
                    if wt_mode == "a":
                        f.write("\n\n")
                    f.write(content)
            except Exception:
                pass
                
        artifact = Artifact(task_id=task.id, name=name, path=path)
        self.task_service.repo.save_artifact(artifact)
        await self.task_service.emit_event(task.id, "ARTIFACT", {"name": name, "path": path})
        return artifact

    async def _process_state(self, task: Task) -> bool:
        """Advance the task by one state. Returns False if no branch matched."""
        project = self.project_service.get_project(task.project_id)
        if not project:
            raise Exception("Project not found")

        if task.status == TaskState.PENDING:
            await self.task_service.update_status(task.id, TaskState.PREPARING)
            
        elif task.status == TaskState.PREPARING:
            should_reset = task.id in self.reset_branch_tasks
            self.reset_branch_tasks.discard(task.id)
            worktree_path = await self.git_service.create_worktree(
                project.repository, task.id, project.default_branch, reset_branch=should_reset
            )
            task = self.task_service.get_task(task.id)
            task.current_worktree = worktree_path
            self.task_service.repo.save_task(task)
            await self._write_artifact(task, "TASK.md", self._task_markdown(task))
            await self.task_service.update_status(task.id, TaskState.INVESTIGATING)
            
        elif task.status == TaskState.INVESTIGATING:
            prompt = f"Task: {task.title}\nDescription: {task.description}\nPlease investigate the root cause."
            provider_obj, model, agent_name = self.get_routed_provider("investigator")
            await self.task_service.update_status(task.id, TaskState.INVESTIGATING, agent=agent_name + " / Investigator")
            
            result = None
            async for chunk in provider_obj.stream_chat(prompt, InvestigationResult, INVESTIGATOR_SYSTEM, [task.current_worktree], model=model):
                if self.cancellation_tokens.get(task.id) and self.cancellation_tokens[task.id].is_set():
                    return True
                await self.task_service.emit_event(task.id, "AGENT_CHUNK", chunk)
                if chunk["type"] == "structured_output":
                    result = chunk["data"]
            
            if result:
                await self._write_artifact(task, "ROOT_CAUSE.md", self._root_cause_markdown(result))
                await self.task_service.update_status(task.id, TaskState.ROOT_CAUSE_READY)
            else:
                await self.task_service.update_status(task.id, TaskState.FAILED, error="No investigation result")

        elif task.status == TaskState.ROOT_CAUSE_READY:
            await self.task_service.update_status(task.id, TaskState.ROOT_CAUSE_REVIEW)
            
        elif task.status == TaskState.ROOT_CAUSE_REVIEW:
            # Transition to implementation
            await self.task_service.update_status(task.id, TaskState.IMPLEMENTING)

        elif task.status == TaskState.IMPLEMENTING:
            prompt = f"Task: {task.title}\nDescription: {task.description}\nIteration: {task.iteration}/{task.max_iterations}\nPlease implement the changes."
            provider_obj, model, agent_name = self.get_routed_provider("coder")
            await self.task_service.update_status(task.id, TaskState.IMPLEMENTING, agent=agent_name + " / Implementer")
            
            result = None
            async for chunk in provider_obj.stream_chat(prompt, ImplementationResult, IMPLEMENTER_SYSTEM, [task.current_worktree], model=model):
                if self.cancellation_tokens.get(task.id) and self.cancellation_tokens[task.id].is_set():
                    return True
                await self.task_service.emit_event(task.id, "AGENT_CHUNK", chunk)
                if chunk["type"] == "structured_output":
                    result = chunk["data"]
            
            if result:
                await self._write_artifact(task, "IMPLEMENTATION.md", self._implementation_markdown(result))
                await self.task_service.update_status(task.id, TaskState.IMPLEMENTATION_READY)
            else:
                await self.task_service.update_status(task.id, TaskState.FAILED, error="No implementation result")

        elif task.status == TaskState.IMPLEMENTATION_READY:
            await self.task_service.update_status(task.id, TaskState.TESTING)

        elif task.status == TaskState.TESTING:
            if project.test_command:
                res = await self.qa_runner.run(project.test_command, task.current_worktree)
                await self.task_service.emit_event(task.id, "TEST_RESULT", {
                    "exit_code": res.exit_code,
                    "stdout": res.stdout,
                    "stderr": res.stderr
                })
                await self._write_artifact(task, "QA.md", self._qa_markdown(project.test_command, res))
                if res.exit_code != 0:
                    task = self.task_service.get_task(task.id)
                    if task.iteration >= task.max_iterations:
                        await self.task_service.update_status(
                            task.id,
                            TaskState.BLOCKED,
                            error=f"Tests failed (exit code {res.exit_code}) on final iteration {task.iteration}: {res.stderr or res.stdout}"
                        )
                        return True
                    else:
                        task.iteration += 1
                        self.task_service.repo.save_task(task)
                        await self.task_service.update_status(
                            task.id,
                            TaskState.NEEDS_CHANGES,
                            error=f"Tests failed with exit code {res.exit_code}. Iteration incremented to {task.iteration}."
                        )
                        return True
            await self.task_service.update_status(task.id, TaskState.QA)
            
        elif task.status == TaskState.QA:
            await self.task_service.update_status(task.id, TaskState.REVIEW)

        elif task.status == TaskState.REVIEW:
            reviewer_name = getattr(self.reviewer_provider, "name", "Reviewer")

            # review_mode gates whether the reviewer runs at all.
            # "every_iteration" (default) always reviews; "final_only" reviews
            # only on the last iteration; "never" skips review entirely.
            mode = (self.review_mode or "every_iteration").strip().lower()
            if mode == "never":
                await self.task_service.emit_event(task.id, "REVIEW_SKIPPED", {"reason": "review_mode=never"})
                await self.task_service.update_status(task.id, TaskState.APPROVED)
                return True
            if mode == "final_only" and task.iteration < task.max_iterations:
                await self.task_service.emit_event(task.id, "REVIEW_SKIPPED", {
                    "reason": "review_mode=final_only",
                    "iteration": task.iteration,
                    "max_iterations": task.max_iterations
                })
                await self.task_service.update_status(task.id, TaskState.APPROVED)
                return True

            prompt = (
                f"Task: {task.title}\n"
                f"Description: {task.description}\n"
                f"Iteration: {task.iteration} of {task.max_iterations}\n"
                f"Please review the implementation in the worktree against task requirements and test results."
            )
            provider_obj, model, agent_name = self.get_routed_provider("reviewer")
            await self.task_service.update_status(task.id, TaskState.REVIEW, agent=agent_name + " / Reviewer")
            
            result = None
            review_failed = False
            error_message = None

            try:
                async for chunk in provider_obj.stream_chat(prompt, ReviewResult, REVIEWER_SYSTEM, [task.current_worktree], model=model):
                    if self.cancellation_tokens.get(task.id) and self.cancellation_tokens[task.id].is_set():
                        return True
                    await self.task_service.emit_event(task.id, "AGENT_CHUNK", chunk)
                    if chunk["type"] == "structured_output":
                        result = chunk["data"]
            except Exception as e:
                review_failed = True
                error_message = str(e)
                logger.warning(f"Primary reviewer {reviewer_name} failed: {error_message}")

            # If primary reviewer failed, check fallback
            if review_failed:
                if self.fallback_enabled and self.reviewer_provider != self.provider:
                    fallback_agent = "Antigravity / Reviewer (Fallback)"
                    await self.task_service.emit_event(task.id, "REVIEWER_FALLBACK", {
                        "primary_error": error_message,
                        "fallback_agent": fallback_agent
                    })
                    await self.task_service.update_status(task.id, TaskState.REVIEW, agent=fallback_agent)
                    try:
                        async for chunk in self.provider.stream_chat(prompt, ReviewResult, REVIEWER_SYSTEM, [task.current_worktree]):
                            if self.cancellation_tokens.get(task.id) and self.cancellation_tokens[task.id].is_set():
                                return True
                            await self.task_service.emit_event(task.id, "AGENT_CHUNK", chunk)
                            if chunk["type"] == "structured_output":
                                result = chunk["data"]
                    except Exception as fb_err:
                        await self.task_service.update_status(
                            task.id,
                            TaskState.FAILED,
                            error=f"Reviewer failed ({error_message}) and fallback failed: {fb_err}"
                        )
                        return True
                else:
                    # NEVER falsely approve on reviewer failure
                    await self.task_service.update_status(
                        task.id,
                        TaskState.FAILED,
                        error=f"Reviewer failed: {error_message}"
                    )
                    return True
            
            if result:
                await self._write_artifact(task, "REVIEW.md", self._review_markdown(result))
                await self._append_artifact(task, "REVIEW_HISTORY.md", f"## Iteration {task.iteration}\n" + self._review_markdown(result))
                decision = str(result.get("decision", "")).strip().upper()
                if decision == "APPROVED":
                    await self.task_service.update_status(task.id, TaskState.APPROVED)
                elif decision == "NEEDS_CHANGES":
                    task = self.task_service.get_task(task.id)
                    if task.iteration >= task.max_iterations:
                        await self.task_service.update_status(
                            task.id,
                            TaskState.BLOCKED,
                            error=f"Reviewer requested changes but reached max iterations ({task.max_iterations}): {result.get('summary')}"
                        )
                    else:
                        task.iteration += 1
                        self.task_service.repo.save_task(task)
                        await self.task_service.update_status(task.id, TaskState.NEEDS_CHANGES)
                elif decision == "BLOCKED":
                    await self.task_service.update_status(
                        task.id,
                        TaskState.BLOCKED,
                        error=f"Reviewer blocked task: {result.get('summary')}"
                    )
                else:
                    await self.task_service.update_status(
                        task.id,
                        TaskState.FAILED,
                        error=f"Invalid reviewer decision '{decision}': {result.get('summary')}"
                    )
            else:
                # NEVER falsely approve if no result was produced
                await self.task_service.update_status(task.id, TaskState.FAILED, error="No review result produced by reviewer")
                
        elif task.status == TaskState.NEEDS_CHANGES:
            await self.task_service.update_status(task.id, TaskState.IMPLEMENTING)

        elif task.status == TaskState.APPROVED:
            await self._write_artifact(task, "FINAL.md", self._final_markdown(task))
            await self.task_service.update_status(task.id, TaskState.COMPLETED)

        else:
            return False

        return True

    @staticmethod
    def _task_markdown(task: Task) -> str:
        lines = [
            f"# {task.title}",
            "",
            f"- **Task ID:** {task.id}",
            f"- **Project:** {task.project_id}",
            f"- **Priority:** {task.priority}",
            f"- **Iteration:** {task.iteration}/{task.max_iterations}",
            "",
            "## Description",
            "",
            task.description,
        ]
        if task.requirements:
            lines += ["", "## Requirements", "", task.requirements]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _root_cause_markdown(result: dict) -> str:
        lines = ["# Root Cause Analysis", ""]
        if result.get("root_cause_found") is not None:
            lines.append(f"- **Root cause found:** {result.get('root_cause_found')}")
        if result.get("summary"):
            lines += ["", "## Summary", "", str(result.get("summary"))]
        if result.get("evidence"):
            lines += ["", "## Evidence", "", str(result.get("evidence"))]
        if result.get("recommended_changes"):
            lines += ["", "## Recommended Changes", "", str(result.get("recommended_changes"))]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _implementation_markdown(result: dict) -> str:
        lines = ["# Implementation", ""]
        if result.get("success") is not None:
            lines.append(f"- **Success:** {result.get('success')}")
        if result.get("summary"):
            lines += ["", "## Summary", "", str(result.get("summary"))]
        files = result.get("files_modified") or result.get("files_changed")
        if files:
            lines += ["", "## Files Modified", ""]
            if isinstance(files, list):
                lines += [f"- {f}" for f in files]
            else:
                lines.append(str(files))
        return "\n".join(lines) + "\n"

    @staticmethod
    def _qa_markdown(test_command: str, res) -> str:
        lines = [
            "# QA Report",
            "",
            f"- **Command:** `{test_command}`",
            f"- **Exit code:** {res.exit_code}",
            "",
            "## Stdout",
            "",
            "```",
            res.stdout or "(empty)",
            "```",
        ]
        if res.stderr:
            lines += ["", "## Stderr", "", "```", res.stderr, "```"]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _review_markdown(result: dict) -> str:
        lines = ["# Review", ""]
        if result.get("decision"):
            lines.append(f"- **Decision:** {result.get('decision')}")
        if result.get("confidence") is not None:
            lines.append(f"- **Confidence:** {result.get('confidence')}")
        if result.get("summary"):
            lines += ["", "## Summary", "", str(result.get("summary"))]
        findings = result.get("findings")
        if findings:
            lines += ["", "## Findings", ""]
            if isinstance(findings, list):
                lines += [f"- {f}" for f in findings]
            else:
                lines.append(str(findings))
        required_changes = result.get("required_changes")
        if required_changes:
            lines += ["", "## Required Changes", ""]
            if isinstance(required_changes, list):
                lines += [f"- {c}" for c in required_changes]
            else:
                lines.append(str(required_changes))
        if result.get("remaining_uncertainty"):
            lines += ["", "## Remaining Uncertainty", "", str(result.get("remaining_uncertainty"))]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _final_markdown(task: Task) -> str:
        return (
            f"# {task.title} â€” Complete\n\n"
            f"- **Task ID:** {task.id}\n"
            f"- **Project:** {task.project_id}\n"
            f"- **Iterations used:** {task.iteration}/{task.max_iterations}\n"
            f"- **Status:** COMPLETED\n"
        )
