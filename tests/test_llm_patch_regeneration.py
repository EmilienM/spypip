"""Tests for LLM-powered patch regeneration functionality."""

import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from spypip.analyzer import PackagingVersionAnalyzer


class TestLLMPatchRegeneration:
    """Test LLM-powered patch regeneration functionality."""

    @pytest.mark.asyncio
    async def test_regenerate_patch_with_llm_basic(self):
        """Test basic LLM patch regeneration functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "repo"
            repo_dir.mkdir()
            
            # Create a target file that the patch will modify
            target_file = repo_dir / "requirements.txt"
            target_file.write_text("flask==2.0.0\nrequests==2.28.0\npytest==7.1.0\n")
            
            # Create a patch file that won't apply (wrong line numbers)
            patch_content = """diff --git a/requirements.txt b/requirements.txt
index 1234567..abcdefg 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -10,3 +10,4 @@
 flask==2.0.0
 requests==2.28.0
+numpy==1.21.0
 pytest==7.1.0
"""
            
            patch_file = Path(temp_dir) / "test.patch"
            patch_file.write_text(patch_content)
            
            # Mock the OpenAI client
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = """diff --git a/requirements.txt b/requirements.txt
index 1234567..abcdefg 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,3 +1,4 @@
 flask==2.0.0
 requests==2.28.0
+numpy==1.21.0
 pytest==7.1.0
"""
            
            analyzer = PackagingVersionAnalyzer("owner/repo", "fake-key")
            analyzer.llm_client.client = MagicMock()
            analyzer.llm_client.client.chat.completions.create.return_value = mock_response
            
            # Test the regeneration
            result = await analyzer.patch_manager.regenerate_patch_with_llm(patch_file, repo_dir, "main", analyzer.llm_client)
            
            assert result is not None
            assert "diff --git a/requirements.txt b/requirements.txt" in result
            assert "+numpy==1.21.0" in result

    @pytest.mark.asyncio
    async def test_regenerate_patch_with_missing_file(self):
        """Test patch regeneration when target file doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "repo"
            repo_dir.mkdir()
            
            # Create a patch file for a non-existent file
            patch_content = """diff --git a/nonexistent.txt b/nonexistent.txt
index 1234567..abcdefg 100644
--- a/nonexistent.txt
+++ b/nonexistent.txt
@@ -1,3 +1,4 @@
 line1
 line2
+line3
 line4
"""
            
            patch_file = Path(temp_dir) / "test.patch"
            patch_file.write_text(patch_content)
            
            analyzer = PackagingVersionAnalyzer("owner/repo", "fake-key")
            
            # Test the regeneration - should return None for missing files
            result = await analyzer.patch_manager.regenerate_patch_with_llm(patch_file, repo_dir, "main", analyzer.llm_client)
            
            assert result is None

    @pytest.mark.asyncio
    async def test_test_regenerated_patch_success(self):
        """Test successful application of regenerated patch."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "repo"
            repo_dir.mkdir()
            
            # Initialize git repo
            import subprocess
            subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, capture_output=True)
            
            # Create a target file
            target_file = repo_dir / "requirements.txt"
            target_file.write_text("flask==2.0.0\nrequests==2.28.0\npytest==7.1.0\n")
            
            # Add and commit the file
            subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, capture_output=True)
            
            # Create a valid patch
            regenerated_patch = """diff --git a/requirements.txt b/requirements.txt
index 1234567..abcdefg 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,3 +1,4 @@
 flask==2.0.0
 requests==2.28.0
+numpy==1.21.0
 pytest==7.1.0
"""
            
            analyzer = PackagingVersionAnalyzer("owner/repo", "fake-key")
            
            # Test the regenerated patch
            result = await analyzer.patch_manager.test_regenerated_patch(
                regenerated_patch, repo_dir, "test.patch"
            )
            
            assert result is True

    @pytest.mark.asyncio
    async def test_test_regenerated_patch_failure(self):
        """Test failure when regenerated patch still doesn't apply."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "repo"
            repo_dir.mkdir()
            
            # Initialize git repo
            import subprocess
            subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
            
            # Create a target file
            target_file = repo_dir / "requirements.txt"
            target_file.write_text("flask==2.0.0\nrequests==2.28.0\npytest==7.1.0\n")
            
            # Create an invalid patch (references non-existent content)
            regenerated_patch = """diff --git a/requirements.txt b/requirements.txt
index 1234567..abcdefg 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,3 +1,4 @@
 django==3.0.0
 fastapi==0.68.0
+numpy==1.21.0
 gunicorn==20.1.0
"""
            
            analyzer = PackagingVersionAnalyzer("owner/repo", "fake-key")
            
            # Test the regenerated patch - should fail
            result = await analyzer.patch_manager.test_regenerated_patch(
                regenerated_patch, repo_dir, "test.patch"
            )
            
            assert result is False