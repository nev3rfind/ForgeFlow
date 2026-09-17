# ForgeFlow Architecture

## System Architecture

ForgeFlow is a local autonomous software-engineering orchestration platform.  It is built using
a clean, modular architecture separating the core orchestration logic from external providers,
the physical filesystem, and UI layers.

### Component Responsibilities

1. **API / Dashboard (Presentation Layer)**
   - **FastAPI Server**: Provides a clean REST API and WebSocket endpoints for real-time updates.
   - **HTML/JS Frontend**: A lightweight, vanilla HTML/JS frontend to monitor and control tasks.

2. **Orchestration Layer**
   - **State Machine**: Manages task transitions
     (`PENDING` → `PREPARING` → `INVESTIGATING` → `ROOT_CAUSE_READY` → `ROOT_CAUSE_REVIEW`
     → `IMPLEMENTING` → `IMPLEMENTATION_READY` → `TESTING` → `QA` → `REVIEW` → `APPROVED`
     → `COMPLETED`).
   - **Iteration Engine**: Tracks retry counts and manages the autonomous loop between
     implementation, testing, and review.  Enforces `max_iterations` with a `BLOCKED` state.
   - **Task Manager**: Coordinates high-level workflows including pause, resume, cancellation,
     and retry.

3. **Agent & Reviewer Providers**
   - **Provider Interface (`AgentProvider`)**: Abstract definitions for agents.
   - **AgyProvider** *(primary worker)*: Concrete implementation that invokes the official
     Google Antigravity CLI (`agy`) as an async subprocess.  Authenticates via the local
     Antigravity/Google account – no `GEMINI_API_KEY` required.  Streams NDJSON events
     (`stream-json`) in real time to the orchestration engine.
   - **AntigravityProvider** *(legacy worker)*: Python SDK implementation, selectable via
     `FORGEFLOW_IMPLEMENTATION_PROVIDER=antigravity`.
   - **AbacusReviewerProvider** *(independent reviewer)*: Executes via the local authenticated
     `abacusai` CLI in non-interactive, read-only plan mode (`--permission-mode plan`).
   - **Provider Separation**: AgyProvider implements code changes; Abacus AI objectively
     evaluates the worktree against task requirements and test results.

4. **Domain Services**
   - **Project Service**: Manages generic project metadata (repository paths, test commands,
     technology type).
   - **Task Service**: Manages the lifecycle and state of engineering tasks, persisting state and
     events to SQLite.
   - **Git/Worktree Service**: Handles isolated Git worktrees to ensure the main repository is
     never corrupted.  Uses non-destructive branch attachment by default; explicit reset with
     automatic backup refs when `reset_branch=True`.
   - **Command Runner**: A controlled execution environment for tests, builds, and linting.
     Sensitive environment variables are stripped before spawning subprocesses.
   - **Artifact Service**: Saves task outputs (`TASK.md`, `ROOT_CAUSE.md`, `IMPLEMENTATION.md`,
     `QA.md`, `REVIEW.md`, `FINAL.md`) locally.

5. **Persistence Layer**
   - **SQLite Database**: Stores projects, tasks, events, and iterations.
   - **Repository Pattern**: Abstracts raw SQL queries away from the business logic.

## Windows Async Subprocesses

On Windows, Python's `asyncio` framework has two main event loop policies: `ProactorEventLoop` and `SelectorEventLoop`.
- **ProactorEventLoop** (Python 3.8+ default) supports async subprocesses via `asyncio.create_subprocess_exec()`.
- **SelectorEventLoop** does not support async subprocesses and raises `NotImplementedError`.

ForgeFlow relies heavily on async subprocesses to orchestrate tools, git worktrees, and AgyProvider workers. Because some test runners or web server configurations (such as older Uvicorn setups) might force a `SelectorEventLoop`, ForgeFlow implements specific safeguards:
1. **Global Configuration:** `app/config.py` explicitly sets `asyncio.WindowsProactorEventLoopPolicy()` upon import to protect against unintentional overrides.
2. **CLI Override:** The `cli.py serve` command bypasses `uvicorn`'s internal Windows loop override by passing `loop="none"`.
3. **Graceful Fallback:** Operations that could fail due to a forced `SelectorEventLoop` (such as `GitService._run_git`) contain a graceful fallback to a background thread using `asyncio.to_thread(subprocess.run)`.

---

## Data Flow & Review Architecture

```
                      +-----------------------------+
                      |          USER / UI          |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |         ORCHESTRATOR        |
                      +--------------+--------------+
                                     |
             +-----------------------+-----------------------+
             |                                               |
             v                                               v
+---------------------------+                   +---------------------------+
|       AGY PROVIDER        |                   |    ABACUS AI REVIEWER     |
|  (agy CLI – investigator, |                   |    (Independent Senior)   |
|   implementer & tester)   |                   +---------------------------+
+---------------------------+                               ^
             |                                              |
             v                                              |
     Git Worktree Edits ----------------------------> Evaluates Diff & QA
```

1. **Investigation & Implementation**: AgyProvider launches `agy` as an isolated child process
   with the Git worktree as its `cwd`.  The agent inspects the codebase, diagnoses the root
   cause, and implements code changes inside the worktree.
2. **Deterministic Tests & QA**: ForgeFlow's `CommandRunner` executes project test commands
   (e.g., `pytest`, `npm test`).  If tests fail, ForgeFlow routes back to `NEEDS_CHANGES`.
3. **Independent Abacus Review**: Invokes `abacusai` locally.  Feeds task requirements, worktree
   git status/diff, and test outputs into the prompt.  Validates structured `ReviewResult`.
