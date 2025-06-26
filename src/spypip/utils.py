"""
Utility functions for SpyPip.
"""

import re
import subprocess
from pathlib import Path

from .constants import PATCH_EXTENSIONS, SUPPORTED_FILE_EXTENSIONS
from .exceptions import GitOperationError, PatchParsingError


def extract_file_paths_from_patches(patches_path: Path) -> set[str]:
    """
    Extract file paths from patch files in the given directory.

    Args:
        patches_path: Path to directory containing patch files

    Returns:
        Set of file paths found in patches

    Raises:
        PatchParsingError: If patch files cannot be parsed
    """
    file_paths = set()

    for patch_file in patches_path.iterdir():
        if not patch_file.is_file():
            continue

        if patch_file.suffix.lower() not in PATCH_EXTENSIONS:
            continue

        try:
            content = patch_file.read_text(encoding="utf-8", errors="ignore")

            # Extract file paths from different patch formats
            if patch_file.suffix.lower() in {".patch", ".diff"}:
                # Git patch format: look for "--- a/file" and "+++ b/file" lines
                git_paths = re.findall(r"^[+-]{3}\s+[ab]/(.+)$", content, re.MULTILINE)
                file_paths.update(git_paths)

                # Also look for "diff --git a/file b/file" lines
                git_diff_paths = re.findall(
                    r"^diff --git a/(.+)\s+b/", content, re.MULTILINE
                )
                file_paths.update(git_diff_paths)

            else:
                # Plain text format: each line is a file path
                lines = content.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith(
                        "#"
                    ):  # Skip empty lines and comments
                        file_paths.add(line)

        except Exception as e:
            raise PatchParsingError(
                f"Could not read patch file '{patch_file}': {e}"
            ) from e

    return file_paths


def run_git_command(
    command: list[str], cwd: Path | None = None, timeout: int | None = None
) -> subprocess.CompletedProcess[str]:
    """
    Run a git command and handle errors.

    Args:
        command: Git command as list of strings
        cwd: Working directory for the command
        timeout: Command timeout in seconds

    Returns:
        Completed process result

    Raises:
        GitOperationError: If git command fails
    """
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise GitOperationError(
                f"Git command failed: {' '.join(command)}\n"
                f"Error: {result.stderr}\n"
                f"Output: {result.stdout}"
            )
        return result
    except subprocess.TimeoutExpired as e:
        raise GitOperationError(f"Git command timed out: {' '.join(command)}") from e
    except Exception as e:
        raise GitOperationError(f"Git command error: {' '.join(command)}: {e}") from e


def extract_target_files_from_patch(patch_content: str) -> list[str]:
    """
    Extract target files from patch content using multiple methods.

    Args:
        patch_content: Content of the patch file

    Returns:
        List of target file paths
    """
    target_files: list[str] = []

    # Method 1: Look for "--- a/" and "+++ b/" lines
    for line in patch_content.split("\n"):
        if line.startswith("--- a/") or line.startswith("+++ b/"):
            parts = line.split("/", 1)
            if len(parts) > 1:
                file_path = parts[1]
                if file_path not in target_files and not file_path.startswith(
                    "dev/null"
                ):
                    target_files.append(file_path)

    # Method 2: Look for "diff --git a/file b/file" lines if method 1 failed
    if not target_files:
        for line in patch_content.split("\n"):
            if line.startswith("diff --git"):
                match = re.search(r"diff --git a/(.+)\s+b/(.+)", line)
                if match:
                    file_path = match.group(1)
                    if file_path not in target_files and not file_path.startswith(
                        "dev/null"
                    ):
                        target_files.append(file_path)

    # Method 3: Look for any file paths mentioned in the patch
    if not target_files:
        lines = patch_content.split("\n")
        for line in lines:
            if "Checking patch" in line or "patch failed:" in line:
                # Extract file path from error messages
                for word in line.split():
                    if "/" in word or word.endswith(SUPPORTED_FILE_EXTENSIONS):
                        cleaned_word = word.rstrip(".:;,")
                        if cleaned_word and cleaned_word not in target_files:
                            target_files.append(cleaned_word)

    return target_files


def calculate_hunk_location(
    file_lines: list[str],
    hunk_lines: list[str],
    _context_lines: list[str],
    _removals: list[str],
    additions: list[str],
) -> tuple[int, int, int, int]:
    """
    Calculate the correct line numbers for a hunk.

    Args:
        file_lines: Lines of the target file
        hunk_lines: Lines in the hunk
        context_lines: Context lines in the hunk
        removals: Lines to be removed
        additions: Lines to be added

    Returns:
        Tuple of (old_start, old_count, new_start, new_count)
    """
    # Find lines that should be present in the original file (context + removals)
    original_lines = []
    for line in hunk_lines:
        if line.startswith(" ") or line.startswith("-"):
            original_lines.append(line[1:] if line else "")
        elif not line.startswith("+"):
            # Line without prefix, treat as context
            original_lines.append(line)

    if not original_lines:
        # If no original lines to match, find best position for additions
        return 1, 0, 1, len(additions)

    # Find the best match in the file
    best_match = -1
    best_score = -1

    for start_idx in range(len(file_lines)):
        # Check how many consecutive lines match
        score = 0
        for i, orig_line in enumerate(original_lines):
            if (
                start_idx + i < len(file_lines)
                and file_lines[start_idx + i].strip() == orig_line.strip()
            ):
                score += 1
            else:
                break

        if score > best_score:
            best_score = score
            best_match = start_idx

    if best_match == -1:
        # Fallback: place at the beginning
        best_match = 0

    # Calculate counts
    old_count = len(
        [line for line in hunk_lines if line.startswith(" ") or line.startswith("-")]
    )
    new_count = len(
        [line for line in hunk_lines if line.startswith(" ") or line.startswith("+")]
    )

    # Handle lines without prefixes as context
    no_prefix_count = len(
        [line for line in hunk_lines if not line.startswith(("+", "-", " "))]
    )
    old_count += no_prefix_count
    new_count += no_prefix_count

    old_start = best_match + 1  # Line numbers are 1-based
    new_start = best_match + 1

    return old_start, old_count, new_start, new_count


