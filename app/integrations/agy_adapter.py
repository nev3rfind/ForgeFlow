"""AgyProvider – ForgeFlow integration with the Google Antigravity CLI (agy).

This module provides an async, streaming implementation that launches the
``agy`` CLI executable as an isolated child process, feeds it a structured
prompt, and translates its ``stream-json`` NDJSON output into ForgeFlow's
unified event dictionary format.

Security model
--------------
ForgeFlow runs under a **TRUSTED LOCAL EXECUTION** model.  The ``--sandbox``
flag restricts certain agy-internal tool capabilities, but it does NOT provide
OS-level isolation.  An agy process launched as the current Windows user may
still access any file visible to that user account.  Do NOT deploy ForgeFlow
as a multi-tenant or untrusted-code execution platform without adding a proper
OS-level sandbox (Docker, Hyper-V, etc.).

The worktree provided as ``cwd`` is an organisational isolation boundary (Git
isolation), not a security boundary.

Credential isolation
--------------------
All known credential environment variables are stripped from the child process
environment so that API keys do not leak into the Antigravity subprocess or any
further children it spawns.

Process-tree termination (Windows)
-----------------------------------
On Windows, ``process.terminate()`` only kills the top-level ``agy.exe``; any
child processes (test runners, shells, compilers, etc.) would be orphaned.
``AgyProvider`` therefore uses ``taskkill /F /T /PID <pid>`` via an async
subprocess to kill the complete process tree before awaiting the root process.
"""

import os
import sys
import json
import re
import asyncio
import logging
import shutil
from typing import AsyncGenerator, Dict, Any, Type, Optional

from pydantic import BaseModel, ValidationError

from app.integrations.provider import AgentProvider
from app.config import get_env_or_registry

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Credential names that must never be passed to child processes.
# Filtering is case-insensitive on all platforms.
# ------------------------------------------------------------------
_BLOCKED_ENV_PREFIXES = frozenset({
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ABACUS_API_KEY",
    "FORGEFLOW_API_KEY",
    "FORGEFLOW_SECRET",
})

# Maximum bytes of diagnostic output preserved per line / stderr dump
_DIAG_MAX_BYTES = 2000


class AgyProviderError(Exception):
    """Raised when the agy CLI produces an error or unexpected output."""


def _is_sensitive(key: str) -> bool:
    return key.upper() in _BLOCKED_ENV_PREFIXES


def _safe_child_env() -> Dict[str, str]:
    """Return os.environ copy with all credential variables removed."""
    return {k: v for k, v in os.environ.items() if not _is_sensitive(k)}


