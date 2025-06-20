"""
Custom exceptions for SpyPip.
"""


class SpyPipError(Exception):
    """Base exception for all SpyPip errors."""

    pass


class ConfigurationError(SpyPipError):
    """Raised when there's an issue with configuration."""

    pass


class RepositoryError(SpyPipError):
    """Raised when there's an issue with repository operations."""

    pass


class PatchError(SpyPipError):
    """Raised when there's an issue with patch operations."""

    pass


class MCPError(SpyPipError):
    """Raised when there's an issue with MCP operations."""

    pass


class LLMError(SpyPipError):
    """Raised when there's an issue with LLM operations."""

    pass


class GitOperationError(RepositoryError):
    """Raised when git operations fail."""

    pass


class PatchApplicationError(PatchError):
    """Raised when patch application fails."""

    pass


class PatchParsingError(PatchError):
    """Raised when patch parsing fails."""

    pass
