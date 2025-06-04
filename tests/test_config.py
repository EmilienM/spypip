"""
Tests for the config module.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from spypip.config import (
    load_environment_variables,
    get_required_env_var,
    get_optional_env_var,
)


def test_get_optional_env_var():
    """Test getting optional environment variables."""
    # Test with existing environment variable
    with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
        assert get_optional_env_var("TEST_VAR") == "test_value"
        assert get_optional_env_var("TEST_VAR", "default") == "test_value"
    
    # Test with non-existing environment variable
    assert get_optional_env_var("NON_EXISTENT_VAR") == ""
    assert get_optional_env_var("NON_EXISTENT_VAR", "default_value") == "default_value"


def test_get_required_env_var():
    """Test getting required environment variables."""
    # Test with existing environment variable
    with patch.dict(os.environ, {"REQUIRED_VAR": "required_value"}):
        assert get_required_env_var("REQUIRED_VAR") == "required_value"
    
    # Test with non-existing environment variable
    with pytest.raises(SystemExit):
        get_required_env_var("NON_EXISTENT_REQUIRED_VAR")


def test_load_environment_variables_without_dotenv():
    """Test that load_environment_variables works without python-dotenv."""
    with patch("spypip.config.DOTENV_AVAILABLE", False):
        # Should not raise any exception
        load_environment_variables()


def test_load_environment_variables_with_dotenv():
    """Test loading environment variables from .env file."""
    # Create a temporary .env file
    with tempfile.TemporaryDirectory() as temp_dir:
        env_file = Path(temp_dir) / ".env"
        env_file.write_text("TEST_ENV_VAR=test_from_dotenv\nANOTHER_VAR=another_value\n")
        
        # Patch the current working directory and load_dotenv
        with patch("spypip.config.Path.cwd", return_value=Path(temp_dir)):
            with patch("spypip.config.DOTENV_AVAILABLE", True):
                with patch("spypip.config.load_dotenv") as mock_load_dotenv:
                    load_environment_variables()
                    mock_load_dotenv.assert_called_once_with(env_file, override=False)


def test_load_environment_variables_no_env_file():
    """Test that load_environment_variables handles missing .env files gracefully."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Mock Path.exists to always return False for any .env file
        def mock_exists(self):
            return str(self).endswith('.env') and False

        with patch("spypip.config.DOTENV_AVAILABLE", True):
            with patch("spypip.config.load_dotenv") as mock_load_dotenv:
                with patch.object(Path, 'exists', mock_exists):
                    load_environment_variables()
                    mock_load_dotenv.assert_not_called()