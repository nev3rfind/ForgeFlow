"""Comprehensive tests for AgyProvider and agy_adapter helpers."""
import asyncio
import json
import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from pydantic import BaseModel

from app.integrations.agy_adapter import (
    AgyProvider,
    AgyProviderError,
    _extract_last_json_object,
    _kill_process_tree,
    _is_sensitive,
    _safe_child_env,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------
class DummySchema(BaseModel):
    message: str


class NestedSchema(BaseModel):
    summary: str
    count: int


@pytest.fixture
def agy_provider():
    with patch("app.integrations.agy_adapter.shutil.which", return_value="/mock/path/agy"):
        with patch("app.integrations.agy_adapter.get_env_or_registry", return_value=None):
            with patch("os.path.isfile", return_value=True):
                # Avoid the official Windows path lookup returning something
                with patch("sys.platform", "linux"):
                    return AgyProvider()


@pytest.fixture
def mock_process():
    process = MagicMock()
    process.returncode = 0
    process.pid = 12345
    process.stdout = AsyncMock()
    process.stderr = AsyncMock()
    process.stderr.read = AsyncMock(return_value=b"")
    process.wait = AsyncMock()
    process.terminate = MagicMock()
    return process


@pytest.fixture
def mock_subprocess(mock_process):
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_process
        yield mock_exec, mock_process


# ===========================================================================
# 1. _extract_last_json_object – balanced-brace extractor
# ===========================================================================
class TestExtractLastJsonObject:
    def test_simple_object(self):
        result = _extract_last_json_object('{"message": "hello"}')
        assert result == {"message": "hello"}

    def test_nested_object(self):
        text = '{"outer": {"inner": 1}, "k": 2}'
        result = _extract_last_json_object(text)
        assert result == {"outer": {"inner": 1}, "k": 2}

    def test_multiple_objects_returns_last(self):
        text = '{"a": 1} some text in between {"b": 2}'
        result = _extract_last_json_object(text)
        assert result == {"b": 2}

    def test_natural_language_before_after(self):
        text = "I found the answer here: {\"result\": \"done\"} and that is all."
        result = _extract_last_json_object(text)
        assert result == {"result": "done"}

    def test_braces_inside_string_value(self):
        text = '{"message": "contains {braces} in value"}'
        result = _extract_last_json_object(text)
        assert result == {"message": "contains {braces} in value"}

    def test_escaped_quote_inside_string(self):
        text = r'{"msg": "he said \"hello\""}'
        result = _extract_last_json_object(text)
        assert result is not None
        assert "msg" in result

    def test_no_json_returns_none(self):
        result = _extract_last_json_object("no json here at all")
        assert result is None

    def test_malformed_json_returns_none(self):
        result = _extract_last_json_object("{this is not json}")
        assert result is None

    def test_intermediate_json_then_final_json(self):
        """Must return the LAST valid object, not an intermediate one."""
        text = (
            'Investigating... found {"intermediate": true} in the code, '
            'here is my final answer: {"summary": "done", "count": 5}'
        )
        result = _extract_last_json_object(text)
        assert result == {"summary": "done", "count": 5}

    def test_deeply_nested(self):
        text = '{"a": {"b": {"c": {"d": 42}}}}'
        result = _extract_last_json_object(text)
        assert result == {"a": {"b": {"c": {"d": 42}}}}

    def test_array_value(self):
        text = '{"items": [1, 2, 3], "ok": true}'
        result = _extract_last_json_object(text)
        assert result == {"items": [1, 2, 3], "ok": True}

    def test_empty_string_returns_none(self):
        result = _extract_last_json_object("")
        assert result is None

    def test_partial_json_returns_none(self):
        result = _extract_last_json_object('{"message": "incomplete')
        assert result is None


# ===========================================================================
# 2. Credential / secret isolation
# ===========================================================================
class TestSecretIsolation:
    def test_is_sensitive_gemini(self):
        assert _is_sensitive("GEMINI_API_KEY") is True

    def test_is_sensitive_openai(self):
        assert _is_sensitive("OPENAI_API_KEY") is True

    def test_is_sensitive_anthropic(self):
        assert _is_sensitive("ANTHROPIC_API_KEY") is True

    def test_is_sensitive_abacus(self):
        assert _is_sensitive("ABACUS_API_KEY") is True

    def test_is_sensitive_forgeflow(self):
        assert _is_sensitive("FORGEFLOW_API_KEY") is True

    def test_is_sensitive_forgeflow_secret(self):
        assert _is_sensitive("FORGEFLOW_SECRET") is True

    def test_is_sensitive_case_insensitive(self):
        assert _is_sensitive("gemini_api_key") is True
        assert _is_sensitive("Gemini_Api_Key") is True

    def test_is_sensitive_safe_var(self):
        assert _is_sensitive("PATH") is False
        assert _is_sensitive("HOME") is False

    def test_safe_child_env_removes_secrets(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "secret", "PATH": "/bin"}):
            env = _safe_child_env()
            assert "GEMINI_API_KEY" not in env
            assert "PATH" in env

    def test_safe_child_env_removes_all_known_secrets(self):
        fake_env = {
            "GEMINI_API_KEY": "g",
            "OPENAI_API_KEY": "o",
            "ANTHROPIC_API_KEY": "a",
            "ABACUS_API_KEY": "b",
            "FORGEFLOW_API_KEY": "f",
            "FORGEFLOW_SECRET": "s",
            "SAFE_VAR": "keep",
        }
        with patch.dict(os.environ, fake_env, clear=True):
            env = _safe_child_env()
        for secret in fake_env:
            if secret != "SAFE_VAR":
                assert secret not in env
        assert env.get("SAFE_VAR") == "keep"


