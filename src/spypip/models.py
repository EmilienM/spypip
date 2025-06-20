"""
Data models for SpyPip.
"""

from dataclasses import dataclass


@dataclass
class PackagingChange:
    """Represents a change to a packaging file."""

    file_path: str
    change_type: str  # 'added', 'modified', 'removed'
    additions: int
    deletions: int
    patch: str


@dataclass
class CommitSummary:
    """Summary of a commit with packaging changes."""

    sha: str
    title: str
    author: str
    url: str
    date: str
    packaging_changes: list[PackagingChange]
    ai_summary: str | None = None


@dataclass
class PatchFailure:
    """Information about a failed patch application."""

    patch_name: str
    error_output: str
