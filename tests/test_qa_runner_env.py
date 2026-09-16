import os
import pytest
from app.qa.runner import CommandRunner


@pytest.mark.asyncio
async def test_qa_runner_scrubs_gemini_api_key(tmp_path):
    runner = CommandRunner()

    # Create a small script that inspects its environment
    script = tmp_path / "check_env.py"
    script.write_text(
        "import os\n"
        "print('GEMINI=' + str(os.environ.get('GEMINI_API_KEY')))\n"
        "print('OPENAI=' + str(os.environ.get('OPENAI_API_KEY')))\n",
        encoding="utf-8"
    )

    # Set mock sensitive environment variables in parent process
    os.environ["GEMINI_API_KEY"] = "mock_secret_key_12345"
    os.environ["OPENAI_API_KEY"] = "mock_openai_secret"

    try:
        res = await runner.run("python check_env.py", cwd=str(tmp_path))

        assert res.exit_code == 0
        assert "GEMINI=None" in res.stdout
        assert "OPENAI=None" in res.stdout
        # Confirm no secret appears in stdout or stderr
        assert "mock_secret_key" not in res.stdout
        assert "mock_openai_secret" not in res.stdout
    finally:
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)


@pytest.mark.asyncio
async def test_qa_runner_preserves_explicit_env(tmp_path):
    runner = CommandRunner()

    script = tmp_path / "check_custom.py"
    script.write_text(
        "import os\n"
        "print('CUSTOM=' + str(os.environ.get('MY_CUSTOM_TEST_VAR')))\n",
        encoding="utf-8"
    )

    caller_env = {"MY_CUSTOM_TEST_VAR": "custom_safe_value"}
    res = await runner.run(
        "python check_custom.py",
        cwd=str(tmp_path),
        env=caller_env
    )

    assert res.exit_code == 0
    assert "CUSTOM=custom_safe_value" in res.stdout
    # Ensure caller's dictionary was not mutated
    assert caller_env == {"MY_CUSTOM_TEST_VAR": "custom_safe_value"}


@pytest.mark.asyncio
async def test_qa_runner_scrubs_case_insensitive_sensitive_vars(tmp_path):
    """Verify uppercase, lowercase, and mixed-case sensitive variables are scrubbed from inherited env."""
    runner = CommandRunner()

    script = tmp_path / "check_case_env.py"
    script.write_text(
        "import os\n"
        "print('UPPER=' + str(os.environ.get('GEMINI_API_KEY')))\n"
        "print('LOWER=' + str(os.environ.get('abacus_api_key')))\n"
        "print('MIXED=' + str(os.environ.get('Anthropic_Api_Key')))\n",
        encoding="utf-8"
    )

    os.environ["GEMINI_API_KEY"] = "secret_upper_123"
    os.environ["abacus_api_key"] = "secret_lower_456"
    os.environ["Anthropic_Api_Key"] = "secret_mixed_789"

    try:
        res = await runner.run("python check_case_env.py", cwd=str(tmp_path))
        assert res.exit_code == 0
        assert "UPPER=None" in res.stdout
        assert "LOWER=None" in res.stdout
        assert "MIXED=None" in res.stdout
        assert "secret_upper_123" not in res.stdout
        assert "secret_lower_456" not in res.stdout
        assert "secret_mixed_789" not in res.stdout
    finally:
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("abacus_api_key", None)
        os.environ.pop("Anthropic_Api_Key", None)


@pytest.mark.asyncio
async def test_qa_runner_scrubs_caller_supplied_sensitive_overrides(tmp_path):
    """Verify caller-supplied explicit env dictionary cannot reintroduce sensitive keys in any casing."""
    runner = CommandRunner()

    script = tmp_path / "check_override_env.py"
    script.write_text(
        "import os\n"
        "print('GEMINI=' + str(os.environ.get('gemini_api_key')))\n"
        "print('OPENAI=' + str(os.environ.get('OPENAI_API_KEY')))\n"
        "print('FORGE=' + str(os.environ.get('ForgeFlow_Secret')))\n"
        "print('SAFE=' + str(os.environ.get('SAFE_USER_VAR')))\n",
        encoding="utf-8"
    )

    caller_env = {
        "gemini_api_key": "dangerous_leak_gemini",
        "OPENAI_API_KEY": "dangerous_leak_openai",
        "ForgeFlow_Secret": "dangerous_leak_secret",
        "SAFE_USER_VAR": "legitimate_override",
    }
    caller_env_copy = dict(caller_env)

    res = await runner.run("python check_override_env.py", cwd=str(tmp_path), env=caller_env)

    assert res.exit_code == 0
    assert "GEMINI=None" in res.stdout
    assert "OPENAI=None" in res.stdout
    assert "FORGE=None" in res.stdout
    assert "SAFE=legitimate_override" in res.stdout
    assert "dangerous_leak" not in res.stdout

    # Ensure caller's dictionary was not mutated
    assert caller_env == caller_env_copy
