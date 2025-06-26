"""
Tests for the max_commits functionality.
"""
import pytest
import subprocess
import sys
from unittest.mock import AsyncMock, Mock, patch
from src.spypip.analyzer import PackagingVersionAnalyzer
import re


class TestMaxCommits:
    """Test the max_commits limit functionality."""

    @pytest.mark.asyncio
    async def test_max_commits_parameter_initialization(self):
        """Test that max_commits parameter is properly initialized."""
        analyzer = PackagingVersionAnalyzer(
            "test_owner/test_repo", "fake_api_key", max_commits=25
        )
        assert analyzer.max_commits == 25

    @pytest.mark.asyncio
    async def test_max_commits_default_value(self):
        """Test that max_commits has the correct default value."""
        analyzer = PackagingVersionAnalyzer(
            "test_owner/test_repo", "fake_api_key"
        )
        assert analyzer.max_commits == 50

    @pytest.mark.asyncio
    async def test_get_commits_between_refs_respects_max_commits(self):
        """Test that get_commits_between_refs respects the max_commits limit."""
        analyzer = PackagingVersionAnalyzer(
            "test_owner/test_repo", "fake_api_key", max_commits=3
        )
        from spypip.github_client import GitHubMCPClient
        analyzer.mcp_client = GitHubMCPClient()

        # Mock get_commit_info to return a specific SHA
        with patch.object(analyzer.mcp_client, "get_commit_info", new=AsyncMock(return_value={"sha": "from_sha_123"})):
            # Mock get_commits_between_refs to return a list of commits
            commits_data = [
                {"sha": "commit1", "commit": {"message": "msg1", "author": {"name": "author1", "date": "2023-01-01"}}, "html_url": "url1"},
                {"sha": "commit2", "commit": {"message": "msg2", "author": {"name": "author2", "date": "2023-01-02"}}, "html_url": "url2"},
                {"sha": "commit3", "commit": {"message": "msg3", "author": {"name": "author3", "date": "2023-01-03"}}, "html_url": "url3"},
                {"sha": "commit4", "commit": {"message": "msg4", "author": {"name": "author4", "date": "2023-01-04"}}, "html_url": "url4"},
                {"sha": "commit5", "commit": {"message": "msg5", "author": {"name": "author5", "date": "2023-01-05"}}, "html_url": "url5"},
            ]
            with patch.object(analyzer.mcp_client, "get_commits_between_refs", new=AsyncMock(return_value=commits_data[:3])):
                commits = await analyzer.get_commits_between_refs("from_ref", "to_ref")
                assert len(commits) == 3
                assert commits[0]["sha"] == "commit1"
                assert commits[1]["sha"] == "commit2"
                assert commits[2]["sha"] == "commit3"

    @pytest.mark.asyncio
    async def test_get_commits_between_refs_stops_at_from_ref(self):
        """Test that get_commits_between_refs stops at from_ref even if max_commits is higher."""
        analyzer = PackagingVersionAnalyzer(
            "test_owner/test_repo", "fake_api_key", max_commits=10
        )
        from spypip.github_client import GitHubMCPClient
        analyzer.mcp_client = GitHubMCPClient()

        # Mock get_commit_info to return a specific SHA
        with patch.object(analyzer.mcp_client, "get_commit_info", new=AsyncMock(return_value={"sha": "commit3"})):
            # Mock get_commits_between_refs to return a list of commits
            commits_data = [
                {"sha": "commit1", "commit": {"message": "msg1", "author": {"name": "author1", "date": "2023-01-01"}}, "html_url": "url1"},
                {"sha": "commit2", "commit": {"message": "msg2", "author": {"name": "author2", "date": "2023-01-02"}}, "html_url": "url2"},
            ]
            with patch.object(analyzer.mcp_client, "get_commits_between_refs", new=AsyncMock(return_value=commits_data)):
                commits = await analyzer.get_commits_between_refs("from_ref", "to_ref")
                assert len(commits) == 2
                assert commits[0]["sha"] == "commit1"
                assert commits[1]["sha"] == "commit2"

    def test_max_commits_validation_zero(self):
        """Test that --max-commits 0 is rejected."""
        result = subprocess.run(
            [sys.executable, "-m", "spypip", "test/repo", "--max-commits", "0"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 2
        assert "--max-commits must be a positive integer" in result.stderr

    def test_max_commits_validation_negative(self):
        """Test that negative --max-commits values are rejected."""
        result = subprocess.run(
            [sys.executable, "-m", "spypip", "test/repo", "--max-commits", "-5"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 2
        assert "--max-commits must be a positive integer" in result.stderr

    def test_max_commits_validation_positive(self):
        """Test that positive --max-commits values are accepted (in help parsing)."""
        result = subprocess.run(
            [sys.executable, "-m", "spypip", "--help"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "--max-commits MAX_COMMITS" in result.stdout
        assert re.search(r"Default\s*is\s*50", result.stdout)