"""
Tests for tag logic functionality
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from spypip.analyzer import PackagingVersionAnalyzer


@pytest.mark.asyncio
class TestTagLogic:
    """Test the tag selection logic for from_tag when not provided."""

    @pytest.fixture
    def analyzer(self):
        """Create a test analyzer instance."""
        return PackagingVersionAnalyzer("test/repo", "fake_key")

    async def test_get_previous_tag_basic(self, analyzer):
        """Test getting the previous tag in a simple case."""
        # Initialize and mock the GitHub client
        from spypip.github_client import GitHubMCPClient
        analyzer.github_client = GitHubMCPClient()
        # Mock the MCP session
        analyzer.github_client.mcp_session = AsyncMock()
        
        # Mock response with tags in chronological order (newest first)
        mock_content = MagicMock()
        mock_content.text = '[\
            {"name": "v4.0.0"},\
            {"name": "v3.0.0"},\
            {"name": "v2.0.0"},\
            {"name": "v1.0.0"}\
        ]'
        
        mock_result = MagicMock()
        mock_result.content = [mock_content]
        
        analyzer.github_client.mcp_session.call_tool.return_value = mock_result
        
        # Test getting previous tag for v3.0.0 should return v2.0.0
        result = await analyzer.get_previous_tag("v3.0.0")
        assert result == "v2.0.0"

    async def test_get_previous_tag_first_tag(self, analyzer):
        """Test getting previous tag when target is the oldest tag."""
        # Initialize and mock the GitHub client
        from spypip.github_client import GitHubMCPClient
        analyzer.github_client = GitHubMCPClient()
        # Mock the MCP session
        analyzer.github_client.mcp_session = AsyncMock()
        
        # Mock response with tags
        mock_content = MagicMock()
        mock_content.text = '[\
            {"name": "v3.0.0"},\
            {"name": "v2.0.0"},\
            {"name": "v1.0.0"}\
        ]'
        
        mock_result = MagicMock()
        mock_result.content = [mock_content]
        
        analyzer.github_client.mcp_session.call_tool.return_value = mock_result
        
        # Test getting previous tag for v1.0.0 should return None (no previous tag)
        result = await analyzer.get_previous_tag("v1.0.0")
        assert result is None

    async def test_get_previous_tag_not_found(self, analyzer):
        """Test getting previous tag when target tag is not found."""
        # Initialize and mock the GitHub client
        from spypip.github_client import GitHubMCPClient
        analyzer.github_client = GitHubMCPClient()
        # Mock the MCP session
        analyzer.github_client.mcp_session = AsyncMock()
        
        # Mock response with tags that don't include the target
        mock_content = MagicMock()
        mock_content.text = '[\
            {"name": "v3.0.0"},\
            {"name": "v2.0.0"},\
            {"name": "v1.0.0"}\
        ]'
        
        mock_result = MagicMock()
        mock_result.content = [mock_content]
        
        analyzer.github_client.mcp_session.call_tool.return_value = mock_result
        
        # Test getting previous tag for a tag that doesn't exist
        result = await analyzer.get_previous_tag("v5.0.0")
        assert result is None

    async def test_analyze_repository_uses_previous_tag(self, analyzer):
        """Test that analyze_repository uses get_previous_tag when from_tag is None and to_tag is not 'main'."""
        # Initialize and mock the GitHub client
        from spypip.github_client import GitHubMCPClient
        analyzer.github_client = GitHubMCPClient()
        analyzer.github_client.mcp_session = AsyncMock()
        analyzer.get_previous_tag = AsyncMock(return_value="v2.0.0")
        analyzer.get_commits_between_refs = AsyncMock(return_value=[])
        analyzer.analyze_commit_for_packaging_changes = AsyncMock(return_value=None)
        
        # Test with to_tag specified but from_tag not provided
        result = await analyzer.analyze_repository(from_tag=None, to_tag="v3.0.0")
        
        # Verify get_previous_tag was called with the correct to_tag
        analyzer.get_previous_tag.assert_called_once_with("v3.0.0")
        
        # Verify get_commits_between_refs was called with the previous tag
        analyzer.get_commits_between_refs.assert_called_once_with("v2.0.0", "v3.0.0")

    async def test_analyze_repository_fallback_to_latest_when_no_previous(self, analyzer):
        """Test fallback to latest tag when no previous tag is found."""
        # Initialize and mock the GitHub client
        from spypip.github_client import GitHubMCPClient
        analyzer.github_client = GitHubMCPClient()
        analyzer.github_client.mcp_session = AsyncMock()
        analyzer.get_previous_tag = AsyncMock(return_value=None)  # No previous tag found
        analyzer.get_latest_tag = AsyncMock(return_value="v4.0.0")
        analyzer.get_commits_between_refs = AsyncMock(return_value=[])
        analyzer.analyze_commit_for_packaging_changes = AsyncMock(return_value=None)
        
        # Test with to_tag specified but from_tag not provided
        result = await analyzer.analyze_repository(from_tag=None, to_tag="v3.0.0")
        
        # Verify both methods were called
        analyzer.get_previous_tag.assert_called_once_with("v3.0.0")
        analyzer.get_latest_tag.assert_called_once()
        
        # Verify get_commits_between_refs was called with the latest tag as fallback
        analyzer.get_commits_between_refs.assert_called_once_with("v4.0.0", "v3.0.0")

    async def test_analyze_repository_main_branch_uses_latest(self, analyzer):
        """Test that analyze_repository still uses latest tag when to_tag is 'main'."""
        # Initialize and mock the GitHub client
        from spypip.github_client import GitHubMCPClient
        analyzer.github_client = GitHubMCPClient()
        analyzer.github_client.mcp_session = AsyncMock()
        analyzer.get_latest_tag = AsyncMock(return_value="v3.0.0")
        analyzer.get_commits_between_refs = AsyncMock(return_value=[])
        analyzer.analyze_commit_for_packaging_changes = AsyncMock(return_value=None)
        
        # Test with to_tag as 'main' and from_tag not provided
        result = await analyzer.analyze_repository(from_tag=None, to_tag="main")
        
        # Verify get_latest_tag was called (and get_previous_tag was NOT called)
        analyzer.get_latest_tag.assert_called_once()
        
        # Verify get_commits_between_refs was called with the latest tag
        analyzer.get_commits_between_refs.assert_called_once_with("v3.0.0", "main")