# ===========================================================================
# 3. Executable discovery
# ===========================================================================
class TestExecutableDiscovery:
    def test_explicit_forgeflow_agt_path_used_first(self):
        with patch("app.integrations.agy_adapter.get_env_or_registry", return_value="/explicit/agy.exe"):
            with patch("os.path.isfile", return_value=True):
                p = AgyProvider()
                assert p.exe_path == "/explicit/agy.exe"

    def test_explicit_path_missing_falls_through(self):
        def fake_isfile(path):
            return path == "/bin/agy"  # only the which path exists

        with patch("app.integrations.agy_adapter.get_env_or_registry", return_value="/missing/agy.exe"):
            with patch("os.path.isfile", side_effect=fake_isfile):
                with patch("app.integrations.agy_adapter.shutil.which", return_value="/bin/agy"):
                    with patch("sys.platform", "linux"):
                        p = AgyProvider()
                        assert p.exe_path == "/bin/agy"

    def test_path_via_shutil_which(self):
        with patch("app.integrations.agy_adapter.get_env_or_registry", return_value=None):
            with patch("app.integrations.agy_adapter.shutil.which", return_value="/usr/bin/agy"):
                with patch("os.path.isfile", return_value=True):
                    with patch("sys.platform", "linux"):
                        p = AgyProvider()
                        assert p.exe_path == "/usr/bin/agy"

    def test_missing_executable_raises(self):
        with patch("app.integrations.agy_adapter.get_env_or_registry", return_value=None):
            with patch("app.integrations.agy_adapter.shutil.which", return_value=None):
                with patch("os.path.isfile", return_value=False):
                    with pytest.raises(AgyProviderError, match="Could not find the 'agy' CLI"):
                        AgyProvider()

    def test_windows_official_path_preferred_over_which(self):
        """On Windows the official install path has higher priority than PATH which."""
        official = r"C:\Users\testuser\AppData\Local\agy\bin\agy.exe"

        def fake_isfile(path):
            return path == official

        with patch("app.integrations.agy_adapter.get_env_or_registry", return_value=None):
            with patch("os.path.isfile", side_effect=fake_isfile):
                with patch("sys.platform", "win32"):
                    # Simulate the default Windows path resolving to our official path
                    with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\testuser\AppData\Local"}, clear=False):
                        with patch("app.integrations.agy_adapter.shutil.which", return_value=r"C:\some\other\agy.exe"):
                            p = AgyProvider()
                            assert p.exe_path == official