4. **Decision Loop**:
   - `APPROVED`: Reaches `APPROVED` then `COMPLETED`.
   - `NEEDS_CHANGES`: Increments iteration count, routes back to `IMPLEMENTING`.
   - `BLOCKED`: Halts execution with an actionable report.

---

## AgyProvider Process Lifecycle

### Subprocess Launch

```
asyncio.create_subprocess_exec(
    agy_path, "-p", prompt,
    "--dangerously-skip-permissions",
    "--sandbox",
    "--output-format", "stream-json",
    "--json-schema", schema_json,
    cwd=worktree_path,   # <- always the orchestrator-provided Git worktree
    env=scrubbed_env,    # <- credentials removed
)
```

### Stream-JSON NDJSON Parsing

Each stdout line is parsed as JSON.  Non-JSON lines (CLI panics, stack traces) are preserved as
`diagnostic` events and logged – they do not crash the provider.  Event types emitted:

| Internal event type | Dashboard event |
|---|---|
| `text` | `AGENT_CHUNK` |
| `tool_call` | `AGENT_CHUNK` |
| `tool_result` | `AGENT_CHUNK` |
| `diagnostic` | `AGENT_CHUNK` |
| `structured_output` | `AGENT_CHUNK` |

### Structured Output Selection

Priority order:
1. **Official `result` event** from the `agy` CLI (`event: "result"`, `status: "OK"`)
2. **Fallback**: last valid JSON object extracted from agent text via balanced-brace scanner
   (never uses intermediate tool output)
3. **Error**: `AgyProviderError` raised if no valid structured result is found

### Timeout & Cancellation

| Trigger | Mechanism |
|---|---|
| `FORGEFLOW_AGY_TIMEOUT` exceeded | `asyncio.timeout(n)` fires |
| Task cancelled by user | `asyncio.CancelledError` propagated |
| Both paths | `_kill_process_tree(pid)` called |

#### Windows Process-Tree Termination

`process.terminate()` alone only kills the top-level `agy.exe`; child processes
(test runners, shells, compilers) would be orphaned and continue locking files.

ForgeFlow uses:

```
taskkill /F /T /PID <pid>
```

…executed via an async subprocess (`asyncio.create_subprocess_exec`) so the event loop is
never blocked.  The call is idempotent – safe if the process has already exited.

---

## ⚠️ Security Model – Trusted Local Execution

> **This is a trusted local execution platform, not a security sandbox.**

### What `--dangerously-skip-permissions --sandbox` provides

The `--sandbox` flag restricts certain Antigravity-internal tool capabilities (e.g., disables
broad filesystem writes outside the working directory within the `agy` agent's own tool
permission system).

### What it does NOT provide

- **It does NOT restrict OS-level file access**.  An `agy.exe` process runs with the **full
  file-system privileges of the current Windows user account**.  It can potentially read, write,
  or delete any file visible to that user account, not just files inside the Git worktree.
- **The Git worktree is an organisational isolation boundary, not an OS security sandbox.**
  An agent can deduce the parent repository path via `git worktree list` and traverse upward.

### Implications

| Acceptable use | Not acceptable use |
|---|---|
| Trusted developer automating their own local repositories | Multi-tenant SaaS shared between untrusting users |
| Single-user local workstation | Executing code from untrusted third parties |
| Offline / air-gapped development environment | Public internet-facing orchestration service |

For true hostile-code isolation, use a dedicated OS-level sandbox:
- Docker Desktop (Windows containers with restricted mounts)
- Hyper-V isolated VMs
- Windows Sandbox with a dedicated restricted user account

### Credential Isolation

The following variables are **stripped** from all child process environments:
`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ABACUS_API_KEY`,
`FORGEFLOW_API_KEY`, `FORGEFLOW_SECRET`.

Filtering is case-insensitive on all platforms.

---

## Abacus Configuration & Fallback Policy

- **`ABACUS_REVIEWER_ENABLED`**: Boolean (default `false`).
- **`ABACUS_REVIEWER_FALLBACK_ENABLED`**: Boolean (default `true`).  If Abacus fails, falls
  back to the primary worker as reviewer.  A failed reviewer is **never** treated as approval.
- **`ABACUS_REVIEW_MODE`**: `every_iteration` (default) | `checkpoint` | `final`.

---

## Environment Variable Reference

| Variable | Default | Description |
|---|---|---|
| `FORGEFLOW_IMPLEMENTATION_PROVIDER` | `antigravity` | `agy` or `antigravity` |
| `FORGEFLOW_AGY_PATH` | auto | Explicit path to `agy` executable |
| `FORGEFLOW_AGY_TIMEOUT` | `600` | Per-task timeout in seconds |
| `FORGEFLOW_DB_PATH` | `forgeflow.db` | SQLite database path |
| `FORGEFLOW_HOST` | `0.0.0.0` | Server bind address |
| `FORGEFLOW_PORT` | `8000` | Server port |
| `FORGEFLOW_WORKSPACE_ROOT` | `<repo>/runtime/worktrees` | Git worktree root |
| `FORGEFLOW_MAX_ITERATIONS` | `5` | Default max task iterations |
| `FORGEFLOW_COMMAND_TIMEOUT` | `300` | QA command timeout in seconds |
| `ABACUS_REVIEWER_ENABLED` | `false` | Enable Abacus reviewer |
| `ABACUS_REVIEWER_FALLBACK_ENABLED` | `true` | Enable reviewer fallback |
| `ABACUS_REVIEW_MODE` | `every_iteration` | Review cadence |
| `ABACUSAI_PATH` | auto | Explicit path to `abacusai` |
| `ABACUS_TIMEOUT` | `120` | Abacus reviewer timeout |
