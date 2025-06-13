"""Tests for patch files functionality."""

import tempfile
import pytest
from pathlib import Path

from spypip.analyzer import PackagingPRAnalyzer


class TestPatchFileHandling:
    """Test patch file handling functionality."""

    def test_default_patterns_when_no_patches_dir(self):
        """Test that default patterns are used when no patches directory is provided."""
        analyzer = PackagingPRAnalyzer("owner", "repo", "fake-key")

        # Should use default patterns
        assert analyzer.file_patterns == analyzer.PACKAGING_PATTERNS
        assert analyzer.patches_dir is None
        assert len(analyzer.patch_file_paths) == 0

        # Test some default pattern matching
        assert analyzer.is_patched("requirements.txt")
        assert analyzer.is_patched("pyproject.toml")
        assert analyzer.is_patched("setup.py")
        assert not analyzer.is_patched("main.py")

    def test_nonexistent_patches_dir_falls_back_to_defaults(self):
        """Test that nonexistent patches directory falls back to default patterns."""
        analyzer = PackagingPRAnalyzer("owner", "repo", "fake-key", patches_dir="/nonexistent/path")

        # Should fall back to default patterns
        assert analyzer.file_patterns == analyzer.PACKAGING_PATTERNS
        assert analyzer.patches_dir == "/nonexistent/path"
        assert len(analyzer.patch_file_paths) == 0

    def test_git_patch_file_parsing(self):
        """Test parsing file paths from git patch files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            patches_dir = Path(temp_dir)

            # Create a sample git patch file
            patch_content = """diff --git a/custom-requirements.txt b/custom-requirements.txt
index 1234567..abcdefg 100644
--- a/custom-requirements.txt
+++ b/custom-requirements.txt
@@ -1,3 +1,4 @@
 flask==2.0.0
 requests==2.28.0
+numpy==1.21.0
 pytest==7.1.0
diff --git a/docker/Dockerfile.prod b/docker/Dockerfile.prod
index 2345678..bcdefgh 100644
--- a/docker/Dockerfile.prod
+++ b/docker/Dockerfile.prod
@@ -1,2 +1,3 @@
 FROM python:3.9
+RUN pip install --upgrade pip
 COPY . /app
"""

            patch_file = patches_dir / "changes.patch"
            patch_file.write_text(patch_content)

            analyzer = PackagingPRAnalyzer("owner", "repo", "fake-key", patches_dir=str(patches_dir))

            # Should detect the exact custom files from patches
            assert analyzer.is_patched("custom-requirements.txt")
            assert analyzer.is_patched("docker/Dockerfile.prod")

            # Should not match unrelated files
            assert not analyzer.is_patched("main.py")
            assert not analyzer.is_patched("other-file.txt")
            assert not analyzer.is_patched("Dockerfile.prod")  # Not exact match

    def test_plain_text_patch_file_parsing(self):
        """Test parsing file paths from plain text files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            patches_dir = Path(temp_dir)

            # Create a sample text file with file paths
            file_list_content = """# Custom packaging files to monitor
project-requirements.txt
build/setup.cfg
containers/Dockerfile.custom
environment-dev.yml
# This is a comment and should be ignored
build-constraints.txt
"""

            file_list = patches_dir / "file_list.txt"
            file_list.write_text(file_list_content)

            analyzer = PackagingPRAnalyzer("owner", "repo", "fake-key", patches_dir=str(patches_dir))

            # Should detect the exact custom files from text file
            assert analyzer.is_patched("project-requirements.txt")
            assert analyzer.is_patched("build/setup.cfg")
            assert analyzer.is_patched("containers/Dockerfile.custom")
            assert analyzer.is_patched("environment-dev.yml")
            assert analyzer.is_patched("build-constraints.txt")

            # Should not match unrelated files
            assert not analyzer.is_patched("main.py")

    def test_multiple_patch_files(self):
        """Test parsing from multiple patch files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            patches_dir = Path(temp_dir)

            # Create multiple patch files
            patch1_content = """--- a/requirements-dev.txt
+++ b/requirements-dev.txt
@@ -1,2 +1,3 @@
 pytest==7.1.0
+coverage==6.0.0
 flake8==4.0.0
"""

            patch2_content = """diff --git a/ci/environment.yml b/ci/environment.yml
index 1234567..abcdefg 100644
--- a/ci/environment.yml
+++ b/ci/environment.yml
@@ -1,3 +1,4 @@
 name: myproject
 dependencies:
   - python=3.9
+  - pip
"""

            file_list_content = """build/pyproject.toml
deployment/Dockerfile
"""

            (patches_dir / "patch1.patch").write_text(patch1_content)
            (patches_dir / "patch2.diff").write_text(patch2_content)
            (patches_dir / "files.txt").write_text(file_list_content)

            analyzer = PackagingPRAnalyzer("owner", "repo", "fake-key", patches_dir=str(patches_dir))

            # Should detect exact files from all patch sources
            assert analyzer.is_patched("requirements-dev.txt")
            assert analyzer.is_patched("ci/environment.yml")
            assert analyzer.is_patched("build/pyproject.toml")
            assert analyzer.is_patched("deployment/Dockerfile")

            # Should not match unrelated files
            assert not analyzer.is_patched("main.py")

    def test_empty_patches_dir_falls_back_to_defaults(self):
        """Test that empty patches directory falls back to default patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            patches_dir = Path(temp_dir)

            analyzer = PackagingPRAnalyzer("owner", "repo", "fake-key", patches_dir=str(patches_dir))

            # Should fall back to default patterns
            assert analyzer.file_patterns == analyzer.PACKAGING_PATTERNS
            assert len(analyzer.patch_file_paths) == 0

            # Test default pattern matching still works
            assert analyzer.is_patched("requirements.txt")
            assert analyzer.is_patched("pyproject.toml")
            assert not analyzer.is_patched("main.py")

    def test_file_as_patches_dir_falls_back_to_defaults(self):
        """Test that providing a file instead of directory falls back to default patterns."""
        with tempfile.TemporaryDirectory() as temp_dir:
            patches_dir = Path(temp_dir)
            not_a_dir = patches_dir / "not_a_directory.txt"
            not_a_dir.write_text("This is a file, not a directory")

            analyzer = PackagingPRAnalyzer("owner", "repo", "fake-key", patches_dir=str(not_a_dir))

            # Should fall back to default patterns
            assert analyzer.file_patterns == analyzer.PACKAGING_PATTERNS
            assert len(analyzer.patch_file_paths) == 0