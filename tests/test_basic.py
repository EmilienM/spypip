"""Basic tests for spypip package."""

import pytest
from spypip import __version__, PackagingPRAnalyzer, PackagingChange, PRSummary


def test_version():
    """Test that version is defined."""
    assert __version__ == "0.1.0"


def test_imports():
    """Test that main classes can be imported."""
    assert PackagingPRAnalyzer is not None
    assert PackagingChange is not None
    assert PRSummary is not None


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


def test_pr_summary_dataclass():
    """Test PRSummary can be instantiated."""
    summary = PRSummary(
        number=123,
        title="Test PR",
        author="testuser",
        url="https://github.com/test/repo/pull/123",
        packaging_changes=[]
    )
    assert summary.number == 123
    assert summary.title == "Test PR"
    assert summary.author == "testuser"
    assert summary.url == "https://github.com/test/repo/pull/123"
    assert summary.packaging_changes == []
    assert summary.ai_summary is None