# ===========================================================================
# 4. Command construction and cwd isolation
# ===========================================================================
class TestCommandConstruction:
    @pytest.mark.asyncio
    async def test_cwd_is_first_workspace(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "hi"}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            await agy_provider.chat("prompt", DummySchema, "system", [workspace])
            kwargs = mock_exec.call_args[1]
            assert kwargs["cwd"] == workspace

    @pytest.mark.asyncio
    async def test_prompt_cannot_override_cwd(self, agy_provider, mock_subprocess):
        """A prompt containing a path must not affect cwd."""
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "ok"}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            await agy_provider.chat("Use directory C:\\Windows\\System32", DummySchema, "sys", [workspace])
            kwargs = mock_exec.call_args[1]
            assert kwargs["cwd"] == workspace

    @pytest.mark.asyncio
    async def test_missing_workspace_raises(self, agy_provider):
        with pytest.raises(AgyProviderError, match="No workspace provided"):
            await agy_provider.chat("prompt", DummySchema, "sys", [])

    @pytest.mark.asyncio
    async def test_invalid_workspace_dir_raises(self, agy_provider):
        with pytest.raises(AgyProviderError, match="does not exist"):
            await agy_provider.chat("prompt", DummySchema, "sys", ["/nonexistent/path/xyz"])

    @pytest.mark.asyncio
    async def test_gemini_key_not_in_child_env(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "x"}}}).encode() + b"\n",
            b"",
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "should-be-removed"}):
            with tempfile.TemporaryDirectory() as workspace:
                await agy_provider.chat("p", DummySchema, "s", [workspace])
                kwargs = mock_exec.call_args[1]
                assert "GEMINI_API_KEY" not in kwargs["env"]

    @pytest.mark.asyncio
    async def test_dangerously_skip_permissions_in_args(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "x"}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            await agy_provider.chat("p", DummySchema, "s", [workspace])
            args = mock_exec.call_args[0]
            assert "--dangerously-skip-permissions" in args
            assert "--sandbox" in args

    @pytest.mark.asyncio
    async def test_json_schema_flag_present(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "x"}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            await agy_provider.chat("p", DummySchema, "s", [workspace])
            args = mock_exec.call_args[0]
            assert "--json-schema" in args
            schema_idx = list(args).index("--json-schema") + 1
            parsed = json.loads(args[schema_idx])
            assert "properties" in parsed


