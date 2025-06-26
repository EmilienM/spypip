"""
Patch operations module for handling patch files and applications.
"""

import contextlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_CLONE_TIMEOUT,
    ERROR_MESSAGES,
    SUCCESS_MESSAGES,
    WARNING_MESSAGES,
)
from .exceptions import GitOperationError, PatchParsingError
from .llm_client import LLMClient
from .models import PatchFailure
from .utils import (
    calculate_hunk_location,
    extract_file_paths_from_patches,
    extract_target_files_from_patch,
    run_git_command,
)


class PatchManager:
    """Manages patch file operations and applications."""

    def __init__(self, patches_dir: str | None = None, json_output: bool = False):
        self.patches_dir = patches_dir
        self.json_output = json_output
        self.patch_file_paths: set[str] = set()

    def load_file_patterns(self, default_patterns: list[str]) -> list[str]:
        """
        Load file patterns from patch files if patches_dir is provided,
        otherwise return the default packaging patterns.

        Args:
            default_patterns: Default patterns to use if no patches directory

        Returns:
            List of file patterns
        """
        if not self.patches_dir:
            return default_patterns

        patches_path = Path(self.patches_dir)
        if not patches_path.exists():
            if not self.json_output:
                print(
                    WARNING_MESSAGES["PATCHES_DIR_NOT_FOUND"].format(
                        path=self.patches_dir
                    )
                )
            return default_patterns

        if not patches_path.is_dir():
            if not self.json_output:
                print(
                    WARNING_MESSAGES["PATCHES_DIR_NOT_FOUND"].format(
                        path=self.patches_dir
                    )
                )
            return default_patterns

        if not self.json_output:
            print(f"Loading file patterns from patches directory: {self.patches_dir}")

        try:
            file_paths = extract_file_paths_from_patches(patches_path)
        except PatchParsingError as e:
            if not self.json_output:
                print(f"Warning: {e}")
            return default_patterns

        if not file_paths:
            if not self.json_output:
                print(WARNING_MESSAGES["NO_FILE_PATHS"])
            return default_patterns

        if not self.json_output:
            print(f"Found {len(file_paths)} file paths in patches")
        # Store the exact file paths - we'll match them directly
        self.patch_file_paths = file_paths
        return []  # Return empty list since we'll use exact path matching

    def is_patched(self, file_path: str, default_patterns: list[str]) -> bool:
        """
        Check if a file path is covered by patches or patterns.

        Args:
            file_path: Path to check
            default_patterns: Default patterns to use if no patch files

        Returns:
            True if file is covered by patches/patterns
        """
        # If we have patch file paths, check for exact matches only
        if self.patch_file_paths:
            return file_path in self.patch_file_paths

        # Fall back to default pattern matching
        for pattern in default_patterns:
            if re.search(pattern, file_path, re.IGNORECASE):
                return True
        return False

    def analyze_patch_compatibility(
        self, patch_file: Path, repo_dir: Path
    ) -> dict[str, Any]:
        """
        Analyze why a patch might not be compatible with the current codebase.

        Args:
            patch_file: Path to the patch file
            repo_dir: Path to the repository directory

        Returns:
            Dictionary with analysis results
        """
        analysis: dict[str, Any] = {
            "patch_file": patch_file.name,
            "target_files": [],
            "missing_files": [],
            "potential_issues": [],
            "suggestions": [],
        }

        try:
            patch_content = Path(patch_file).read_text(
                encoding="utf-8", errors="ignore"
            )

            # Extract target files and their modifications
            lines = patch_content.split("\n")
            current_file = None

            for line in lines:
                if line.startswith("--- a/"):
                    current_file = line[6:]  # Remove '--- a/'
                    analysis["target_files"].append(current_file)

                    target_path = repo_dir / current_file
                    if not target_path.exists():
                        analysis["missing_files"].append(current_file)
                        analysis["potential_issues"].append(
                            f"File {current_file} does not exist in repository"
                        )

                elif line.startswith("diff --git"):
                    # Alternative way to extract file names
                    match = re.search(r"diff --git a/(.+) b/", line)
                    if match:
                        file_path = match.group(1)
                        if file_path not in analysis["target_files"]:
                            analysis["target_files"].append(file_path)
                            target_path = repo_dir / file_path
                            if not target_path.exists():
                                analysis["missing_files"].append(file_path)

            # Generate suggestions based on analysis
            if analysis["missing_files"]:
                analysis["suggestions"].append(
                    "Some target files are missing. The patch may be for a different version or branch."
                )
                analysis["suggestions"].append(
                    "Consider updating the patch file paths or checking if files have been moved/renamed."
                )

            if not analysis["target_files"]:
                analysis["potential_issues"].append(
                    "Could not identify target files in patch"
                )
                analysis["suggestions"].append(
                    "Patch format may be invalid or unsupported"
                )

        except Exception as e:
            analysis["potential_issues"].append(f"Error reading patch file: {e}")

        return analysis

    def fix_patch_line_numbers(
        self, patch_content: str, current_files_content: dict[str, str]
    ) -> str:
        """
        Fix the line numbers in unified diff headers by computing them based on actual content.

        Args:
            patch_content: The patch content with potentially incorrect line numbers
            current_files_content: Dictionary mapping file paths to their current content

        Returns:
            Patch content with corrected line numbers
        """
        lines = patch_content.split("\n")
        fixed_lines = []
        current_file = None

        i = 0
        while i < len(lines):
            line = lines[i]

            # Track which file we're working with
            if line.startswith("diff --git"):
                fixed_lines.append(line)
                current_file = None
                # Extract file path from diff line
                match = re.search(r"diff --git a/(.+)\s+b/", line)
                if match:
                    current_file = match.group(1)
            elif line.startswith("--- a/") or line.startswith("+++ b/"):
                fixed_lines.append(line)
            elif (
                line.startswith("@@")
                and current_file
                and current_file in current_files_content
            ):
                # This is a hunk header that needs fixing
                hunk_lines = []
                context_lines = []
                additions = []
                removals = []

                # Look ahead to collect all lines in this hunk
                j = i + 1
                while j < len(lines) and not (
                    lines[j].startswith("@@") or lines[j].startswith("diff --git")
                ):
                    hunk_line = lines[j]
                    hunk_lines.append(hunk_line)

                    if hunk_line.startswith("+"):
                        additions.append(hunk_line[1:])  # Remove the +
                    elif hunk_line.startswith("-"):
                        removals.append(hunk_line[1:])  # Remove the -
                    elif hunk_line.startswith(" "):
                        context_lines.append(hunk_line[1:])  # Remove the space
                    else:
                        # Line without prefix, treat as context
                        context_lines.append(hunk_line)
                    j += 1

                # Find the location in the original file where this hunk should apply
                file_content = current_files_content[current_file]
                file_lines = file_content.split("\n")

                # Find the best match for the context and removals in the original file
                old_start, old_count, new_start, new_count = calculate_hunk_location(
                    file_lines, hunk_lines, context_lines, removals, additions
                )

                # Create the corrected hunk header
                fixed_header = (
                    f"@@ -{old_start},{old_count} +{new_start},{new_count} @@"
                )
                fixed_lines.append(fixed_header)

                # Add all the hunk lines
                fixed_lines.extend(hunk_lines)

                # Skip the lines we already processed
                i = j - 1
            else:
                fixed_lines.append(line)

            i += 1

        return "\n".join(fixed_lines)

    async def test_regenerated_patch(
        self,
        regenerated_patch: str,
        repo_dir: Path,
        original_patch_name: str,
        show_content_always: bool = False,
    ) -> bool:
        """
        Test if the regenerated patch applies successfully and print it if it does.

        Args:
            regenerated_patch: The LLM-generated patch content
            repo_dir: Path to the cloned repository
            original_patch_name: Name of the original patch file
            show_content_always: Whether to show content even if patch doesn't apply

        Returns:
            True if patch applies successfully, False otherwise
        """
        try:
            # Ensure repository is in clean state before testing
            run_git_command(["git", "reset", "--hard", "HEAD"], cwd=repo_dir)

            # Write the regenerated patch to a temporary file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False
            ) as tmp_file:
                # Ensure patch ends with newline to avoid "malformed patch" errors
                patch_content = regenerated_patch
                if not patch_content.endswith("\n"):
                    patch_content += "\n"
                tmp_file.write(patch_content)
                tmp_patch_path = tmp_file.name

            try:
                # Test if the regenerated patch applies using patch -p1
                test_result = subprocess.run(
                    ["patch", "-p1", "--dry-run", "--fuzz=0", "-i", tmp_patch_path],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                )

                if test_result.returncode == 0:
                    if not self.json_output:
                        print(
                            SUCCESS_MESSAGES["PATCH_REGENERATED"].format(
                                name=original_patch_name
                            )
                        )
                        print("=" * 60)
                        print("REGENERATED PATCH CONTENT:")
                        print("=" * 60)
                        print(regenerated_patch)
                        print("=" * 60)
                        print(
                            f"The above patch content can be saved to replace {original_patch_name}"
                        )
                        print("=" * 60)
                    return True
                else:
                    if not self.json_output:
                        if show_content_always:
                            print(
                                f"✗ Regenerated patch for {original_patch_name} still doesn't apply, but showing content:"
                            )
                            print("=" * 60)
                            print("REGENERATED PATCH CONTENT (DOES NOT APPLY):")
                            print("=" * 60)
                            print(regenerated_patch)
                            print("=" * 60)
                            print(
                                f"The above patch content was generated but does not apply to {original_patch_name}"
                            )
                            print("=" * 60)
                        else:
                            print(
                                f"Regenerated patch for {original_patch_name} still doesn't apply"
                            )
                    return False

            finally:
                # Clean up temporary file
                with contextlib.suppress(OSError):
                    Path(tmp_patch_path).unlink()

        except Exception as e:
            if not self.json_output:
                print(f"Error testing regenerated patch: {e}")
            return False

    async def regenerate_patch_with_llm(
        self, patch_file: Path, repo_dir: Path, ref: str, llm_client: LLMClient
    ) -> str | None:
        """
        Use LLM to regenerate a patch file when the original fails to apply.

        Args:
            patch_file: Path to the original patch file that failed
            repo_dir: Path to the cloned repository
            ref: Git reference being tested
            llm_client: LLM client for regeneration

        Returns:
            The regenerated patch content if successful, None otherwise
        """
        try:
            # Read the original patch content
            original_patch = Path(patch_file).read_text(
                encoding="utf-8", errors="ignore"
            )

            # Extract target files from the patch
            target_files = extract_target_files_from_patch(original_patch)

            if not target_files:
                return None

            # Get current content of target files
            current_files_content = {}
            for file_path in target_files:
                target_path = repo_dir / file_path
                if target_path.exists():
                    try:
                        current_files_content[file_path] = target_path.read_text(
                            encoding="utf-8", errors="ignore"
                        )
                    except Exception:
                        continue

            if not current_files_content:
                return None

            # Use LLM to regenerate the patch
            regenerated_patch = llm_client.regenerate_patch(
                original_patch, current_files_content, ref
            )

            if regenerated_patch:
                # Fix the line numbers in the patch headers
                fixed_patch = self.fix_patch_line_numbers(
                    regenerated_patch, current_files_content
                )
                return fixed_patch.strip()

            return None

        except Exception as e:
            if not self.json_output:
                print(f"LLM patch regeneration failed: {e}")
            return None

    def generate_jira_content(
        self,
        failed_patches: list[PatchFailure],
        ref: str,
        repo_owner: str,
        repo_name: str,
    ) -> str:
        """
        Generate Jira ticket content from failed patches.

        Args:
            failed_patches: List of failed patch information
            ref: Git reference that was tested
            repo_owner: Repository owner
            repo_name: Repository name

        Returns:
            Formatted Jira content
        """
        content_lines = [
            f"Some patches for {repo_owner}/{repo_name} failed to apply on {ref}:",
            "",
        ]

        for patch_failure in failed_patches:
            content_lines.append(f"Applying patch: {patch_failure.patch_name}")
            content_lines.append(
                WARNING_MESSAGES["PATCH_FAILED"].format(name=patch_failure.patch_name)
            )
            content_lines.append(patch_failure.error_output)
            content_lines.append("")

        content_lines.append("You'll need to fix these patches manually.")

        return "\n".join(content_lines)

    async def check_patch_application(
        self,
        service: str,
        repo_owner_or_project: str,
        repo_name: str = "",
        ref: str = "main",
        llm_client: LLMClient | None = None,
    ) -> bool:
        """
        Check if patches can be applied to the repository at the specified ref.

        Args:
            service: 'github' or 'gitlab'
            repo_owner_or_project: Repository owner (GitHub) or project path (GitLab)
            repo_name: Repository name (GitHub) or empty (GitLab)
            ref: The git reference to check patches against
            llm_client: Optional LLM client for patch regeneration

        Returns:
            True if all patches apply successfully, False otherwise

        Raises:
            PatchApplicationError: If there are issues with patch application process
        """
        if not self.patches_dir:
            if not self.json_output:
                print(ERROR_MESSAGES["NO_PATCHES_DIR"])
            return False

        patches_path = Path(self.patches_dir)
        if not patches_path.exists() or not patches_path.is_dir():
            if not self.json_output:
                print(
                    ERROR_MESSAGES["PATCHES_DIR_NOT_EXIST"].format(
                        path=self.patches_dir
                    )
                )
            return False

        if not self.json_output:
            if service == "gitlab":
                print(
                    f"Checking patch application for {repo_owner_or_project} (GitLab) at ref '{ref}'"
                )
            else:
                print(
                    f"Checking patch application for {repo_owner_or_project}/{repo_name} at ref '{ref}'"
                )

        # Get patch files
        patch_files = []
        for patch_file in patches_path.iterdir():
            if patch_file.is_file() and patch_file.suffix.lower() in {
                ".patch",
                ".diff",
            }:
                patch_files.append(patch_file)

        if not patch_files:
            if not self.json_output:
                print(
                    "Warning: No patch files (.patch or .diff) found in patches directory"
                )
                print(
                    "Only .patch and .diff files are supported for patch application testing"
                )
            return True  # No patches to apply is considered success

        if not self.json_output:
            print(f"Found {len(patch_files)} patch files to test")

        # Create temporary directory for repository clone
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "repo"

            try:
                # Clone the repository
                if not self.json_output:
                    print("Cloning repository to temporary directory...")
                if service == "github":
                    clone_url = (
                        f"https://github.com/{repo_owner_or_project}/{repo_name}.git"
                    )
                    run_git_command(
                        [
                            "git",
                            "clone",
                            "--depth",
                            "1",
                            "--branch",
                            ref,
                            "--recurse-submodules",
                            clone_url,
                            str(repo_dir),
                        ],
                        timeout=DEFAULT_CLONE_TIMEOUT,
                    )
                elif service == "gitlab":
                    clone_url = f"https://gitlab.com/{repo_owner_or_project}.git"
                    # Setup authentication for GitLab
                    gitlab_username = os.environ.get("GITLAB_USERNAME")
                    gitlab_token = os.environ.get("GITLAB_PERSONAL_ACCESS_TOKEN")
                    if not gitlab_username or not gitlab_token:
                        raise RuntimeError(
                            "GITLAB_USERNAME and GITLAB_PERSONAL_ACCESS_TOKEN must be set in the environment for GitLab patch application."
                        )
                    # Use a credential helper for this repo only
                    # Write a .git-credentials file in the temp directory
                    credentials_path = Path(temp_dir) / ".git-credentials"
                    credentials_url = (
                        f"https://{gitlab_username}:{gitlab_token}@gitlab.com"
                    )
                    credentials_path.write_text(credentials_url + "\n")
                    # Configure git to use this credentials file
                    run_git_command(
                        [
                            "git",
                            "config",
                            "--global",
                            "credential.helper",
                            f"store --file={credentials_path}",
                        ]
                    )
                    try:
                        run_git_command(
                            [
                                "git",
                                "clone",
                                "--depth",
                                "1",
                                "--branch",
                                ref,
                                "--recurse-submodules",
                                clone_url,
                                str(repo_dir),
                            ],
                            timeout=DEFAULT_CLONE_TIMEOUT,
                        )
                    finally:
                        # Clean up credential helper config
                        run_git_command(
                            [
                                "git",
                                "config",
                                "--global",
                                "--unset",
                                "credential.helper",
                            ]
                        )
                        with contextlib.suppress(Exception):
                            credentials_path.unlink()
                else:
                    raise ValueError(f"Unsupported service: {service}")

                if not self.json_output:
                    print(SUCCESS_MESSAGES["REPO_CLONED"])

                # Test each patch
                all_patches_successful = True
                failed_patches = []

                for patch_file in patch_files:
                    if not self.json_output:
                        print(f"\nTesting patch: {patch_file.name}")

                    # Try to apply the patch with --dry-run first using patch -p1
                    patch_result = subprocess.run(
                        [
                            "patch",
                            "-p1",
                            "--dry-run",
                            "--fuzz=0",
                            "-i",
                            str(patch_file),
                        ],
                        cwd=repo_dir,
                        capture_output=True,
                        text=True,
                    )

                    if patch_result.returncode == 0:
                        if not self.json_output:
                            print(
                                SUCCESS_MESSAGES["PATCH_APPLIED"].format(
                                    name=patch_file.name
                                )
                            )
                    else:
                        # Handle patch failure
                        error_output = await self._handle_patch_failure(
                            patch_file, patch_result, repo_dir, ref, llm_client
                        )

                        if (
                            error_output
                        ):  # Only count as failure if we couldn't regenerate
                            failed_patches.append(
                                PatchFailure(
                                    patch_name=patch_file.name,
                                    error_output=error_output,
                                )
                            )
                            all_patches_successful = False

                # Handle output based on format
                if self.json_output:
                    if failed_patches:
                        # Generate JSON output for Jira tickets
                        json_output_data = {
                            "title": f"Failed to apply patches {repo_owner_or_project}{('/' + repo_name) if repo_name else ''} for '{ref}'",
                            "content": self.generate_jira_content(
                                failed_patches, ref, repo_owner_or_project, repo_name
                            ),
                        }
                        print(json.dumps(json_output_data, indent=2))
                else:
                    print(f"\n{'=' * 50}")
                    if all_patches_successful:
                        print(SUCCESS_MESSAGES["ALL_PATCHES_APPLIED"])
                    else:
                        print(WARNING_MESSAGES["SOME_PATCHES_FAILED"])

                return all_patches_successful

            except GitOperationError as e:
                if "timed out" in str(e).lower():
                    print(ERROR_MESSAGES["CLONE_TIMEOUT"])
                else:
                    print(f"Error during git operation: {e}")
                return False
            except Exception as e:
                print(f"Error during patch application check: {e}")
                return False

    async def _handle_patch_failure(
        self,
        patch_file: Path,
        patch_result: subprocess.CompletedProcess,
        repo_dir: Path,
        ref: str,
        llm_client: LLMClient | None,
    ) -> str | None:
        """Handle patch application failure with LLM regeneration attempt."""
        # Collect error information for JSON output
        error_output = []
        if patch_result.stderr:
            error_output.append(f"  Error: {patch_result.stderr.strip()}")
        if patch_result.stdout:
            error_output.append(f"  Output: {patch_result.stdout.strip()}")

        if not self.json_output:
            print(WARNING_MESSAGES["PATCH_FAILED"].format(name=patch_file.name))
            for line in error_output:
                print(line)
            print("  Attempting LLM-powered patch regeneration...")

        # Try to regenerate the patch using LLM if available
        if llm_client:
            try:
                regenerated_patch = await self.regenerate_patch_with_llm(
                    patch_file, repo_dir, ref, llm_client
                )
                if regenerated_patch:
                    # Test the regenerated patch and always show the content
                    regenerated_patch_result = await self.test_regenerated_patch(
                        regenerated_patch,
                        repo_dir,
                        patch_file.name,
                        show_content_always=True,
                    )
                    if regenerated_patch_result:
                        return None  # Success - don't count as failure
                else:
                    if not self.json_output:
                        print(f"LLM failed to regenerate patch for {patch_file.name}")
            except Exception as e:
                if not self.json_output:
                    print(f"Error during LLM regeneration: {e}")

        # Continue with diagnostic information if regeneration failed
        self._add_diagnostic_info(patch_file, repo_dir, error_output)

        return "\n".join(error_output)

    def _add_diagnostic_info(
        self, patch_file: Path, repo_dir: Path, error_output: list[str]
    ) -> None:
        """Add diagnostic information about patch failure."""
        if not self.json_output:
            print("  Continuing with diagnostic information...")

        # Try with different patch options for better diagnostics
        diagnostic_result = subprocess.run(
            [
                "patch",
                "-p1",
                "--dry-run",
                "--ignore-whitespace",
                "--fuzz=0",
                "-i",
                str(patch_file),
            ],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        if diagnostic_result.returncode == 0:
            diagnostic_info = "  Note: Patch would succeed with --ignore-whitespace"
            error_output.append(diagnostic_info)
            if not self.json_output:
                print(diagnostic_info)
        else:
            # Try to show what files the patch is trying to modify
            try:
                patch_content = Path(patch_file).read_text()

                # Extract file paths from patch
                file_paths = set()
                for line in patch_content.split("\n"):
                    if line.startswith("--- a/") or line.startswith("+++ b/"):
                        path = line.split("/", 1)[1] if "/" in line else line
                        file_paths.add(path)

                if file_paths:
                    file_info = (
                        f"  Patch targets these files: {', '.join(sorted(file_paths))}"
                    )
                    error_output.append(file_info)
                    if not self.json_output:
                        print(file_info)

                    # Check if these files exist
                    for file_path in file_paths:
                        target_file = repo_dir / file_path
                        if target_file.exists():
                            status_info = f"    ✓ {file_path} exists"
                            error_output.append(status_info)
                            if not self.json_output:
                                print(status_info)
                        else:
                            status_info = f"    ✗ {file_path} does not exist"
                            error_output.append(status_info)
                            if not self.json_output:
                                print(status_info)

            except Exception as e:
                error_info = f"  Could not analyze patch content: {e}"
                error_output.append(error_info)
                if not self.json_output:
                    print(error_info)

        # Perform detailed analysis of why the patch failed
        analysis = self.analyze_patch_compatibility(patch_file, repo_dir)

        if analysis["potential_issues"]:
            if not self.json_output:
                print("  Potential issues:")
            for issue in analysis["potential_issues"]:
                issue_info = f"    - {issue}"
                error_output.append(issue_info)
                if not self.json_output:
                    print(issue_info)

        if analysis["suggestions"]:
            if not self.json_output:
                print("  Suggestions:")
            for suggestion in analysis["suggestions"]:
                suggestion_info = f"    - {suggestion}"
                error_output.append(suggestion_info)
                if not self.json_output:
                    print(suggestion_info)
