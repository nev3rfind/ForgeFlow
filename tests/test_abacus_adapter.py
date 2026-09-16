import pytest
import os
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from app.integrations.abacus_adapter import AbacusReviewerProvider, AbacusReviewerError
from app.agents.roles import ReviewResult

def test_find_cli_via_env():
    with patch.dict(os.environ, {"ABACUSAI_PATH": "C:\\custom\\abacusai.exe"}):
        with patch("os.path.exists", side_effect=lambda p: p == "C:\\custom\\abacusai.exe"):
            provider = AbacusReviewerProvider()
            assert provider.cli_path == "C:\\custom\\abacusai.exe"

def test_extract_json_direct():
    provider = AbacusReviewerProvider(cli_path="dummy")
    raw = '{"decision": "APPROVED", "summary": "Looks good", "findings": [], "required_changes": [], "confidence": 1.0}'
    data = provider._extract_json(raw)
    assert data["decision"] == "APPROVED"

def test_extract_json_markdown_code_block():
    provider = AbacusReviewerProvider(cli_path="dummy")
    raw = """Here is my review:
```json
{
  "decision": "NEEDS_CHANGES",
  "summary": "Fix syntax error",
  "findings": ["Syntax error on line 5"],
  "required_changes": ["Fix line 5"],
  "confidence": 0.9
}
```
Hope this helps!
"""
    data = provider._extract_json(raw)
    assert data["decision"] == "NEEDS_CHANGES"
    assert data["findings"] == ["Syntax error on line 5"]

def test_extract_json_embedded_in_prose():
    provider = AbacusReviewerProvider(cli_path="dummy")
    raw = """> Routed to Deepseek V4.1 Flash (Thinking)
Some thoughts here...
{"decision": "APPROVED", "summary": "Clean diff", "findings": [], "required_changes": [], "confidence": 0.95}
"""
    data = provider._extract_json(raw)
    assert data["decision"] == "APPROVED"

def test_extract_json_malformed_raises():
    provider = AbacusReviewerProvider(cli_path="dummy")
    raw = "Not a json at all! {invalid: json, "
    with pytest.raises(AbacusReviewerError):
        provider._extract_json(raw)

@pytest.mark.asyncio
async def test_abacus_cli_not_found_raises():
    provider = AbacusReviewerProvider(cli_path="/nonexistent/abacusai")
    with patch("os.path.exists", return_value=False):
        with pytest.raises(AbacusReviewerError) as exc:
            async for _ in provider.stream_chat("prompt", ReviewResult, "system", []):
                pass
        assert "executable was not found" in str(exc.value)

@pytest.mark.asyncio
async def test_abacus_cli_timeout():
    provider = AbacusReviewerProvider(cli_path="dummy", timeout=1)
    with patch.object(provider, "is_available", return_value=True):
        with patch.object(provider, "_gather_worktree_context", new_callable=AsyncMock, return_value="context"):
            mock_proc = MagicMock()
            mock_proc.stdout.readline = AsyncMock(side_effect=[b"", b""])
            async def slow_communicate():
                await asyncio.sleep(2)
                return b"", b""
            mock_proc.communicate = slow_communicate
            mock_proc.kill = MagicMock()

            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                with pytest.raises(AbacusReviewerError) as exc:
                    async for _ in provider.stream_chat("prompt", ReviewResult, "system", []):
                        pass
                assert "timed out" in str(exc.value)

@pytest.mark.asyncio
async def test_abacus_cli_nonzero_exit():
    provider = AbacusReviewerProvider(cli_path="dummy", timeout=5)
    with patch.object(provider, "is_available", return_value=True):
        with patch.object(provider, "_gather_worktree_context", new_callable=AsyncMock, return_value="context"):
            mock_proc = MagicMock()
            mock_proc.stdout.readline = AsyncMock(side_effect=[b"", b""])
            mock_proc.communicate = AsyncMock(return_value=(b"", b"Unauthorized: session expired"))
            mock_proc.returncode = 1

            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                with pytest.raises(AbacusReviewerError) as exc:
                    async for _ in provider.stream_chat("prompt", ReviewResult, "system", []):
                        pass
                assert "non-zero code 1" in str(exc.value)