def clean_reasoning_response(content: str) -> str:
    """
    Extract the final response from reasoning model output.

    Reasoning models often include reasoning steps wrapped in tags like:
    <thinking>...</thinking> or <reasoning>...</reasoning>

    This method extracts only the final answer that comes after these reasoning blocks.

    Args:
        content: Raw content from the model

    Returns:
        Cleaned content without reasoning tags
    """
    if not content:
        return content

    # Common reasoning tags used by various models (properly closed tags)
    closed_tag_patterns = [
        r"<thinking>.*?</thinking>",
        r"<reasoning>.*?</reasoning>",
        r"<analysis>.*?</analysis>",
        r"<internal_thought>.*?</internal_thought>",
        r"<think>.*?</think>",
        r"<reason>.*?</reason>",
        # Additional variations for think tags
        r"<think[^>]*>.*?</think>",  # think tags with attributes
        r"<THINK>.*?</THINK>",  # uppercase variants
        r"<Think>.*?</Think>",  # title case variants
    ]

    # Remove all properly closed reasoning blocks first
    cleaned_content = content
    for pattern in closed_tag_patterns:
        cleaned_content = re.sub(
            pattern, "", cleaned_content, flags=re.DOTALL | re.IGNORECASE
        )

    # Handle unclosed tags - look for opening tags without closing tags
    # This handles cases like: <think>\nsome reasoning text\n\nActual response here
    unclosed_patterns = [
        r"<think[^>]*>\s*.*?(?=\n\n[A-Z])",  # unclosed think tag until double newline + capital letter
        r"<thinking[^>]*>\s*.*?(?=\n\n[A-Z])",  # unclosed thinking tag
        r"<reasoning[^>]*>\s*.*?(?=\n\n[A-Z])",  # unclosed reasoning tag
        r"<analysis[^>]*>\s*.*?(?=\n\n[A-Z])",  # unclosed analysis tag
    ]

    for pattern in unclosed_patterns:
        cleaned_content = re.sub(
            pattern, "", cleaned_content, flags=re.DOTALL | re.IGNORECASE
        )

    # Special handling: if content starts with an unclosed tag and has a clear break,
    # extract everything after the first substantial paragraph break
    if re.match(
        r"^\s*<(think|thinking|reasoning|analysis)", cleaned_content, re.IGNORECASE
    ):
        # Look for the first occurrence of double newline followed by actual content
        match = re.search(r"\n\n\s*([A-Z][^<\n].*)", cleaned_content, re.DOTALL)
        if match:
            cleaned_content = match.group(1)

    # Clean up any extra whitespace and newlines
    cleaned_content = re.sub(r"\n\s*\n\s*\n", "\n\n", cleaned_content)
    cleaned_content = cleaned_content.strip()

    # If the cleaned content is empty or too short, return original
    if len(cleaned_content.strip()) < 10:
        return content

    return cleaned_content


def validate_repository_format(repository: str) -> tuple[str, str, str]:
    """
    Validate and parse repository format.

    Args:
        repository: Repository in format 'owner/repo' or full URL

    Returns:
        For GitHub: (service, owner, repo)
        For GitLab: (service, project_path, "")

    Raises:
        ValueError: If repository format is invalid
    """
    # Support full URLs for GitHub and GitLab
    if repository.startswith("https://"):
        if "github.com/" in repository:
            service = "github"
            parts = repository.split("github.com/")[-1].split("/")
            if len(parts) < 2:
                raise ValueError(
                    "Repository URL must be in format 'https://github.com/owner/repo' or 'https://gitlab.com/namespace/project'"
                )
            owner_or_namespace = parts[0]
            repo_or_project = parts[1]
            return service, owner_or_namespace, repo_or_project
        elif "gitlab.com/" in repository:
            service = "gitlab"
            project_path = repository.split("gitlab.com/")[-1].strip("/")
            return service, project_path, ""
        else:
            raise ValueError("Repository URL must be from github.com or gitlab.com")
    # Support short form for GitHub (default)
    if "/" in repository:
        parts = repository.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError("Repository must be in format 'owner/repo'")
        return "github", parts[0], parts[1]
    raise ValueError(
        "Repository must be in format 'owner/repo' or a full GitHub/GitLab URL"
    )
