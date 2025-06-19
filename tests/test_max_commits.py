"""
Tests for the max_commits functionality.
"""
import pytest
import subprocess
import sys
from unittest.mock import AsyncMock, Mock, patch
from src.spypip.analyzer import PackagingVersionAnalyzer


class TestMaxCommits:
    """Test the max_commits limit functionality."""

    @pytest.mark.asyncio
    async def test_max_commits_parameter_initialization(self):
        """Test that max_commits parameter is properly initialized."""
        analyzer = PackagingVersionAnalyzer(
            "test_owner", "test_repo", "fake_api_key", max_commits=25
        )
        assert analyzer.max_commits == 25

    @pytest.mark.asyncio
    async def test_max_commits_default_value(self):
        """Test that max_commits has the correct default value."""
        analyzer = PackagingVersionAnalyzer(
            "test_owner", "test_repo", "fake_api_key"
        )
        assert analyzer.max_commits == 50

    @pytest.mark.asyncio
    async def test_get_commits_between_refs_respects_max_commits(self):
        """Test that get_commits_between_refs respects the max_commits limit."""
        analyzer = PackagingVersionAnalyzer(
            "test_owner", "test_repo", "fake_api_key", max_commits=3
        )
        
        # Mock the MCP session
        mock_session = AsyncMock()
        analyzer.mcp_session = mock_session
        
        # Mock the commit info response (for from_ref)
        mock_commit_response = Mock()
        mock_commit_response.content = [Mock()]
        mock_commit_response.content[0].text = '{"sha": "from_sha_123"}'
        
        # Mock the list commits response with more commits than max_commits
        mock_commits_response = Mock()
        mock_commits_response.content = [Mock()]
        mock_commits_response.content[0].text = '''[
            {"sha": "commit1", "commit": {"message": "msg1", "author": {"name": "author1", "date": "2023-01-01"}}, "html_url": "url1"},
            {"sha": "commit2", "commit": {"message": "msg2", "author": {"name": "author2", "date": "2023-01-02"}}, "html_url": "url2"},
            {"sha": "commit3", "commit": {"message": "msg3", "author": {"name": "author3", "date": "2023-01-03"}}, "html_url": "url3"},
            {"sha": "commit4", "commit": {"message": "msg4", "author": {"name": "author4", "date": "2023-01-04"}}, "html_url": "url4"},
            {"sha": "commit5", "commit": {"message": "msg5", "author": {"name": "author5", "date": "2023-01-05"}}, "html_url": "url5"}
        ]'''
        
        # Set up the call_tool mock to return appropriate responses
        def mock_call_tool(tool_name, params):
            if tool_name == "get_commit":
                return mock_commit_response
            elif tool_name == "list_commits":
                return mock_commits_response
            return Mock()
        
        mock_session.call_tool.side_effect = mock_call_tool
        
        # Call the method
        commits = await analyzer.get_commits_between_refs("from_ref", "to_ref")
        
        # Verify that only max_commits (3) commits are returned, not all 5
        assert len(commits) == 3
        assert commits[0]["sha"] == "commit1"
        assert commits[1]["sha"] == "commit2"
        assert commits[2]["sha"] == "commit3"

    @pytest.mark.asyncio
    async def test_get_commits_between_refs_stops_at_from_ref(self):
        """Test that get_commits_between_refs stops at from_ref even if max_commits is higher."""
        analyzer = PackagingVersionAnalyzer(
            "test_owner", "test_repo", "fake_api_key", max_commits=10
        )
        
        # Mock the MCP session
        mock_session = AsyncMock()
        analyzer.mcp_session = mock_session
        
        # Mock the commit info response (for from_ref)
        mock_commit_response = Mock()
        mock_commit_response.content = [Mock()]
        mock_commit_response.content[0].text = '{"sha": "commit3"}'  # from_ref is commit3
        
        # Mock the list commits response
        mock_commits_response = Mock()
        mock_commits_response.content = [Mock()]
        mock_commits_response.content[0].text = '''[
            {"sha": "commit1", "commit": {"message": "msg1", "author": {"name": "author1", "date": "2023-01-01"}}, "html_url": "url1"},
            {"sha": "commit2", "commit": {"message": "msg2", "author": {"name": "author2", "date": "2023-01-02"}}, "html_url": "url2"},
            {"sha": "commit3", "commit": {"message": "msg3", "author": {"name": "author3", "date": "2023-01-03"}}, "html_url": "url3"},
            {"sha": "commit4", "commit": {"message": "msg4", "author": {"name": "author4", "date": "2023-01-04"}}, "html_url": "url4"}
        ]'''
        
        # Set up the call_tool mock to return appropriate responses
        def mock_call_tool(tool_name, params):
            if tool_name == "get_commit":
                return mock_commit_response
            elif tool_name == "list_commits":
                return mock_commits_response
            return Mock()
        
        mock_session.call_tool.side_effect = mock_call_tool
        
        # Call the method
        commits = await analyzer.get_commits_between_refs("from_ref", "to_ref")
        
        # Should stop at commit3 (from_ref), so only commits 1 and 2 should be returned
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
        assert "Default is 50" in result.stdout