import asyncio
import os
import re
import shlex
from typing import Optional, Dict

# Characters that enable shell chaining / redirection / substitution.
# A project's test command is user-supplied config, so it must not be able to
# escape into arbitrary shell execution.
_SHELL_METACHARS = re.compile(r"[;&|`$><\n\r]|\$\(|\|\|")

# Commands that are never legitimate as a project test command.
_DENIED_EXECUTABLES = {
    "rm", "rmdir", "del", "format", "mkfs", "dd", "shutdown", "reboot",
    "curl", "wget", "nc", "netcat", "telnet", "ssh", "scp", "ftp",
    "powershell", "pwsh", "cmd", "bash", "sh", "zsh", "csh",
    "reg", "regedit", "net", "netsh", "schtasks", "at", "crontab",
    "chmod", "chown", "sudo", "su", "runas", "takeown", "icacls",
}


class CommandValidationError(ValueError):
    """Raised when a configured command is rejected as unsafe."""


def validate_command(command: str) -> str:
    """Reject commands containing shell metacharacters or denied executables.

    Returns the command unchanged when it is safe to run.
    """
    if not command or not command.strip():
        raise CommandValidationError("Command is empty")

    if _SHELL_METACHARS.search(command):
        raise CommandValidationError(
            "Command contains shell metacharacters (; & | ` $ > <) which are not allowed"
        )

    try:
        parts = shlex.split(command, posix=False)
    except ValueError as e:
        raise CommandValidationError(f"Command could not be parsed: {e}")

    if not parts:
        raise CommandValidationError("Command is empty")

    exe = os.path.basename(parts[0].strip('"').strip("'")).lower()
    if exe.endswith(".exe"):
        exe = exe[:-4]
    if exe in _DENIED_EXECUTABLES:
        raise CommandValidationError(f"Executable '{exe}' is not permitted as a test command")

    return command


# Environment variables containing sensitive credentials that must not leak
# into project test / build subprocesses.
SENSITIVE_ENV_VARS = frozenset({
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ABACUS_API_KEY",
    "FORGEFLOW_API_KEY",
    "FORGEFLOW_SECRET",
})


def is_sensitive_env_var(name: str) -> bool:
    """Return True if name corresponds to a protected credential (case-insensitive)."""
    return bool(name) and name.strip().upper() in SENSITIVE_ENV_VARS


class CommandResult:
    def __init__(self, command: str, exit_code: int, stdout: str, stderr: str, duration: float):
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration

class CommandRunner:
    async def run(self, command: str, cwd: str, timeout: int = 300, env: Optional[Dict[str, str]] = None) -> CommandResult:
        validate_command(command)

        start_time = asyncio.get_event_loop().time()
        
        # Scrub sensitive host API keys while preserving safe environment (case-insensitive)
        merged_env = {k: v for k, v in os.environ.items() if not is_sensitive_env_var(k)}
        if env:
            # Caller-supplied overrides: filter out protected keys without mutating caller's dict
            safe_env_overrides = {k: v for k, v in env.items() if not is_sensitive_env_var(k)}
            merged_env.update(safe_env_overrides)

        # On Windows, we need shell=True for things like 'pytest' or 'gradlew' easily
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise TimeoutError(f"Command '{command}' timed out after {timeout} seconds")

        duration = asyncio.get_event_loop().time() - start_time
        
        return CommandResult(
            command=command,
            exit_code=process.returncode,
            stdout=stdout.decode().strip(),
            stderr=stderr.decode().strip(),
            duration=duration
        )
