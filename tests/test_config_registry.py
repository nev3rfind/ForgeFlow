import os
import pytest
from unittest.mock import patch, MagicMock
from app.config import get_env_or_registry


def test_env_var_takes_precedence():
    test_key = "FORGEFLOW_MOCK_ENV_TEST_KEY"
    os.environ[test_key] = "mock-env-precedence-value"
    try:
        val = get_env_or_registry(test_key)
        assert val == "mock-env-precedence-value"
    finally:
        os.environ.pop(test_key, None)


def test_registry_fallback_when_env_unset():
    test_key = "FORGEFLOW_MOCK_REG_TEST_KEY"
    os.environ.pop(test_key, None)

    mock_key_obj = MagicMock()
    # Mock winreg.OpenKey as context manager and winreg.QueryValueEx returning a mock value
    mock_open_key = MagicMock()
    mock_open_key.return_value.__enter__.return_value = mock_key_obj
    mock_open_key.return_value.__exit__.return_value = False

    with patch("os.name", "nt"), \
         patch("winreg.OpenKey", mock_open_key), \
         patch("winreg.QueryValueEx", return_value=("mock-registry-stored-value", 1)):
        val = get_env_or_registry(test_key)
        assert val == "mock-registry-stored-value"
        # Verify it was propagated into os.environ for child subprocesses
        assert os.environ.get(test_key) == "mock-registry-stored-value"

    os.environ.pop(test_key, None)


def test_missing_value_returns_default():
    test_key = "FORGEFLOW_MOCK_MISSING_KEY"
    os.environ.pop(test_key, None)

    mock_open_key = MagicMock(side_effect=FileNotFoundError("Mock registry key not found"))

    with patch("os.name", "nt"), \
         patch("winreg.OpenKey", mock_open_key):
        val = get_env_or_registry(test_key, default="fallback_default")
        assert val == "fallback_default"
        assert os.environ.get(test_key) is None
