# ForgeFlow

Universal autonomous software-engineering orchestration platform.

ForgeFlow coordinates autonomous coding agents, project analysis, implementation, testing, QA,
review, Git workflows, and live task monitoring through a local web dashboard.

## Architecture Highlights

- **Worker (AgyProvider)**: The Google Antigravity CLI (`agy`) is the primary implementation
  worker for investigation, implementation and testing.  Authenticates via the local
  Antigravity/Google account – no `GEMINI_API_KEY` or API billing is required.
- **Fallback Worker (AntigravityProvider)**: Legacy Antigravity Python SDK provider, selectable
  via `FORGEFLOW_IMPLEMENTATION_PROVIDER=antigravity` (default).
- **Reviewer**: Abacus AI acts as the independent senior reviewer via local CLI integration
  (`abacusai`).
- **Orchestration**: ForgeFlow controls task state, iteration limits, deterministic test
  execution, and Git worktree isolation.
- **Git Safety**: All modifications happen within dedicated Git worktrees.  The primary
  repository branch remains untouched until reviewed and merged.

## Selecting the Implementation Provider

```powershell
# Use the official Antigravity CLI (recommended)
$env:FORGEFLOW_IMPLEMENTATION_PROVIDER = "agy"
python cli.py serve

# Use the legacy Antigravity Python SDK (default if env var not set)
$env:FORGEFLOW_IMPLEMENTATION_PROVIDER = "antigravity"
python cli.py serve
```

## AgyProvider Configuration

| Variable | Default | Description |
|---|---|---|
| `FORGEFLOW_IMPLEMENTATION_PROVIDER` | `antigravity` | Set to `agy` to activate AgyProvider |
| `FORGEFLOW_AGY_PATH` | auto-detected | Explicit path to `agy.exe` (optional) |
| `FORGEFLOW_AGY_TIMEOUT` | `600` | AgyProvider per-task timeout in seconds |

### agy Executable Discovery (deterministic priority)

1. `FORGEFLOW_AGY_PATH` environment variable (explicit, highest priority)
2. Official Windows installation path: `%LOCALAPPDATA%\agy\bin\agy.exe`
3. `PATH` via `shutil.which("agy")`

If no valid executable is found, ForgeFlow raises a clear `AgyProviderError` at startup.

### Authentication

AgyProvider uses the locally authenticated Antigravity/Google account session.
No `GEMINI_API_KEY` or API billing is required.

### Credential Isolation

The following environment variables are **never** passed to agy child processes or to
any project test subprocesses:

- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `ABACUS_API_KEY`
- `FORGEFLOW_API_KEY`
- `FORGEFLOW_SECRET`

Filtering is case-insensitive on all platforms.

## ⚠️ Security Model – Trusted Local Execution

> **ForgeFlow is a trusted local execution platform.**

The combination of `--dangerously-skip-permissions` and `--sandbox` restricts certain
Antigravity-internal tool capabilities, but it does **NOT** provide OS-level process isolation.

An `agy.exe` process launched by ForgeFlow runs with the **full file-system privileges of the
current Windows user account**.  It can potentially read, write, or delete any file that the
user account can access – not just files inside the Git worktree.

**Git worktree isolation is an organisational boundary, not a security sandbox.**

Do **NOT** deploy ForgeFlow as:
- A multi-tenant service shared between users who do not trust each other.
- A sandbox for executing untrusted or adversarial code.
- A service exposed to the public internet without additional OS/container isolation.

For true hostile-code isolation you would need a dedicated OS-level sandbox such as:
- Docker Desktop (Windows containers)
- Hyper-V isolated VMs
- Windows Sandbox or a dedicated restricted user account

## Process Lifecycle & Cancellation

When a task is cancelled or times out:

1. ForgeFlow calls `_kill_process_tree(pid)`.
2. On Windows this invokes `taskkill /F /T /PID <pid>` asynchronously, which terminates the
   entire process tree including test runners, compilers, and shells spawned by agy.
3. On other platforms `SIGTERM` is sent to the process group.
4. ForgeFlow then awaits process exit with a 10-second grace period.

This prevents orphaned child processes from locking Git worktree files.

## Abacus AI Reviewer Configuration

ForgeFlow supports using the local `abacusai` CLI as an independent senior code reviewer.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ABACUS_REVIEWER_ENABLED` | `false` | Enable Abacus AI as the senior reviewer |
| `ABACUS_REVIEWER_FALLBACK_ENABLED` | `true` | Fallback to worker review if Abacus CLI fails |
| `ABACUS_REVIEW_MODE` | `every_iteration` | Review cadence (`every_iteration`, `checkpoint`, `final`) |
| `ABACUSAI_PATH` | auto-detected | Custom path to `abacusai` executable |

### Running with Abacus Reviewer Enabled

```powershell
$env:ABACUS_REVIEWER_ENABLED = "true"
$env:FORGEFLOW_IMPLEMENTATION_PROVIDER = "agy"
python cli.py serve
```

## Start ForgeFlow on Windows

You can start the entire ForgeFlow environment with one command:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\ddona\ForgeFlow\start_forgeflow.ps1
```

This script automatically:
- Validates the Python virtual environment.
- Configures ForgeFlow to use the `agy` implementation provider.
- Enables the Abacus AI reviewer.
- Starts the server **without auto-reload** (normal execution intentionally omits `--reload` because ForgeFlow task worktrees are actively modified by workers and must not trigger server restarts).
- Opens the dashboard in your default browser.

## Quick Start (Manual)

### 1. Start the ForgeFlow Server

```powershell
$env:FORGEFLOW_IMPLEMENTATION_PROVIDER = "agy"
python cli.py serve
```

Access the dashboard at `http://localhost:8000`.

### 2. Configure Projects & Tasks via CLI

```powershell
# Check health
python cli.py health

# Register a project
python cli.py project add --name "My Project" --repo "C:\Path\To\Repo" --type "python" --test-command "pytest"

# Create a task
python cli.py task create --project "<project-id>" --title "Fix login bug" --desc "Fix auth token expiration"

# Start task
python cli.py task start <task-id>
```

## Running Tests

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest tests
```
