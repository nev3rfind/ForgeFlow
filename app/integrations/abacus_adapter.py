import asyncio
import json
import os
import re
import shutil
import logging
from typing import AsyncGenerator, Dict, Any, Type, Optional, List
from pydantic import BaseModel
from app.integrations.provider import AgentProvider
from app.agents.roles import ReviewResult

logger = logging.getLogger("forgeflow.abacus")

class AbacusReviewerError(Exception):
    """Raised when the Abacus reviewer fails or returns invalid output."""
    pass

class AbacusReviewerProvider(AgentProvider):
    def __init__(
        self,
        cli_path: Optional[str] = None,
        timeout: int = 120,
        review_mode: str = "every_iteration",
        fallback_enabled: bool = True
    ):
        self.cli_path = cli_path or self._find_cli()
        self.timeout = timeout
        self.review_mode = review_mode
        self.fallback_enabled = fallback_enabled
        self.name = "Abacus Reviewer"

    def _find_cli(self) -> Optional[str]:
        # 1. Environment variable override
        env_path = os.environ.get("ABACUSAI_PATH")
        if env_path and os.path.exists(env_path):
            return env_path
        
        # 2. System PATH
        which_path = shutil.which("abacusai") or shutil.which("abacusai.exe")
        if which_path:
            return which_path
        
        # 3. Standard user install location on Windows
        home_path = os.path.expanduser("~/.abacusai/bin/abacusai.exe")
        if os.path.exists(home_path):
            return home_path

        # 4. Standard Linux / macOS location
        unix_path = os.path.expanduser("~/.abacusai/bin/abacusai")
        if os.path.exists(unix_path):
            return unix_path

        return None

    def is_available(self) -> bool:
        return bool(self.cli_path and os.path.exists(self.cli_path))

    async def _gather_worktree_context(self, worktree_path: str) -> str:
        """Collect read-only git status, diff, and file tree from worktree."""
        if not worktree_path or not os.path.exists(worktree_path):
            return "No worktree directory provided."

        context_parts = [f"=== WORKTREE PATH: {worktree_path} ==="]
        
        # Check if it's a git repo/worktree
        try:
            # git status
            p_status = await asyncio.create_subprocess_exec(
                "git", "status", "--short",
                cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            out_status, _ = await p_status.communicate()
            context_parts.append(f"--- Git Status ---\n{out_status.decode('utf-8', errors='replace').strip() or 'Working tree clean'}")

            # git diff
            p_diff = await asyncio.create_subprocess_exec(
                "git", "diff", "HEAD~1..HEAD",
                cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            out_diff, _ = await p_diff.communicate()
            diff_text = out_diff.decode('utf-8', errors='replace').strip()
            if not diff_text:
                # Try uncommitted diff
                p_diff2 = await asyncio.create_subprocess_exec(
                    "git", "diff",
                    cwd=worktree_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                out_diff2, _ = await p_diff2.communicate()
                diff_text = out_diff2.decode('utf-8', errors='replace').strip()

            context_parts.append(f"--- Git Diff ---\n{diff_text or 'No diff found'}")
        except Exception as e:
            context_parts.append(f"--- Git Info Error: {e} ---")

        # Scan for key markdown artifacts in the worktree
        artifact_names = ["TASK.md", "ROOT_CAUSE.md", "IMPLEMENTATION.md", "QA.md", "REVIEW.md"]
        for art_name in artifact_names:
            art_path = os.path.join(worktree_path, art_name)
            if os.path.exists(art_path):
                try:
                    with open(art_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(5000) # limit to prevent blowing token budget
                        context_parts.append(f"--- Artifact {art_name} ---\n{content}")
                except Exception as e:
                    logger.warning(f"Could not read artifact {art_path}: {e}")

        return "\n\n".join(context_parts)

    def _build_full_prompt(self, prompt: str, system_instruction: str, worktree_context: str) -> str:
        schema_format = json.dumps({
            "decision": "APPROVED | NEEDS_CHANGES | BLOCKED",
            "summary": "Concise summary of review findings",
            "findings": ["finding 1", "finding 2"],
            "required_changes": ["required change 1"],
            "confidence": 0.95
        }, indent=2)

        return (
            f"{system_instruction}\n\n"
            f"CRITICAL SAFETY INSTRUCTION:\n"
            f"You are a strict, read-only senior reviewer.\n"
            f"Do NOT modify, create, or delete any files.\n"
            f"Do NOT execute shell commands.\n"
            f"Perform analysis ONLY based on the task description and worktree context below.\n\n"
            f"--- TASK & VERIFICATION DETAILS ---\n"
            f"{prompt}\n\n"
            f"--- WORKTREE CONTEXT ---\n"
            f"{worktree_context}\n\n"
            f"--- OUTPUT SPECIFICATION ---\n"
            f"You MUST respond ONLY with a valid JSON object matching this schema:\n"
            f"{schema_format}\n"
            f"Valid decision values are: 'APPROVED', 'NEEDS_CHANGES', or 'BLOCKED'.\n"
            f"Do NOT wrap with markdown comments or explanation outside the JSON."
        )

    def _extract_json(self, raw_text: str) -> Dict[str, Any]:
        """Extract and parse the JSON object from raw response text."""
        # 1. Try direct parse
        cleaned = raw_text.strip()
        try:
            return json.loads(cleaned)
        except Exception:
            pass

        # 2. Look for ```json ... ``` block
        code_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except Exception:
                pass

        # 3. Look for outermost { ... }
        match = re.search(r'(\{[\s\S]*\})', raw_text)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        raise AbacusReviewerError(f"Malformed JSON output from Abacus reviewer: {raw_text[:300]}")

    async def chat(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_instruction: str,
        workspaces: List[str]
    ) -> BaseModel:
        accumulated_text = ""
        structured_data = None

        async for chunk in self.stream_chat(prompt, schema, system_instruction, workspaces):
            if chunk.get("type") == "text":
                accumulated_text += chunk.get("content", "")
            elif chunk.get("type") == "structured_output":
                structured_data = chunk.get("data")

        if structured_data:
            return schema.model_validate(structured_data)
        
        parsed = self._extract_json(accumulated_text)
        return schema.model_validate(parsed)

    async def stream_chat(
        self,
        prompt: str,
        schema: Type[BaseModel],
        system_instruction: str,
        workspaces: List[str],
        model: str = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not self.is_available():
            raise AbacusReviewerError(
                f"Abacus AI CLI executable was not found. Looked at: {self.cli_path or 'PATH'}. "
                "Ensure abacusai is installed and authenticated via 'abacusai auth login'."
            )

        worktree_path = workspaces[0] if workspaces else ""
        worktree_context = await self._gather_worktree_context(worktree_path)
        full_prompt = self._build_full_prompt(prompt, system_instruction, worktree_context)

        cmd = [
            self.cli_path,
            "-p", full_prompt,
            "--permission-mode", "plan",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--disallowed-tools", "file_write",
            "--disallowed-tools", "file_str_replace",
            "--disallowed-tools", "bash",
            "--disallowed-tools", "shell_start"
        ]
        
        if model and model not in ("default", "auto"):
            cmd.extend(["--model", model])

        logger.info(f"Invoking Abacus CLI reviewer in plan mode with timeout {self.timeout}s")
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=worktree_path if (worktree_path and os.path.exists(worktree_path)) else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        except Exception as e:
            raise AbacusReviewerError(f"Failed to spawn Abacus CLI process: {e}")

        full_text = ""
        deadline = asyncio.get_event_loop().time() + self.timeout

        async def read_stream():
            nonlocal full_text
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except asyncio.TimeoutError:
                    raise
                if not line:
                    break
                line_str = line.decode('utf-8', errors='replace').strip()
                if not line_str:
                    continue
                try:
                    payload = json.loads(line_str)
                    if payload.get("type") == "event" and payload.get("event", {}).get("type") == "text_delta":
                        content = payload["event"].get("content", "")
                        if content:
                            full_text += content
                            yield {"type": "text", "content": content}
                except json.JSONDecodeError:
                    pass

        try:
            async for chunk in read_stream():
                yield chunk

            # Wait for process to terminate with remaining timeout
            remaining = max(1.0, deadline - asyncio.get_event_loop().time())
            stdout_rem, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=remaining)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.communicate()
            except Exception:
                pass
            raise AbacusReviewerError(f"Abacus reviewer timed out after {self.timeout} seconds")

        if proc.returncode != 0:
            err_msg = stderr_bytes.decode('utf-8', errors='replace').strip()
            raise AbacusReviewerError(
                f"Abacus CLI exited with non-zero code {proc.returncode}: {err_msg[:400]}"
            )

        if not full_text.strip():
            # If no streaming deltas were received, check remaining stdout
            stdout_str = stdout_rem.decode('utf-8', errors='replace').strip()
            if stdout_str:
                full_text = stdout_str

        if not full_text.strip():
            raise AbacusReviewerError("Abacus reviewer returned empty output")

        # Parse and validate structured output
        parsed_dict = self._extract_json(full_text)
        try:
            validated = schema.model_validate(parsed_dict)
        except Exception as e:
            raise AbacusReviewerError(f"Abacus review schema validation failed: {e}")

        yield {"type": "structured_output", "data": validated.model_dump()}
