"""
Configuration module for SpyPip.

Handles loading environment variables from .env files and system environment.
"""

import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


def load_environment_variables() -> None:
    """
    Load environment variables from .env file if it exists.

    This function looks for .env files in the following order:
    1. Current working directory
    2. User's home directory
    3. Directory containing the spypip package

    If python-dotenv is not installed, this function will silently skip
    loading .env files and rely on system environment variables only.
    """
    if not DOTENV_AVAILABLE:
        return

    # Possible .env file locations in order of preference
    env_paths = [
        Path.cwd() / ".env",  # Current working directory
        Path.home() / ".env",  # User's home directory
        Path(__file__).parent.parent.parent / ".env",  # Project root
    ]

    for env_path in env_paths:
        if env_path.exists() and env_path.is_file():
            load_dotenv(env_path, override=False)
            break


def get_required_env_var(var_name: str, description: Optional[str] = None) -> str:
    """
    Get a required environment variable.

    Args:
        var_name: Name of the environment variable
        description: Optional description of what the variable is used for

    Returns:
        The value of the environment variable

    Raises:
        SystemExit: If the environment variable is not set
    """
    value = os.getenv(var_name)
    if not value:
        error_msg = f"Error: {var_name} environment variable not set"
        if description:
            error_msg += f"\n{description}"
        print(error_msg)
        raise SystemExit(1)
    return value


def get_optional_env_var(var_name: str, default: str = "") -> str:
    """
    Get an optional environment variable with a default value.

    Args:
        var_name: Name of the environment variable
        default: Default value if the variable is not set

    Returns:
        The value of the environment variable or the default value
    """
    return os.getenv(var_name, default)
