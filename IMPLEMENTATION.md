# ForgeFlow Implementation & Engineering Hardening Report

## 1. System Overview
ForgeFlow is a universal local AI software-engineering orchestration platform coordinating:
- Git repositories and isolated worktrees.
- AI investigation, implementation, and review agents.
- Testing, QA, and verification runners.
- Independent senior reviewer decisions (Abacus AI adapter with fallback).
- Iterative task repair loops.
- Task state persistence and event streaming.
- Real-time browser command center dashboard.

ForgeFlow is technology-stack agnostic, supporting arbitrary Git repositories without project-specific hard-coding.

---

## 2. PREPARING -> FAILED Runtime Issue: Diagnosis & Root Causes

### Symptoms
When tasks were started or retried on repositories (e.g. `C:\Users\ddona\ForgeFlow-test-project`, task `c517aecd-8c9f-4908-a9c1-641fea7f6b63`), execution immediately failed during the `PREPARING` phase (`PENDING -> PREPARING -> FAILED`).

### Root Causes
1. **Worktree & Branch Metadata Desynchronization**:
   - `GitService.create_worktree()` previously called `shutil.rmtree(worktree_path)` to clear prior worktree directories on disk without invoking `git worktree remove` or `git worktree prune`.
   - Git retained the worktree registration in `.git/worktrees/` and the local branch in `.git/refs/heads/task/<id>`.
   - On retry or restart, `git worktree add -b task/<id> ...` failed with:
     `fatal: A branch named 'task/...' already exists.`
   - When the directory was removed on disk while Git metadata remained, Git rejected commands with:
     `fatal: 'task/...' is already checked out at '...'`.
2. **Relative `workspace_root`**:
   - `Settings.workspace_root` defaulted to `./runtime/worktrees`, causing destination paths to resolve inconsistently depending on the working directory from which the server or CLI was launched.
3. **Windows Environment API Key Inheritance**:
   - `GEMINI_API_KEY` was stored in the Windows User registry (`HKCU\Environment`), but was not inherited by new child processes or subshells started before a system environment broadcast, causing `AntigravityProvider` to fail with `ValueError: A Gemini API key is required.`
4. **WebSocket Event Error Payload Omission**:
   - `TaskService.update_status()` saved error information to SQLite, but excluded `"error"` from the `STATE_CHANGED` WebSocket event payload, leaving frontend clients unaware of failure causes.

---

## 3. Initial Fix & End-to-End Verification
- **Git Service Overhaul**: Added `git worktree prune`, porcelain parsing via `list_worktrees()`, safe worktree removal, and resilient creation.
- **Canonical Workspace Path**: Pinned `workspace_root` default to `<ForgeFlow_root>/runtime/worktrees`.
- **Registry Fallback**: Added `get_env_or_registry("GEMINI_API_KEY")` in `config.py` and `AntigravityProvider`.
- **Event Visibility**: Dispatched `"error": task.error_information` in `STATE_CHANGED` WebSocket payloads.
- **Initial Verification**: All 63 tests passed, and real end-to-end task execution completed successfully on `C:\Users\ddona\ForgeFlow-test-project`, creating `greeting.txt` containing `Hello from ForgeFlow`.

---

## 4. Independent Senior Review Findings & Hardening

An independent senior engineering review evaluated the initial fix and identified key hardening requirements:

### 1. Safe Task Branch Retry & Worktree Lifecycle
- **Problem**: `git worktree add -B` forcibly reset the task branch to `base_branch`, which could destroy legitimate intermediate commits if a task was stopped and resumed or if external commits existed.
- **Hardening Implemented**:
  - `create_worktree(..., reset_branch=False)` checks if `refs/heads/task/<task_id>` exists.
  - If the branch exists and `reset_branch=False` (default for resumptions/retries), it executes `git worktree add <worktree_path> <branch_name>`, attaching to the existing branch and preserving all commits.
  - If `reset_branch=True` is explicitly requested, it counts unique commits ahead of `base_branch` and creates an automatic backup ref (`refs/forgeflow/backups/task_<task_id>_<timestamp>`) before resetting via `-B`.
  - Unrelated worktrees and branches are never touched.

