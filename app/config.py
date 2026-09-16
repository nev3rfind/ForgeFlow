"""Central configuration for ForgeFlow.

All settings are read from environment variables with sensible defaults so the
application can be configured without modifying source code. No secrets are
stored here; secrets (e.g. API keys) are read from the environment at runtime.
"""
import os
from dataclasses import dataclass
from typing import Optional


def get_env_or_registry(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve an environment variable, falling back to Windows User/System registry if on Windows."""
    val = os.environ.get(key)
    if val:
        return val
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as k:
                val, _ = winreg.QueryValueEx(k, key)
                if val:
                    os.environ[key] = str(val)
                    return str(val)
        except Exception:
            pass
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as k:
                val, _ = winreg.QueryValueEx(k, key)
                if val:
                    os.environ[key] = str(val)
                    return str(val)
        except Exception:
            pass
    return default


# Proactively resolve GEMINI_API_KEY from Windows User registry if not present in process env
get_env_or_registry("GEMINI_API_KEY")

_CANONICAL_WORKSPACE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "runtime", "worktrees")
)


def _bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).lower() in ("true", "1", "yes", "on")


@dataclass
class Settings:
    database_path: str = "forgeflow.db"
    host: str = "0.0.0.0"
    port: int = 8000
    workspace_root: str = _CANONICAL_WORKSPACE_ROOT

    abacus_reviewer_enabled: bool = False
    abacus_reviewer_fallback_enabled: bool = True
    abacus_review_mode: str = "every_iteration"
    abacusai_path: str = ""
    abacus_timeout: int = 120

    implementation_provider: str = "antigravity"
    agy_timeout: int = 600  # seconds; overridable via FORGEFLOW_AGY_TIMEOUT

    default_max_iterations: int = 5
    command_timeout: int = 300
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        raw_ws = os.environ.get("FORGEFLOW_WORKSPACE_ROOT")
        workspace_root = os.path.abspath(raw_ws) if raw_ws else _CANONICAL_WORKSPACE_ROOT
        return cls(
            database_path=os.environ.get("FORGEFLOW_DB_PATH", "forgeflow.db"),
            host=os.environ.get("FORGEFLOW_HOST", "0.0.0.0"),
            port=int(os.environ.get("FORGEFLOW_PORT", "8000")),
            workspace_root=workspace_root,
            abacus_reviewer_enabled=_bool("ABACUS_REVIEWER_ENABLED", "false"),
            abacus_reviewer_fallback_enabled=_bool("ABACUS_REVIEWER_FALLBACK_ENABLED", "true"),
            abacus_review_mode=os.environ.get("ABACUS_REVIEW_MODE", "every_iteration"),
            abacusai_path=os.environ.get("ABACUSAI_PATH", ""),
            abacus_timeout=int(os.environ.get("ABACUS_TIMEOUT", "120")),
            implementation_provider=os.environ.get("FORGEFLOW_IMPLEMENTATION_PROVIDER", "antigravity").lower(),
            agy_timeout=int(os.environ.get("FORGEFLOW_AGY_TIMEOUT", "600")),
            default_max_iterations=int(os.environ.get("FORGEFLOW_MAX_ITERATIONS", "5")),
            command_timeout=int(os.environ.get("FORGEFLOW_COMMAND_TIMEOUT", "300")),
            log_level=os.environ.get("FORGEFLOW_LOG_LEVEL", "INFO"),
        )

    def public_dict(self) -> dict:
        """Non-secret settings safe to expose to the browser."""
        return {
            "database_path": self.database_path,
            "host": self.host,
            "port": self.port,
            "workspace_root": self.workspace_root,
            "abacus_reviewer_enabled": self.abacus_reviewer_enabled,
            "abacus_reviewer_fallback_enabled": self.abacus_reviewer_fallback_enabled,
            "abacus_review_mode": self.abacus_review_mode,
            "abacus_timeout": self.abacus_timeout,
            "implementation_provider": self.implementation_provider,
            "agy_timeout": self.agy_timeout,
            "default_max_iterations": self.default_max_iterations,
            "command_timeout": self.command_timeout,
            "log_level": self.log_level,
        }

settings = Settings.from_env()
