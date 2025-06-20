"""
SpyPip - Python Packaging Version Analyzer

A tool that analyzes GitHub repositories to compare commits between versions/tags that touch
Python packaging files and provides AI-powered summaries of packaging-related changes.
"""

__version__ = "0.1.0"
__author__ = "Emilien Macchi"
__email__ = "emacchi@redhat.com"

# Import from the refactored analyzer (keeping backward compatibility)
from .analyzer import PackagingVersionAnalyzer
from .config import (
    get_optional_env_var,
    get_required_env_var,
    load_environment_variables,
)
from .exceptions import (
    ConfigurationError,
    GitOperationError,
    LLMError,
    MCPError,
    PatchApplicationError,
    PatchError,
    PatchParsingError,
    RepositoryError,
    SpyPipError,
)
from .models import CommitSummary, PackagingChange, PatchFailure

__all__ = [
    "CommitSummary",
    "ConfigurationError",
    "GitOperationError",
    "LLMError",
    "MCPError",
    "PackagingChange",
    "PackagingVersionAnalyzer",
    "PatchApplicationError",
    "PatchError",
    "PatchFailure",
    "PatchParsingError",
    "RepositoryError",
    "SpyPipError",
    "__version__",
    "get_optional_env_var",
    "get_required_env_var",
    "load_environment_variables",
]
