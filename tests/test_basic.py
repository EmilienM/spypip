"""Basic tests for spypip package."""

import pytest
from spypip import __version__, PackagingVersionAnalyzer, PackagingChange, CommitSummary


def test_version():
    """Test that version is defined."""
    assert __version__ == "0.1.0"


def test_imports():
    """Test that main classes can be imported."""
    assert PackagingVersionAnalyzer is not None
    assert PackagingChange is not None
    assert CommitSummary is not None


def test_packaging_change_dataclass():
    """Test PackagingChange can be instantiated."""
    change = PackagingChange(
        file_path="pyproject.toml",
        change_type="modified",
        additions=10,
        deletions=5,
        patch="@@ -1,3 +1,3 @@\n test patch"
    )
    assert change.file_path == "pyproject.toml"
    assert change.change_type == "modified"
    assert change.additions == 10
    assert change.deletions == 5
    assert change.patch == "@@ -1,3 +1,3 @@\n test patch"


def test_commit_summary_dataclass():
    """Test CommitSummary can be instantiated."""
    summary = CommitSummary(
        sha="abc123def456",
        title="Test commit",
        author="testuser",
        url="https://github.com/test/repo/commit/abc123def456",
        date="2024-01-01T12:00:00Z",
        packaging_changes=[]
    )
    assert summary.sha == "abc123def456"
    assert summary.title == "Test commit"
    assert summary.author == "testuser"
    assert summary.url == "https://github.com/test/repo/commit/abc123def456"
    assert summary.date == "2024-01-01T12:00:00Z"
    assert summary.packaging_changes == []
    assert summary.ai_summary is None