# ===========================================================================
# 5. Structured output selection and validation
# ===========================================================================
class TestStructuredOutput:
    @pytest.mark.asyncio
    async def test_official_result_event_used(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "from result"}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            result = await agy_provider.chat("p", DummySchema, "s", [workspace])
            assert result.message == "from result"

    @pytest.mark.asyncio
    async def test_fallback_to_last_json_in_text(self, agy_provider, mock_subprocess):
        """When no result event, extract from agent text."""
        mock_exec, mock_process = mock_subprocess
        # Agent says something then emits JSON, then EOF (no result event)
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "step_update", "step_update": {"step_type": "agent_response", "state": "ACTIVE",
                                                                  "content": 'Intermediate {"message": "wrong"} then the final answer: {"message": "correct"}'}}).encode() + b"\n",
            b"",
        ]
        # With no result event and returncode=0:
        with tempfile.TemporaryDirectory() as workspace:
            result = await agy_provider.chat("p", DummySchema, "s", [workspace])
            # Must pick the LAST json object = {"message": "correct"}
            assert result.message == "correct"

    @pytest.mark.asyncio
    async def test_missing_result_raises(self, agy_provider, mock_subprocess):
        """No result event and no JSON in text → clear error."""
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "step_update", "step_update": {"step_type": "agent_response", "state": "ACTIVE",
                                                                  "content": "Just plain text, no JSON."}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            with pytest.raises(AgyProviderError, match="did not produce a valid structured result"):
                await agy_provider.chat("p", DummySchema, "s", [workspace])

    @pytest.mark.asyncio
    async def test_pydantic_validation_failure_raises(self, agy_provider, mock_subprocess):
        """Result event payload that doesn't match schema → clear error."""
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"wrong_field": 99}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            with pytest.raises(AgyProviderError):
                await agy_provider.chat("p", DummySchema, "s", [workspace])

    @pytest.mark.asyncio
    async def test_cli_error_status_raises(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.returncode = 1
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "result", "result": {"status": "ERROR", "error": "internal failure"}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            with pytest.raises(AgyProviderError, match="CLI Error: internal failure"):
                await agy_provider.chat("p", DummySchema, "s", [workspace])

    @pytest.mark.asyncio
    async def test_non_zero_exit_raises(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.returncode = 2
        mock_process.stderr.read = AsyncMock(return_value=b"fatal crash")
        mock_process.stdout.readline.side_effect = [b""]
        with tempfile.TemporaryDirectory() as workspace:
            with pytest.raises(AgyProviderError, match="exited with code 2"):
                await agy_provider.chat("p", DummySchema, "s", [workspace])

    @pytest.mark.asyncio
    async def test_multiple_json_objects_picks_last(self, agy_provider, mock_subprocess):
        """Multiple JSON blobs in agent text → only last one used for schema."""
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "step_update", "step_update": {
                "step_type": "agent_response", "state": "ACTIVE",
                "content": 'First: {"message": "first"} then {"message": "last"}'}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            result = await agy_provider.chat("p", DummySchema, "s", [workspace])
            assert result.message == "last"


# ===========================================================================
# 6. Stream events
# ===========================================================================
class TestStreamEvents:
    @pytest.mark.asyncio
    async def test_text_event_yielded(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "step_update", "step_update": {"step_type": "agent_response", "state": "ACTIVE", "content": "Working..."}}).encode() + b"\n",
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "done"}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            events = [e async for e in agy_provider.stream_chat("p", DummySchema, "s", [workspace])]
        text_events = [e for e in events if e["type"] == "text"]
        assert text_events[0]["content"] == "Working..."

    @pytest.mark.asyncio
    async def test_tool_call_event_yielded(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "step_update", "step_update": {"step_type": "tool", "state": "ACTIVE", "tool_info": {"name": "read_file", "parameters": {"path": "x.py"}}}}).encode() + b"\n",
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "done"}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            events = [e async for e in agy_provider.stream_chat("p", DummySchema, "s", [workspace])]
        tool_events = [e for e in events if e["type"] == "tool_call"]
        assert tool_events[0]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_structured_output_yielded_last(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "final"}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            events = [e async for e in agy_provider.stream_chat("p", DummySchema, "s", [workspace])]
        structured = [e for e in events if e["type"] == "structured_output"]
        assert len(structured) == 1
        assert structured[0]["data"]["message"] == "final"

    @pytest.mark.asyncio
    async def test_non_json_stdout_yielded_as_diagnostic(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            b"Fatal error: something went wrong\n",
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "ok"}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            events = [e async for e in agy_provider.stream_chat("p", DummySchema, "s", [workspace])]
        diag = [e for e in events if e["type"] == "diagnostic"]
        assert any("Fatal error" in d["content"] for d in diag)

    @pytest.mark.asyncio
    async def test_malformed_json_line_not_crash(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        mock_process.stdout.readline.side_effect = [
            b"this is definitely not json\n",
            b"{also not json\n",
            json.dumps({"event": "result", "result": {"status": "OK", "response": {"message": "survived"}}}).encode() + b"\n",
            b"",
        ]
        with tempfile.TemporaryDirectory() as workspace:
            result = await agy_provider.chat("p", DummySchema, "s", [workspace])
        assert result.message == "survived"


# ===========================================================================
# 7. Cancellation – Windows process-tree termination
# ===========================================================================
class TestCancellation:
    @pytest.mark.asyncio
    async def test_cancellation_calls_kill_process_tree(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess

        async def slow_readline():
            await asyncio.sleep(10)
            return b""

        mock_process.stdout.readline.side_effect = slow_readline

        with patch("app.integrations.agy_adapter._kill_process_tree", new_callable=AsyncMock) as mock_kill:
            with tempfile.TemporaryDirectory() as workspace:
                task = asyncio.create_task(agy_provider.chat("p", DummySchema, "s", [workspace]))
                await asyncio.sleep(0.05)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            mock_kill.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancellation_on_already_exited_process(self, agy_provider, mock_subprocess):
        """If the process already exited, kill_process_tree must not raise."""
        mock_exec, mock_process = mock_subprocess

        async def instant_readline():
            # Return EOF immediately, simulating quick exit
            return b""

        mock_process.stdout.readline.side_effect = instant_readline
        mock_process.returncode = 0

        # Should not raise even though process exited before kill
        with patch("app.integrations.agy_adapter._kill_process_tree", new_callable=AsyncMock):
            with tempfile.TemporaryDirectory() as workspace:
                # This should complete normally (EOF immediately), not hang
                with pytest.raises(AgyProviderError):
                    await agy_provider.chat("p", DummySchema, "s", [workspace])

    @pytest.mark.asyncio
    async def test_windows_kill_process_tree_uses_taskkill(self):
        """On Windows, _kill_process_tree must use taskkill /F /T /PID."""
        fake_taskkill = AsyncMock()
        fake_proc = MagicMock()
        fake_proc.wait = AsyncMock()
        fake_taskkill.return_value = fake_proc

        with patch("sys.platform", "win32"):
            with patch("asyncio.create_subprocess_exec", fake_taskkill):
                await _kill_process_tree(9999)

        args = fake_taskkill.call_args[0]
        assert "taskkill" in args
        assert "/F" in args
        assert "/T" in args
        assert "/PID" in args
        assert "9999" in args

    @pytest.mark.asyncio
    async def test_non_windows_kill_uses_sigterm(self):
        """On non-Windows, _kill_process_tree uses os.kill(SIGTERM)."""
        with patch("sys.platform", "linux"):
            with patch("os.kill") as mock_kill:
                import signal
                await _kill_process_tree(1234)
                mock_kill.assert_called_once_with(1234, signal.SIGTERM)

    @pytest.mark.asyncio
    async def test_non_windows_kill_handles_already_exited(self):
        """ProcessLookupError must not propagate."""
        with patch("sys.platform", "linux"):
            with patch("os.kill", side_effect=ProcessLookupError):
                # Must not raise
                await _kill_process_tree(9999)


# ===========================================================================
# 8. Timeout
# ===========================================================================
class TestTimeout:
    @pytest.mark.asyncio
    async def test_timeout_kills_process_and_raises(self, agy_provider, mock_subprocess):
        mock_exec, mock_process = mock_subprocess
        agy_provider.timeout = 1  # very short

        async def forever_readline():
            await asyncio.sleep(100)
            return b""

        mock_process.stdout.readline.side_effect = forever_readline

        with patch("app.integrations.agy_adapter._kill_process_tree", new_callable=AsyncMock) as mock_kill:
            with tempfile.TemporaryDirectory() as workspace:
                with pytest.raises(AgyProviderError, match="timed out"):
                    await agy_provider.chat("p", DummySchema, "s", [workspace])
            mock_kill.assert_awaited_once()


# ===========================================================================
# 9. Async EventBus callback (Blocking Issue 3)
# ===========================================================================
class TestAsyncEventBus:
    """Verify that event bus subscribers work with async callbacks."""

    @pytest.mark.asyncio
    async def test_async_callback_receives_events(self):
        """EventBus must correctly call an async subscriber."""
        from app.events.bus import EventBus

        bus = EventBus()
        received = []

        async def on_event(event):
            received.append(event)

        bus.subscribe("task-1", on_event)
        await bus.publish_raw("task-1", "AGENT_CHUNK", {"type": "text", "content": "hello"})
        assert len(received) == 1
        assert received[0].event_type == "AGENT_CHUNK"

    @pytest.mark.asyncio
    async def test_subscription_cleanup(self):
        """Unsubscribe must prevent further events from being delivered."""
        from app.events.bus import EventBus

        bus = EventBus()
        received = []

        async def on_event(event):
            received.append(event)

        bus.subscribe("task-2", on_event)
        bus.unsubscribe("task-2", on_event)
        await bus.publish_raw("task-2", "AGENT_CHUNK", {})
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_state_changed_event(self):
        """STATE_CHANGED events must be deliverable asynchronously."""
        from app.events.bus import EventBus

        bus = EventBus()
        received = []

        async def on_event(event):
            received.append(event)

        bus.subscribe("task-3", on_event)
        await bus.publish_raw("task-3", "STATE_CHANGED", {"status": "INVESTIGATING"})
        assert any(e.event_type == "STATE_CHANGED" for e in received)