### 2. Secret Scrubbing in Test Subprocesses
- **Problem**: `CommandRunner.run()` copied `os.environ`, leaking `GEMINI_API_KEY` into project test commands.
- **Hardening Implemented**:
  - Defined `SENSITIVE_ENV_VARS` (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ABACUS_API_KEY`, `FORGEFLOW_API_KEY`, `FORGEFLOW_SECRET`).
  - Filtered out sensitive environment keys before spawning test subprocesses. Preserved explicit caller-supplied `env` variables.

### 3. Path Traversal Protection
- **Problem**: `task_id` from URL parameters was joined into filesystem paths without validation.
- **Hardening Implemented**:
  - `_validate_task_id(task_id)` enforces strict regex `^[a-zA-Z0-9_\-]+$`.
  - Enforced path containment using `os.path.commonpath([workspace_root, worktree_path]) == workspace_root`.
  - Applied `_validate_worktree_path()` to `remove_worktree()` to ensure no directory outside `workspace_root` can be targeted for deletion.

### 4. Clean Artifact Lifecycle
- **Problem**: Retrying tasks accumulated duplicate artifact rows in SQLite pointing to overwritten files.
- **Hardening Implemented**:
  - Updated `Repository.save_artifact()` to perform an upsert on `(task_id, name)`.
  - Added `Repository.delete_artifacts(task_id)`.
  - In `Orchestrator.retry_task()`, existing physical artifact files are archived into `runtime/worktrees/artifacts/<task_id>/history/<timestamp>/` before new iterations run, keeping active artifacts clean while preserving disk history.

### 5. Windows Pytest Developer Experience
- **Problem**: Running bare `pytest` on Windows failed during session teardown due to symlink cleanup permissions.
- **Hardening Implemented**:
  - Added root `pytest.ini` specifying `testpaths = tests`, `pythonpath = .`, `basetemp = runtime/test_tmp`, and `tmp_path_retention_policy = none`.
  - Running `pytest` now executes reliably across all environments without special command-line flags.

---

## 5. Automated Test Suite Summary
- **Total Tests**: 85 automated unit and integration tests.
- **Passing Rate**: 100% (85 passed, 0 failed, 1 deprecation warning in Starlette test client).
- **Test Modules**:
  - `tests/test_git_service.py`: Fresh creation, idempotent recreation, desync recovery, unrelated worktree preservation, commit preservation on restart, backup on explicit reset, path traversal rejection, rapid reset collision avoidance, and safe routine metadata pruning (11 tests).
  - `tests/test_retry_reset_branch.py`: Orchestrator `reset_branch` flag propagation, commit preservation by default, backup ref creation, clean reset when no unique commits exist, and branch safety during iterative `NEEDS_CHANGES -> IMPLEMENTING` repair loops (5 tests).
  - `tests/test_qa_runner_env.py`: Case-insensitive secret scrubbing across uppercase, lowercase, mixed-case, caller overrides, and caller dict immutability (4 tests).
  - `tests/test_task_service_events.py`: Error payload verification on `STATE_CHANGED` events and guaranteed WebSocket unsubscription on unexpected errors (2 tests).
  - `tests/test_config_registry.py`: Registry environment fallback and precedence mocking (3 tests).
  - `tests/test_artifact_lifecycle.py`: Artifact upsert and task artifact deletion (2 tests).
  - `tests/test_command_validation.py`: Shell metacharacters and forbidden executable validation (35 tests).
  - `tests/test_orchestration_review.py`: Orchestrator state machine, Abacus review, fallback provider (9 tests).
  - `tests/test_abacus_adapter.py`: Abacus reviewer CLI adapter parsing and error handling (8 tests).
  - `tests/test_antigravity_adapter.py`: Antigravity provider formatting and structured output (5 tests).
  - `tests/test_api_endpoints.py`: REST API sanity tests (1 test).

---

## 6. End-to-End Task Verification
- **Task**: `c517aecd-8c9f-4908-a9c1-641fea7f6b63`
- **Target Repository**: `C:\Users\ddona\ForgeFlow-test-project`
- **Goal**: Create `greeting.txt` containing `Hello from ForgeFlow`
- **Execution Trajectory**:
  - `PENDING -> PREPARING -> INVESTIGATING -> ROOT_CAUSE_READY -> ROOT_CAUSE_REVIEW -> IMPLEMENTING -> IMPLEMENTATION_READY -> TESTING -> QA -> REVIEW -> APPROVED -> COMPLETED`.
- **Results**:
  - Status: `COMPLETED` (Iteration 1/5, Error: None).
  - `greeting.txt`: `'Hello from ForgeFlow\n'`
  - Artifacts generated: `TASK.md`, `ROOT_CAUSE.md`, `IMPLEMENTATION.md`, `QA.md`, `REVIEW.md` (Decision: APPROVED, Confidence: 1.0), `FINAL.md`.
  - Artifact history: Prior run physical files preserved in `runtime/worktrees/artifacts/c517aecd-8c9f-4908-a9c1-641fea7f6b63/history/`.
  - Manual user worktree `C:\Users\ddona\ForgeFlow-test-worktree`: **Completely untouched and preserved** on branch `test-forgeflow-worktree`.

---

## 7. Hardening Phase 2: Independent Review Findings Resolution

### Finding 1 & 3: Case-Insensitive Secret Filtering & Caller Override Sanitization
- **File**: `app/qa/runner.py`
- **Behavior**:
  - Filter function `is_sensitive_env_var()` evaluates `key.upper() in SENSITIVE_ENV_VARS`.
  - Strips uppercase (`GEMINI_API_KEY`), lowercase (`gemini_api_key`), and mixed-case (`Gemini_Api_Key`, `Anthropic_Api_Key`) variables from child test subprocess environments.
  - Applies identical case-insensitive filtering to explicit caller-supplied `env` dictionaries without mutating the caller's input dictionary.

### Finding 2: Full Propagation of `reset_branch` Through Orchestration Engine
- **Files**: `app/orchestration/engine.py`, `app/main.py`
- **Distinction of Semantics**:
  - **SAFE DEFAULT (`reset_branch=False`)**: Retains and checks out existing task branch commits without altering branch history. Used by standard task creation, retries, and iterative repair loops (`NEEDS_CHANGES -> IMPLEMENTING`).
  - **EXPLICIT DESTRUCTIVE OPERATION (`reset_branch=True`)**: Explicitly requested when wiping the task branch back to `base_branch`. If commits exist on the branch ahead of `base_branch`, ForgeFlow automatically backs them up to `refs/forgeflow/backups/task_<task_id>_<timestamp>_<uuid>` before resetting via `git worktree add -B`.
- **Engine Propagation**: Tracked via `self.reset_branch_tasks` in `Orchestrator`, passed to `git_service.create_worktree(..., reset_branch=should_reset)` in `PREPARING` state, and exposed on `/tasks/{task_id}/retry?reset_branch=true`.

### Finding 4: Guaranteed WebSocket Subscription Cleanup
- **File**: `app/main.py`
- **Behavior**: Enclosed WebSocket event delivery loop in a `try ... finally:` block, guaranteeing that `event_bus.unsubscribe(task_id, callback)` is always executed on `WebSocketDisconnect`, abrupt client drops (`ConnectionResetError`, `anyio.EndOfStream`), or unexpected runtime exceptions.

### Finding 5: Collision-Safe Backup References
- **File**: `app/git/service.py`
- **Behavior**: Updated backup ref generation format to `refs/forgeflow/backups/{clean_branch}_{timestamp_ms}_{uuid4[:8]}`. Verified with rapid successive resets that every backup ref is globally unique and unmerged commits are never lost or overwritten.

### Finding 6: Routine Worktree Pruning
- **File**: `app/git/service.py`
- **Behavior**: Added explicit `prune_worktrees(repo_path)` method to `GitService` and integrated it into worktree lifecycle hooks. Safely cleans dead metadata when worktree folders are deleted from disk outside Git, without affecting unrelated live worktrees.

### Finding 7: Windows Path Length Assessment & Mitigation
- **File**: `app/git/service.py`
- **Assessment**:
  - Controlled workspace root: `runtime/worktrees/forgeflow_task_<task_id>` utilizes ~90 characters with full UUIDs, leaving >160 characters for nested project files under standard Windows 260-char limits.
  - Added `-c core.longpaths=true` to all Git invocations in `GitService._run_git()`, enabling Git for Windows to leverage Windows extended-length path APIs (`\\?\`) seamlessly across all worktrees.

 # # #   5 .   D e s k t o p   R P A   A r c h i t e c t u r e 
 -   B y p a s s e d   p y w i n a u t o ' s   d e f a u l t   w i n d o w   e n u m e r a t i o n   d u e   t o   i n t e g e r - s i z e   l i m i t s   ( c a n n o t   f i t   ' i n t '   i n t o   a n   i n d e x - s i z e d   i n t e g e r )   o c c u r r i n g   w h e n   n a v i g a t i n g   c o m p l e x   U I A / D e s k t o p   t r e e s   o n   6 4 - b i t   s y s t e m s . 
 -   I m p l e m e n t e d   a   r o b u s t   C - l e v e l   w i n d o w   d i s c o v e r y   u s i n g   c t y p e s . w i n d l l . u s e r 3 2 . E n u m W i n d o w s . 
 -   A d d e d   i s o l a t i o n   c h e c k s :   T h e   R P A   e n g i n e   s t r i c t l y   f i l t e r s   o u t   t h e   F o r g e F l o w   d a s h b o a r d   b r o w s e r   ( d e t e c t s   l o c a l h o s t ,    o r g e f l o w ,   o r   c h r o m e   i s   b e i n g   c o n t r o l l e d )   t o   p r e v e n t   b r o w s e r   s t e a l i n g . 
 -   C o n n e c t i o n s   a r e   s t r i c t l y   r o u t e d   t h r o u g h   h a n d l e - b a s e d   b i n d i n g s   t o   t h e   e x a c t   e x t r a c t e d   A n t i g r a v i t y   p r o c e s s .  
 