"""
SpyPip - Python Packaging Version Analyzer

A tool that analyzes GitHub repositories to compare commits between versions/tags that touch
Python packaging files and provides AI-powered summaries of packaging-related changes.
"""

__version__ = "0.1.0"
__author__ = "Emilien Macchi"
__email__ = "emacchi@redhat.com"

from .analyzer import PackagingVersionAnalyzer, PackagingChange, CommitSummary
from .config import (
    load_environment_variables,
    get_required_env_var,
    get_optional_env_var,
)

__all__ = [
    "PackagingVersionAnalyzer",
    "PackagingChange",
    "CommitSummary",
    "load_environment_variables",
    "get_required_env_var",
    "get_optional_env_var",
    "__version__",
]