# ------------------------------------------------------------------
# Balanced-brace JSON extractor
# ------------------------------------------------------------------
def _extract_last_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Extract the *last* complete JSON object from arbitrary text.

    This implements a character-level balanced-brace scanner that correctly
    handles:
    - nested objects / arrays
    - quoted strings (including escaped quotes and brace characters inside)
    - multiple JSON objects / natural language before/after

    Returns the parsed dict of the last valid JSON object found, or None.
    """
    last_good: Optional[Dict[str, Any]] = None
    i = 0
    n = len(text)
    while i < n:
        if text[i] != '{':
            i += 1
            continue
        # Found a potential object start – walk forward with brace counting
        depth = 0
        in_str = False
        escaped = False
        j = i
        while j < n:
            ch = text[j]
            if escaped:
                escaped = False
                j += 1
                continue
            if ch == '\\' and in_str:
                escaped = True
                j += 1
                continue
            if ch == '"':
                in_str = not in_str
                j += 1
                continue
            if not in_str:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = text[i:j + 1]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict):
                                last_good = parsed
                        except json.JSONDecodeError:
                            pass
                        j += 1
                        break
            j += 1
        i = j if j > i else i + 1
    return last_good


# ------------------------------------------------------------------
# Windows process-tree termination
# ------------------------------------------------------------------
async def _kill_process_tree(pid: int) -> None:
    """Asynchronously kill an entire process tree on Windows via taskkill.

    Falls back to a simple terminate() signal on non-Windows platforms.
    Idempotent: safe to call even if the process has already exited.
    """
    if sys.platform != "win32":
        try:
            import signal
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            "taskkill", "/F", "/T", "/PID", str(pid),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    except FileNotFoundError:
        # taskkill not found – extremely unusual but degrade gracefully
        try:
            os.kill(pid, 0)  # check existence
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(1, False, pid)  # type: ignore[attr-defined]
            ctypes.windll.kernel32.TerminateProcess(handle, 1)  # type: ignore[attr-defined]
        except (ProcessLookupError, OSError):
            pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("taskkill failed for PID %d: %s", pid, exc)


# ------------------------------------------------------------------
# AgyProvider
# ------------------------------------------------------------------
class AgyProvider(AgentProvider):
    """ForgeFlow implementation/investigation worker backed by the agy CLI."""

    name = "Agy"

    # Default provider-level timeout in seconds (overridable via env)
    DEFAULT_TIMEOUT = 600

    def __init__(self) -> None:
        self.exe_path = self._get_executable_path()
        if not self.exe_path:
            raise AgyProviderError(
                "Could not find the 'agy' CLI executable.  "
                "Set FORGEFLOW_AGY_PATH to the full path, or ensure 'agy' is on PATH."
            )
        timeout_env = os.environ.get("FORGEFLOW_AGY_TIMEOUT", "")
        try:
            self.timeout = int(timeout_env) if timeout_env else self.DEFAULT_TIMEOUT
        except ValueError:
            self.timeout = self.DEFAULT_TIMEOUT

    # ------------------------------------------------------------------
    # Executable discovery (deterministic priority order)
    # ------------------------------------------------------------------
    def _get_executable_path(self) -> Optional[str]:
        """Resolve the agy executable with deterministic priority:

        1. FORGEFLOW_AGY_PATH (explicit override – highest priority)
        2. Official Windows installation path (%LOCALAPPDATA%\\agy\\bin\\agy.exe)
        3. PATH via shutil.which

        Each candidate is verified to actually exist as a file.
        """
        # 1. Explicit configuration
        config_path = get_env_or_registry("FORGEFLOW_AGY_PATH")
        if config_path:
            if os.path.isfile(config_path):
                logger.debug("AgyProvider: using FORGEFLOW_AGY_PATH = %s", config_path)
                return config_path
            else:
                logger.warning(
                    "FORGEFLOW_AGY_PATH is set to '%s' but that file does not exist.",
                    config_path,
                )

        # 2. Official Windows installation location (preferred over PATH wrappers)
        if sys.platform == "win32":
            default_windows_path = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "agy", "bin", "agy.exe",
            )
            if os.path.isfile(default_windows_path):
                logger.debug("AgyProvider: using default Windows path = %s", default_windows_path)
                return default_windows_path

        # 3. PATH
        which_path = shutil.which("agy")
        if which_path and os.path.isfile(which_path):
            logger.debug("AgyProvider: using PATH = %s", which_path)
            return which_path

        return None

    # ------------------------------------------------------------------
    # JSON / structured-output helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_output(output: Any) -> Optional[Dict[str, Any]]:
        if output is None:
            return None
        if isinstance(output, BaseModel):
            return output.model_dump()
        if isinstance(output, dict):
            return output
        return {"value": output}

    def _validate_or_fallback(
        self,
        structured: Any,
        final_text: Optional[str],
        schema: Type[BaseModel],
    ) -> BaseModel:
        """Validate structured result against schema, with a safe text fallback.

        Priority:
        1. Use the official ``result`` event payload when it validates.
        2. Extract the *last* JSON object from the final assistant text only
           when the official result is absent or invalid.

        Never treats intermediate tool output as the final result because
        ``final_text`` accumulates only ``agent_response`` ACTIVE chunks, not
        tool output.
        """
        coerced = self._coerce_output(structured)
        if coerced is not None:
            try:
                return schema.model_validate(coerced)
            except ValidationError:
                logger.debug("Structured payload failed schema validation, trying text fallback.")

        # Text fallback – extract last JSON object from assistant text only
        if final_text:
            parsed = _extract_last_json_object(final_text)
            if parsed is not None:
                try:
                    return schema.model_validate(parsed)
                except ValidationError as ve:
                    raise AgyProviderError(
                        f"Fallback JSON extracted from agent text did not match schema: {ve}"
                    ) from ve

        raise AgyProviderError(
            "Agy CLI did not produce a valid structured result matching the required schema. "
            f"Raw text preview: {(final_text or '')[:300]!r}"
        )

    # ------------------------------------------------------------------
    # Argument construction
    # ------------------------------------------------------------------
    def _build_args(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_instruction: str,
        workspaces: list,
    ) -> tuple:
        """Build CLI argument list and validated cwd.

        The cwd is always derived from the first workspace provided by the
        orchestration layer and is never overridable by prompt content.
        """
        if not workspaces:
            raise AgyProviderError("No workspace provided to AgyProvider; cannot determine cwd.")

        cwd = workspaces[0]
        if not os.path.isdir(cwd):
            raise AgyProviderError(
                f"Target worktree '{cwd}' does not exist or is not a directory. "
                "ForgeFlow must create the Git worktree before invoking the provider."
            )

        finish_instruction = (
            "\n\nCRITICAL OUTPUT INSTRUCTION:\n"
            "When you have finished your work, you MUST output your final answer as a single "
            "JSON object that strictly conforms to the requested schema.  "
            "Do NOT respond with plain text."
        )

        combined_prompt = (
            f"SYSTEM INSTRUCTION:\n{system_instruction}"
            f"{finish_instruction}"
            f"\n\nUSER PROMPT:\n{prompt}"
        )

        schema_json = json.dumps(schema.model_json_schema())

        args: list = [
            self.exe_path,
            "-p", combined_prompt,
            "--dangerously-skip-permissions",
            "--sandbox",
            "--output-format", "stream-json",
            "--json-schema", schema_json,
        ]

        # Additional read-only context directories (never used as cwd)
        for ws in workspaces[1:]:
            args.extend(["--add-dir", ws])

        return args, cwd

    # ------------------------------------------------------------------
    # Core async process execution
    # ------------------------------------------------------------------
    async def _execute_process(
        self, args: list, cwd: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Launch the agy CLI and yield ForgeFlow-normalised event dicts.

        Handles:
        - NDJSON stream-json parsing
        - non-JSON diagnostic lines (safe, truncated logging)
        - process-tree termination on cancellation
        - provider-level timeout (configurable via FORGEFLOW_AGY_TIMEOUT)
        - exit-code checking
        """
        env = _safe_child_env()

        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        pid = process.pid
        diagnostic_lines: list = []

        async def _drain_stderr() -> str:
            """Read stderr without blocking the event loop."""
            try:
                raw = await process.stderr.read()
                return raw.decode("utf-8", errors="replace").strip()
            except Exception:  # noqa: BLE001
                return ""

        try:
            async with asyncio.timeout(self.timeout):
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break

                    line_str = line.decode("utf-8", errors="replace").strip()
                    if not line_str:
                        continue

                    try:
                        event = json.loads(line_str)
                    except json.JSONDecodeError:
                        # Non-JSON output: preserve for diagnostics, do not crash
                        truncated = line_str[:_DIAG_MAX_BYTES]
                        diagnostic_lines.append(truncated)
                        logger.debug("agy non-JSON stdout: %s", truncated)
                        yield {"type": "diagnostic", "content": truncated}
                        continue

                    ev_name = event.get("event")

                    if ev_name == "step_update":
                        step = event.get("step_update", {})
                        step_type = step.get("step_type")
                        state = step.get("state")

                        if step_type == "agent_response" and state == "ACTIVE":
                            content = step.get("content", "")
                            if content:
                                yield {"type": "text", "content": content}

                        elif step_type == "tool" and state == "ACTIVE":
                            tool_info = step.get("tool_info", {})
                            name = tool_info.get("name")
                            params = tool_info.get("parameters", {})
                            if name:
                                yield {"type": "tool_call", "name": name, "args": params}

                        elif step_type == "tool" and state == "DONE":
                            tool_info = step.get("tool_info", {})
                            name = tool_info.get("name")
                            if name:
                                yield {"type": "tool_result", "name": name, "result": "completed"}

                    elif ev_name == "result":
                        res = event.get("result", {})
                        if res.get("status") == "ERROR":
                            raise AgyProviderError(f"CLI Error: {res.get('error', 'Unknown')}")
                        yield {"type": "__raw_result__", "data": res}

                await process.wait()

        except asyncio.TimeoutError:
            logger.warning("AgyProvider: process timed out after %ds (PID %d)", self.timeout, pid)
            await _kill_process_tree(pid)
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
            raise AgyProviderError(
                f"Antigravity CLI process timed out after {self.timeout} seconds."
            )

        except asyncio.CancelledError:
            logger.debug("AgyProvider: task cancelled – terminating process tree (PID %d)", pid)
            await _kill_process_tree(pid)
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
            raise  # re-raise so the orchestrator handles CancelledError

        else:
            # Normal exit – check return code
            if process.returncode != 0:
                stderr_text = await _drain_stderr()
                diag = "\n".join(diagnostic_lines[-10:])  # last 10 non-JSON lines
                detail = stderr_text or diag or "(no stderr captured)"
                raise AgyProviderError(
                    f"Antigravity CLI exited with code {process.returncode}: "
                    f"{detail[:_DIAG_MAX_BYTES]}"
                )

    # ------------------------------------------------------------------
    # Public provider interface
    # ------------------------------------------------------------------
    async def chat(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_instruction: str,
        workspaces: list,
    ) -> BaseModel:
        args, cwd = self._build_args(prompt, schema, system_instruction, workspaces)

        final_text = ""
        structured_data = None

        async for event in self._execute_process(args, cwd):
            if event["type"] == "text":
                final_text += event.get("content", "")
            elif event["type"] == "__raw_result__":
                structured_data = event["data"].get("response")

        return self._validate_or_fallback(structured_data, final_text, schema)

    async def stream_chat(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_instruction: str,
        workspaces: list,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        args, cwd = self._build_args(prompt, schema, system_instruction, workspaces)

        final_text = ""
        structured_data = None

        async for event in self._execute_process(args, cwd):
            if event["type"] == "text":
                final_text += event.get("content", "")
                yield event
            elif event["type"] in ("tool_call", "tool_result", "diagnostic"):
                yield event
            elif event["type"] == "__raw_result__":
                structured_data = event["data"].get("response")

        validated = self._validate_or_fallback(structured_data, final_text, schema)
        yield {"type": "structured_output", "data": validated.model_dump()}
