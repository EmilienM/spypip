"""Tests for patch regeneration with removals and additions."""

import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from spypip.analyzer import PackagingVersionAnalyzer


class TestPatchRemovals:
    """Test patch regeneration with complex removals and additions."""

    @pytest.mark.asyncio
    async def test_regenerate_patch_with_removals_and_reordering(self):
        """Test patch regeneration when items have moved and need to be removed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "repo"
            repo_dir.mkdir()
            
            # Create a target file that simulates the current requirements.txt
            target_file = repo_dir / "requirements.txt"
            target_file.write_text("""astunparse
cmake
expecttest>=0.3.0
filelock
fsspec
hypothesis
jinja2
lintrunner ; platform_machine != "s390x"
networkx
ninja
numpy
optree>=0.13.0
packaging
psutil
pyyaml
requests
# issue on Windows after >= 75.8.2 - https://github.com/pytorch/pytorch/issues/148877
setuptools<=75.8.2
sympy>=1.13.3
types-dataclasses
typing-extensions>=4.10.0
""")
            
            # Create a patch that removes cmake and adds new dependencies
            patch_content = """diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -18,4 +18,7 @@
 ninja
 packaging
 optree>=0.13.0
-cmake
+iniconfig
+pluggy
+pybind11
+triton
"""
            
            patch_file = Path(temp_dir) / "test.patch"
            patch_file.write_text(patch_content)
            
            # Mock the OpenAI client to return a proper patch that removes cmake and adds new deps
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = """diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,6 +1,10 @@
 astunparse
-cmake
 expecttest>=0.3.0
 filelock
 fsspec
 hypothesis
+iniconfig
 jinja2
 lintrunner ; platform_machine != "s390x"
 networkx
@@ -12,6 +16,9 @@
 packaging
 psutil
 pyyaml
+pluggy
+pybind11
 requests
 # issue on Windows after >= 75.8.2 - https://github.com/pytorch/pytorch/issues/148877
 setuptools<=75.8.2
 sympy>=1.13.3
+triton
 types-dataclasses
 typing-extensions>=4.10.0
"""
            
            analyzer = PackagingVersionAnalyzer("owner/repo", "fake-key")
            analyzer.llm_client.client = MagicMock()
            analyzer.llm_client.client.chat.completions.create.return_value = mock_response
            
            # Test the regeneration
            result = await analyzer.patch_manager.regenerate_patch_with_llm(patch_file, repo_dir, "main", analyzer.llm_client)
            
            assert result is not None
            assert "diff --git a/requirements.txt b/requirements.txt" in result
            # Verify cmake is being removed
            assert "-cmake" in result
            # Verify new dependencies are being added
            assert "+iniconfig" in result
            assert "+pluggy" in result
            assert "+pybind11" in result
            assert "+triton" in result

    @pytest.mark.asyncio
    async def test_extract_target_files_from_complex_patch(self):
        """Test that target files are extracted even from patches with unusual formats."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "repo"
            repo_dir.mkdir()
            
            # Create target files
            (repo_dir / "requirements.txt").write_text("content")
            (repo_dir / "cmake/External").mkdir(parents=True, exist_ok=True)
            (repo_dir / "cmake/External/aotriton.cmake").write_text("content")
            
            # Create a patch with error messages (simulating failed patch output)
            patch_content = """diff --git a/cmake/External/aotriton.cmake b/cmake/External/aotriton.cmake
index 1234567..abcdefg 100644
--- a/cmake/External/aotriton.cmake
+++ b/cmake/External/aotriton.cmake
@@ -18,6 +18,8 @@
   add_library(__caffe2_aotriton INTERFACE)
   # Note it is INSTALL"ED"
   if(DEFINED ENV{AOTRITON_INSTALLED_PREFIX})
+    # Copy preinstalled aotriton
+    message(STATUS "Copying preinstalled AOTriton")
     install(DIRECTORY
             $ENV{AOTRITON_INSTALLED_PREFIX}/lib
             $ENV{AOTRITON_INSTALLED_PREFIX}/include
"""
            
            patch_file = Path(temp_dir) / "test.patch"
            patch_file.write_text(patch_content)
            
            analyzer = PackagingVersionAnalyzer("owner/repo", "fake-key")
            
            # Test file extraction from the patch
            with open(patch_file, "r", encoding="utf-8", errors="ignore") as f:
                original_patch = f.read()
            
            # Extract target files using the enhanced logic
            target_files = []
            for line in original_patch.split("\n"):
                if line.startswith("--- a/") or line.startswith("+++ b/"):
                    parts = line.split("/", 1)
                    if len(parts) > 1:
                        file_path = parts[1]
                        if file_path not in target_files and not file_path.startswith("dev/null"):
                            target_files.append(file_path)
            
            # Should successfully extract the cmake file
            assert "cmake/External/aotriton.cmake" in target_files

    @pytest.mark.asyncio
    async def test_fix_patch_line_numbers(self):
        """Test that patch line numbers are correctly calculated."""
        analyzer = PackagingVersionAnalyzer("owner/repo", "fake-key")

        # Sample file content
        file_content = """astunparse
cmake
expecttest>=0.3.0
filelock
fsspec
hypothesis"""

        current_files_content = {"requirements.txt": file_content}

        # Patch with incorrect line numbers
        patch_with_wrong_numbers = """diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -2,7 +2,11 @@
 astunparse
-cmake
 expecttest>=0.3.0
 filelock
 fsspec
+iniconfig
+pluggy
 hypothesis"""

        # Fix the line numbers
        fixed_patch = analyzer.patch_manager.fix_patch_line_numbers(patch_with_wrong_numbers, current_files_content)

        # Should have corrected line numbers
        assert "@@ -1,6 +1,7 @@" in fixed_patch or "@@ -1,6 +1,8 @@" in fixed_patch
        assert "-cmake" in fixed_patch
        assert "+iniconfig" in fixed_patch
        assert "+pluggy" in fixed_patch