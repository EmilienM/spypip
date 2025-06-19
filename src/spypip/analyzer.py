#!/usr/bin/env python3
"""
Python Packaging Version Analyzer

This script compares commits between two versions/tags to find packaging changes
and uses an LLM to summarize packaging-related changes.
"""

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, cast, Tuple

# Type checking imports
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

import openai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass
class PackagingChange:
    file_path: str
    change_type: str  # 'added', 'modified', 'removed'
    additions: int
    deletions: int
    patch: str


@dataclass
class CommitSummary:
    sha: str
    title: str
    author: str
    url: str
    date: str
    packaging_changes: List[PackagingChange]
    ai_summary: Optional[str] = None


@dataclass
class PatchFailure:
    patch_name: str
    error_output: str


class PackagingVersionAnalyzer:
    PACKAGING_PATTERNS = [
        r"requirements.*\.txt$",
        r".*requirements.*\.txt$",
        r"pyproject\.toml$",
        r"setup\.py$",
        r"setup\.cfg$",
        r"poetry\.lock$",
        r"Pipfile$",
        r"Pipfile\.lock$",
        r"constraints.*\.txt$",
        r".*constraints.*\.txt$",
        r"environment\.ya?ml$",
        r"conda.*\.ya?ml$",
        r".*\.spec$",  # RPM spec files
        r"Containerfile.*$",
        r"Dockerfile.*$",
        r".*\.dockerfile$",
        r"pip\.conf$",
        r"tox\.ini$",
        r".*\/requirements\/.*\.txt$",
    ]

    def __init__(
        self,
        repo_owner: str,
        repo_name: str,
        openai_api_key: str,
        patches_dir: Optional[str] = None,
        json_output: bool = False,
    ):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.patches_dir = patches_dir
        self.json_output = json_output
        base_url = os.getenv(
            "OPENAI_ENDPOINT_URL", "https://models.github.ai/inference"
        )
        self.model_name = os.getenv("MODEL_NAME", "openai/gpt-4.1")
        self.openai_client = openai.OpenAI(api_key=openai_api_key, base_url=base_url)
        self.mcp_client: Optional[Any] = None
        self.mcp_session: Optional[ClientSession] = None

        # Initialize file patterns - use patch files if provided, otherwise use defaults
        self.patch_file_paths: Set[str] = (
            set()
        )  # Will be populated if patches_dir is used
        self.file_patterns = self._load_file_patterns()

    async def __aenter__(self):
        github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")

        # Create server parameters with different logging settings for JSON mode
        env_vars = {**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": github_token or ""}

        # Try to suppress MCP server logging when in JSON mode
        if self.json_output:
            # Set environment variables that might suppress logging
            env_vars.update(
                {
                    "MCP_LOG_LEVEL": "ERROR",  # Try to suppress info logs
                    "RUST_LOG": "error",  # Suppress Rust logging if applicable
                }
            )

        # Always suppress MCP server startup messages by wrapping the command
        # Create a shell command that redirects stderr to /dev/null
        if os.name == "posix":  # Unix-like systems
            command = "sh"
            args = ["-c", "github-mcp-server stdio --toolsets all 2>/dev/null"]
        else:  # Windows
            command = "cmd"
            args = ["/c", "github-mcp-server stdio --toolsets all 2>nul"]

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env_vars,
        )

        self.mcp_client = stdio_client(server_params)

        read_stream, write_stream = await self.mcp_client.__aenter__()
        self.mcp_session = ClientSession(read_stream, write_stream)
        await self.mcp_session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Close session first, then client, with better exception handling
        session_exception = None
        client_exception = None

        # Close MCP session
        if self.mcp_session:
            try:
                await self.mcp_session.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                session_exception = e
                if not self.json_output:
                    print(f"Warning: Error closing MCP session: {e}")

        # Close MCP client
        if self.mcp_client:
            try:
                await self.mcp_client.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                client_exception = e
                if not self.json_output:
                    print(f"Warning: Error closing MCP client: {e}")

        # If we had an original exception, don't suppress it
        # Only suppress cleanup exceptions if there was no original exception
        if exc_type is None and (session_exception or client_exception):
            # If there was no original exception but cleanup failed, we might want to raise
            # However, for now we'll just log and continue to avoid masking the original issue
            pass

        return False  # Don't suppress any original exceptions

    def _load_file_patterns(self) -> List[str]:
        """
        Load file patterns from patch files if patches_dir is provided,
        otherwise return the default packaging patterns.
        """
        if not self.patches_dir:
            return self.PACKAGING_PATTERNS

        patches_path = Path(self.patches_dir)
        if not patches_path.exists():
            print(
                f"Warning: Patches directory '{self.patches_dir}' does not exist. Using default patterns."
            )
            return self.PACKAGING_PATTERNS

        if not patches_path.is_dir():
            print(
                f"Warning: Patches path '{self.patches_dir}' is not a directory. Using default patterns."
            )
            return self.PACKAGING_PATTERNS

        if not self.json_output:
            print(f"Loading file patterns from patches directory: {self.patches_dir}")
        file_paths = self._extract_file_paths_from_patches(patches_path)

        if not file_paths:
            if not self.json_output:
                print(
                    "Warning: No file paths found in patch files. Using default patterns."
                )
            return self.PACKAGING_PATTERNS

        if not self.json_output:
            print(f"Found {len(file_paths)} file paths in patches")
        # Store the exact file paths - we'll match them directly
        self.patch_file_paths = file_paths
        return []  # Return empty list since we'll use exact path matching

    def _extract_file_paths_from_patches(self, patches_path: Path) -> Set[str]:
        """
        Extract file paths from patch files in the given directory.

        Patch files can be in various formats:
        - Git patch files (.patch, .diff)
        - Plain text files containing file paths (one per line)
        """
        file_paths = set()

        # Look for patch files and text files
        patch_extensions = {".patch", ".diff", ".txt"}

        for patch_file in patches_path.iterdir():
            if not patch_file.is_file():
                continue

            if patch_file.suffix.lower() not in patch_extensions:
                continue

            try:
                with open(patch_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                # Extract file paths from different patch formats
                if patch_file.suffix.lower() in {".patch", ".diff"}:
                    # Git patch format: look for "--- a/file" and "+++ b/file" lines
                    git_paths = re.findall(
                        r"^[+-]{3}\s+[ab]/(.+)$", content, re.MULTILINE
                    )
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
                print(f"Warning: Could not read patch file '{patch_file}': {e}")
                continue

        return file_paths

    def is_patched(self, file_path: str) -> bool:
        # If we have patch file paths, check for exact matches only
        if self.patch_file_paths:
            return file_path in self.patch_file_paths

        # Fall back to default pattern matching
        for pattern in self.file_patterns:
            if re.search(pattern, file_path, re.IGNORECASE):
                return True
        return False

    async def get_latest_tag(self) -> Optional[str]:
        """Get the latest tag from the repository."""
        try:
            if self.mcp_session is None:
                return None
            result = await self.mcp_session.call_tool(
                "list_tags",
                {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "perPage": 1,
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                if hasattr(first_content, "text"):
                    data = json.loads(first_content.text)
                    if isinstance(data, list) and len(data) > 0:
                        return str(data[0]["name"])
            return None

        except Exception as e:
            print(f"Error fetching latest tag: {e}")
            return None

    async def get_previous_tag(self, to_tag: str) -> Optional[str]:
        """Get the tag that comes before the specified tag in chronological order."""
        try:
            if self.mcp_session is None:
                return None

            # Get all tags with a reasonable limit
            result = await self.mcp_session.call_tool(
                "list_tags",
                {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "perPage": 100,  # Get more tags to find the previous one
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                if hasattr(first_content, "text"):
                    data = json.loads(first_content.text)
                    if isinstance(data, list) and len(data) > 0:
                        tags = [str(tag["name"]) for tag in data]

                        # Find the to_tag in the list
                        try:
                            to_tag_index = tags.index(to_tag)
                            # If we found the tag and there's a previous one, return it
                            if to_tag_index + 1 < len(tags):
                                return tags[to_tag_index + 1]
                        except ValueError:
                            # to_tag not found in the list, might need more tags
                            print(
                                f"Warning: Tag '{to_tag}' not found in the first {len(tags)} tags"
                            )
                            pass
            return None

        except Exception as e:
            print(f"Error fetching previous tag for {to_tag}: {e}")
            return None

    async def get_commits_between_refs(
        self, from_ref: str, to_ref: str
    ) -> List[Dict[str, Any]]:
        """Get commits between two references (tags/branches)."""
        print(
            f"Fetching commits between {from_ref} and {to_ref} for {self.repo_owner}/{self.repo_name}..."
        )

        try:
            if self.mcp_session is None:
                return []

            # Get the commit SHA for from_ref to know where to stop
            from_commit = await self.get_commit_info(from_ref)
            from_sha = from_commit["sha"] if from_commit else None

            all_commits = []
            page = 1
            per_page = 100

            while True:
                # Get commits from the to_ref branch with pagination
                result = await self.mcp_session.call_tool(
                    "list_commits",
                    {
                        "owner": self.repo_owner,
                        "repo": self.repo_name,
                        "sha": to_ref,
                        "perPage": per_page,
                        "page": page,
                    },
                )

                if not (hasattr(result, "content") and result.content):
                    break

                first_content = result.content[0]
                if not hasattr(first_content, "text"):
                    break

                data = json.loads(first_content.text)
                if not isinstance(data, list) or len(data) == 0:
                    break

                page_commits = cast(List[Dict[str, Any]], data)

                # Filter commits to only include those after from_ref
                found_from_ref = False
                for commit in page_commits:
                    if from_sha and commit["sha"] == from_sha:
                        found_from_ref = True
                        break
                    all_commits.append(commit)

                # If we found the from_ref commit or got less than per_page commits, we're done
                if found_from_ref or len(page_commits) < per_page:
                    break

                page += 1

            print(f"Found {len(all_commits)} commits between {from_ref} and {to_ref}")
            return all_commits

        except Exception as e:
            print(f"Error fetching commits: {e}")
            return []

    async def get_commit_info(self, ref: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific commit/tag/branch."""
        try:
            if self.mcp_session is None:
                return None
            result = await self.mcp_session.call_tool(
                "get_commit",
                {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "sha": ref,
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                if hasattr(first_content, "text"):
                    data = json.loads(first_content.text)
                    return cast(Dict[str, Any], data)
            return None

        except Exception as e:
            print(f"Error fetching commit info for {ref}: {e}")
            return None

    async def get_commit_files(self, commit_sha: str) -> List[Dict[str, Any]]:
        """Get files changed in a specific commit."""
        try:
            if self.mcp_session is None:
                return []
            result = await self.mcp_session.call_tool(
                "get_commit",
                {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "sha": commit_sha,
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                if hasattr(first_content, "text"):
                    data = json.loads(first_content.text)
                    files = data.get("files", [])
                    return (
                        cast(List[Dict[str, Any]], files)
                        if isinstance(files, list)
                        else []
                    )
            return []

        except Exception as e:
            print(f"Error fetching files for commit {commit_sha}: {e}")
            return []

    async def analyze_commit_for_packaging_changes(
        self, commit: Dict[str, Any]
    ) -> Optional[CommitSummary]:
        commit_sha = commit["sha"]
        commit_title = commit["commit"]["message"].split("\n")[
            0
        ]  # First line of commit message

        files = await self.get_commit_files(commit_sha)
        packaging_changes = []

        for file_info in files:
            file_path = file_info.get("filename", "")

            if self.is_patched(file_path):
                change = PackagingChange(
                    file_path=file_path,
                    change_type=file_info.get("status", "modified"),
                    additions=file_info.get("additions", 0),
                    deletions=file_info.get("deletions", 0),
                    patch=file_info.get("patch", ""),
                )
                packaging_changes.append(change)

        if packaging_changes:
            return CommitSummary(
                sha=commit_sha,
                title=commit_title,
                author=commit["commit"]["author"]["name"],
                url=commit["html_url"],
                date=commit["commit"]["author"]["date"],
                packaging_changes=packaging_changes,
            )

        return None

    def generate_ai_summary(self, commit_summary: CommitSummary) -> str:
        print(f"Generating AI summary for commit {commit_summary.sha[:8]}...")

        context = f"""
Commit {commit_summary.sha}: {commit_summary.title}
Author: {commit_summary.author}
Date: {commit_summary.date}
URL: {commit_summary.url}

Packaging files changed:
"""

        for change in commit_summary.packaging_changes:
            context += f"\n- {change.file_path} ({change.change_type})"
            context += f" +{change.additions} -{change.deletions}"

            if change.patch:
                context += f"\n  Patch preview:\n{change.patch[:500]}..."

        prompt = f"""
Analyze the following commit that touches Python packaging files.
Provide a concise summary of what packaging-related changes are being made.
Focus on:
- Dependencies being added, removed, or updated
- Build configuration changes
- Containerization changes
- Version constraints modifications
- New packaging tools or methods introduced

Context:
{context}

Please provide a clear, concise summary of the packaging implications of this commit.
"""

        try:
            response = self.openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert Python packaging and dependency management analyst specializing in analyzing GitHub commits for packaging-related changes. Your role is to provide clear, actionable insights about how changes to packaging files impact project dependencies, build processes, and deployment.

Key areas of expertise:
- Python packaging files: requirements.txt, pyproject.toml, setup.py, setup.cfg, poetry.lock, Pipfile
- Build and dependency management: pip, poetry, conda, tox configurations
- Containerization: Dockerfiles, Containerfiles, and container-specific requirements
- Version constraints and dependency resolution conflicts
- Security implications of dependency updates
- Performance and compatibility impacts of package changes

When analyzing commits, focus on:
1. **Dependency Changes**: New packages added, removed, or updated with version implications
2. **Version Constraints**: Changes to version pinning, ranges, or compatibility requirements
3. **Build Configuration**: Modifications to build tools, scripts, or packaging metadata
4. **Environment Management**: Changes to virtual environments, conda environments, or containerization
5. **Security & Compliance**: Dependency vulnerabilities, license changes, or policy violations
6. **Performance Impact**: Dependencies that may affect runtime performance or bundle size
7. **Breaking Changes**: Updates that may introduce compatibility issues or require code changes

Provide concise, technical summaries that help developers understand the packaging implications and potential risks or benefits of the changes made in each commit.""",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            if content:
                # Handle reasoning models that include reasoning steps
                final_content = self._extract_final_response(content)
                return final_content.strip()
            else:
                return "No summary generated"

        except Exception as e:
            print(f"Error generating AI summary: {e}")
            return f"Error generating summary: {str(e)}"

    def _extract_final_response(self, content: str) -> str:
        """
        Extract the final response from reasoning model output.

        Reasoning models often include reasoning steps wrapped in tags like:
        <thinking>...</thinking> or <reasoning>...</reasoning>

        This method extracts only the final answer that comes after these reasoning blocks.
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

    def analyze_patch_compatibility(
        self, patch_file: Path, repo_dir: Path
    ) -> Dict[str, Any]:
        """
        Analyze why a patch might not be compatible with the current codebase.
        Returns detailed information about potential issues and suggestions.
        """
        analysis: Dict[str, Any] = {
            "patch_file": patch_file.name,
            "target_files": [],
            "missing_files": [],
            "potential_issues": [],
            "suggestions": [],
        }

        try:
            with open(patch_file, "r", encoding="utf-8", errors="ignore") as f:
                patch_content = f.read()

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

    async def _regenerate_patch_with_llm(
        self, patch_file: Path, repo_dir: Path, ref: str
    ) -> Optional[str]:
        """
        Use LLM to regenerate a patch file when the original fails to apply.

        Args:
            patch_file: Path to the original patch file that failed
            repo_dir: Path to the cloned repository
            ref: Git reference being tested

        Returns:
            The regenerated patch content if successful, None otherwise
        """
        try:
            # Read the original patch content
            with open(patch_file, "r", encoding="utf-8", errors="ignore") as f:
                original_patch = f.read()

            # Extract target files from the patch using multiple methods
            target_files: List[str] = []

            # Method 1: Look for "--- a/" and "+++ b/" lines
            for line in original_patch.split("\n"):
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
                for line in original_patch.split("\n"):
                    if line.startswith("diff --git"):
                        match = re.search(r"diff --git a/(.+)\s+b/(.+)", line)
                        if match:
                            file_path = match.group(1)
                            if (
                                file_path not in target_files
                                and not file_path.startswith("dev/null")
                            ):
                                target_files.append(file_path)

            # Method 3: Look for any file paths mentioned in the patch
            if not target_files:
                # Try to find file paths that look like they could be target files
                # This is a fallback for unusual patch formats
                lines = original_patch.split("\n")
                for i, line in enumerate(lines):
                    if "Checking patch" in line or "patch failed:" in line:
                        # Extract file path from error messages
                        for word in line.split():
                            if "/" in word or word.endswith(
                                (
                                    ".txt",
                                    ".py",
                                    ".c",
                                    ".cpp",
                                    ".h",
                                    ".cmake",
                                    ".toml",
                                    ".cfg",
                                    ".yml",
                                    ".yaml",
                                )
                            ):
                                cleaned_word = word.rstrip(".:;,")
                                if cleaned_word and cleaned_word not in target_files:
                                    target_files.append(cleaned_word)

            if not target_files:
                return None

            # Get current content of target files
            current_files_content = {}
            for file_path in target_files:
                target_path = repo_dir / file_path
                if target_path.exists():
                    try:
                        with open(
                            target_path, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            current_files_content[file_path] = f.read()
                    except Exception:
                        continue

            if not current_files_content:
                return None

            # Prepare the LLM prompt
            files_context = ""
            for file_path, content in current_files_content.items():
                files_context += (
                    f"\n--- Current content of {file_path} ---\n{content}\n"
                )

            prompt = f"""You are a patch regeneration expert. A patch file failed to apply to a repository at reference '{ref}'.

Your task is to analyze the original patch and the current file content, then generate a new patch that achieves the same intended changes but applies cleanly to the current codebase.

Original patch that failed:
```
{original_patch}
```

Current file content:{files_context}

IMPORTANT ANALYSIS GUIDELINES:
1. Look at what lines the original patch REMOVED (lines starting with '-') and ensure they are removed from the current content
2. Look at what lines the original patch ADDED (lines starting with '+') and ensure they are added in the appropriate location
3. If a line that should be removed has moved to a different location in the current file, find it and remove it from there
4. If dependencies or content have been reordered, adapt the patch to work with the current structure
5. Maintain the same intent: removals should still be removed, additions should still be added

Please generate a new patch in unified diff format that:
1. Achieves the EXACT SAME INTENT as the original patch (same additions, same removals)
2. Applies cleanly to the current file content by finding the correct locations
3. Uses proper unified diff format with correct line numbers
4. Includes appropriate context lines
5. Can be applied using 'patch -p1' command

Return ONLY the patch content, no explanations or markdown formatting."""

            # Call the LLM
            response = self.openai_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert patch regeneration system that creates unified diff patches. You understand patch formats and can adapt patches to different codebases while preserving the original intent.

Key principles:
1. PRESERVE INTENT: If the original patch removed a line, the new patch must also remove that line (even if it moved)
2. PRESERVE INTENT: If the original patch added a line, the new patch must also add that line
3. ADAPT LOCATIONS: Find where removed lines are located in the current file and remove them from there
4. ADAPT LOCATIONS: Add new lines in the most appropriate location based on the current file structure
5. HANDLE REORDERING: Account for content that may have been reordered or moved since the original patch

Always generate valid unified diff format patches that can be applied with 'patch -p1' and achieve the exact same end result as the original patch intended.""",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.1,
            )

            content = response.choices[0].message.content  # type: ignore
            if content:
                # Handle reasoning models that include reasoning steps
                regenerated_patch = self._extract_final_response(content)
                # Fix the line numbers in the patch headers
                fixed_patch = self._fix_patch_line_numbers(
                    regenerated_patch, current_files_content
                )
                return fixed_patch.strip()

        except Exception as e:
            print(f"LLM patch regeneration failed: {e}")

        return None

    def _fix_patch_line_numbers(
        self, patch_content: str, current_files_content: Dict[str, str]
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
                old_start, old_count, new_start, new_count = (
                    self._calculate_hunk_location(
                        file_lines, hunk_lines, context_lines, removals, additions
                    )
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

    def _calculate_hunk_location(
        self,
        file_lines: List[str],
        hunk_lines: List[str],
        context_lines: List[str],
        removals: List[str],
        additions: List[str],
    ) -> Tuple[int, int, int, int]:
        """
        Calculate the correct line numbers for a hunk.

        Returns:
            (old_start, old_count, new_start, new_count)
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
            old_start = 1
            old_count = 0
            new_start = 1
            new_count = len(additions)
            return old_start, old_count, new_start, new_count

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
            [
                line
                for line in hunk_lines
                if line.startswith(" ") or line.startswith("-")
            ]
        )
        new_count = len(
            [
                line
                for line in hunk_lines
                if line.startswith(" ") or line.startswith("+")
            ]
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

    async def _test_regenerated_patch(
        self,
        regenerated_patch: str,
        repo_dir: Path,
        original_patch_name: str,
        json_output: bool,
        show_content_always: bool = False,
    ) -> bool:
        """
        Test if the regenerated patch applies successfully and print it if it does.

        Args:
            regenerated_patch: The LLM-generated patch content
            repo_dir: Path to the cloned repository
            original_patch_name: Name of the original patch file
            json_output: Whether we're in JSON output mode

        Returns:
            True if patch applies successfully, False otherwise
        """
        try:
            # Ensure repository is in clean state before testing
            reset_result = subprocess.run(
                ["git", "reset", "--hard", "HEAD"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )

            if reset_result.returncode != 0:
                if not json_output:
                    print(
                        f"Warning: Could not reset repository to clean state: {reset_result.stderr}"
                    )

            # Write the regenerated patch to a temporary file
            import tempfile

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
                    if not json_output:
                        print(
                            f"✓ Successfully regenerated patch for {original_patch_name}"
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
                    if not json_output:
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
                import os

                try:
                    os.unlink(tmp_patch_path)
                except OSError:
                    pass

        except Exception as e:
            if not json_output:
                print(f"Error testing regenerated patch: {e}")
            return False

    def _generate_jira_content(
        self, failed_patches: List[PatchFailure], ref: str
    ) -> str:
        """
        Generate Jira ticket content from failed patches.
        """
        content_lines = [
            f"Some patches for {self.repo_owner}/{self.repo_name} failed to apply on {ref}:",
            "",
        ]

        for patch_failure in failed_patches:
            content_lines.append(f"Applying patch: {patch_failure.patch_name}")
            content_lines.append(f"✗ Patch {patch_failure.patch_name} FAILED to apply")
            content_lines.append(patch_failure.error_output)
            content_lines.append("")

        content_lines.append("You'll need to fix these patches manually.")

        return "\n".join(content_lines)

    async def check_patch_application(
        self, ref: str = "main", json_output: bool = False
    ) -> bool:
        """
        Check if patches can be applied to the repository at the specified ref.

        This method:
        1. Clones the repository to a temporary directory (including submodules)
        2. Checks out the specified ref
        3. Attempts to apply each patch file
        4. Reports success/failure for each patch

        Args:
            ref: The git reference to check patches against
            json_output: If True, output failed patches in JSON format for Jira tickets

        Returns True if all patches apply successfully, False otherwise.
        """
        if not self.patches_dir:
            if not json_output:
                print("Error: No patches directory specified")
            return False

        patches_path = Path(self.patches_dir)
        if not patches_path.exists() or not patches_path.is_dir():
            if not json_output:
                print(
                    f"Error: Patches directory '{self.patches_dir}' does not exist or is not a directory"
                )
            return False

        if not json_output:
            print(
                f"Checking patch application for {self.repo_owner}/{self.repo_name} at ref '{ref}'"
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
            if not json_output:
                print(
                    "Warning: No patch files (.patch or .diff) found in patches directory"
                )
                print(
                    "Only .patch and .diff files are supported for patch application testing"
                )
            return True  # No patches to apply is considered success

        if not json_output:
            print(f"Found {len(patch_files)} patch files to test")

        # Create temporary directory for repository clone
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir) / "repo"

            try:
                # Clone the repository
                if not json_output:
                    print("Cloning repository to temporary directory...")
                clone_url = f"https://github.com/{self.repo_owner}/{self.repo_name}.git"

                clone_result = subprocess.run(
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
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )

                if clone_result.returncode != 0:
                    print(f"Error cloning repository: {clone_result.stderr}")
                    return False

                if not json_output:
                    print("Successfully cloned repository")

                # Test each patch
                all_patches_successful = True
                failed_patches = []

                for patch_file in patch_files:
                    if not json_output:
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
                        if not json_output:
                            print(
                                f"✓ Patch {patch_file.name} can be applied successfully"
                            )
                    else:
                        # Collect error information for JSON output
                        error_output = []
                        if patch_result.stderr:
                            error_output.append(
                                f"  Error: {patch_result.stderr.strip()}"
                            )
                        if patch_result.stdout:
                            error_output.append(
                                f"  Output: {patch_result.stdout.strip()}"
                            )

                        if not json_output:
                            print(f"✗ Patch {patch_file.name} FAILED to apply")
                            for line in error_output:
                                print(line)
                            print("  Attempting LLM-powered patch regeneration...")

                        # Try to regenerate the patch using LLM
                        regenerated_patch = await self._regenerate_patch_with_llm(
                            patch_file, repo_dir, ref
                        )
                        if regenerated_patch:
                            # Test the regenerated patch and always show the content
                            regenerated_patch_result = (
                                await self._test_regenerated_patch(
                                    regenerated_patch,
                                    repo_dir,
                                    patch_file.name,
                                    json_output,
                                    show_content_always=True,
                                )
                            )
                            if regenerated_patch_result:
                                continue  # Skip the rest of the error handling since patch was successfully regenerated
                        else:
                            if not json_output:
                                print(
                                    f"LLM failed to regenerate patch for {patch_file.name}"
                                )

                        if not json_output:
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
                            diagnostic_info = (
                                "  Note: Patch would succeed with --ignore-whitespace"
                            )
                            error_output.append(diagnostic_info)
                            if not json_output:
                                print(diagnostic_info)
                        else:
                            # Try to show what files the patch is trying to modify
                            try:
                                with open(patch_file, "r") as f:
                                    patch_content = f.read()

                                # Extract file paths from patch
                                file_paths = set()
                                for line in patch_content.split("\n"):
                                    if line.startswith("--- a/") or line.startswith(
                                        "+++ b/"
                                    ):
                                        path = (
                                            line.split("/", 1)[1]
                                            if "/" in line
                                            else line
                                        )
                                        file_paths.add(path)

                                if file_paths:
                                    file_info = f"  Patch targets these files: {', '.join(sorted(file_paths))}"
                                    error_output.append(file_info)
                                    if not json_output:
                                        print(file_info)

                                    # Check if these files exist
                                    for file_path in file_paths:
                                        target_file = repo_dir / file_path
                                        if target_file.exists():
                                            status_info = f"    ✓ {file_path} exists"
                                            error_output.append(status_info)
                                            if not json_output:
                                                print(status_info)
                                        else:
                                            status_info = (
                                                f"    ✗ {file_path} does not exist"
                                            )
                                            error_output.append(status_info)
                                            if not json_output:
                                                print(status_info)

                            except Exception as e:
                                error_info = f"  Could not analyze patch content: {e}"
                                error_output.append(error_info)
                                if not json_output:
                                    print(error_info)

                        # Perform detailed analysis of why the patch failed
                        analysis = self.analyze_patch_compatibility(
                            patch_file, repo_dir
                        )

                        if analysis["potential_issues"]:
                            if not json_output:
                                print("  Potential issues:")
                            for issue in analysis["potential_issues"]:
                                issue_info = f"    - {issue}"
                                error_output.append(issue_info)
                                if not json_output:
                                    print(issue_info)

                        if analysis["suggestions"]:
                            if not json_output:
                                print("  Suggestions:")
                            for suggestion in analysis["suggestions"]:
                                suggestion_info = f"    - {suggestion}"
                                error_output.append(suggestion_info)
                                if not json_output:
                                    print(suggestion_info)

                        # Store the failed patch information
                        failed_patches.append(
                            PatchFailure(
                                patch_name=patch_file.name,
                                error_output="\n".join(error_output),
                            )
                        )

                        all_patches_successful = False

                # Handle output based on format
                if json_output:
                    if failed_patches:
                        # Generate JSON output for Jira tickets
                        json_output_data = {
                            "title": f"Failed to apply patches {self.repo_owner}/{self.repo_name} for '{ref}'",
                            "content": self._generate_jira_content(failed_patches, ref),
                        }
                        print(json.dumps(json_output_data, indent=2))
                    # For JSON output, don't print success messages to keep output clean
                else:
                    print(f"\n{'=' * 50}")
                    if all_patches_successful:
                        print("✓ ALL PATCHES CAN BE APPLIED SUCCESSFULLY")
                    else:
                        print("✗ SOME PATCHES FAILED TO APPLY")

                return all_patches_successful

            except subprocess.TimeoutExpired:
                print("Error: Repository clone timed out")
                return False
            except Exception as e:
                print(f"Error during patch application check: {e}")
                return False

    async def analyze_repository(
        self, from_tag: Optional[str] = None, to_tag: str = "main"
    ) -> List[CommitSummary]:
        print(f"Starting analysis of {self.repo_owner}/{self.repo_name}")

        # Determine the from_tag if not provided
        if not from_tag:
            # If to_tag is specified and not 'main', try to get the previous tag
            if to_tag != "main":
                from_tag = await self.get_previous_tag(to_tag)
                if from_tag:
                    print(f"Using previous tag as from_tag: {from_tag}")
                else:
                    print(
                        f"Warning: Could not find a tag before '{to_tag}'. Using latest tag as fallback."
                    )
                    from_tag = await self.get_latest_tag()
                    if not from_tag:
                        print(
                            "Warning: No tags found in repository. Using 'HEAD~10' as fallback."
                        )
                        from_tag = "HEAD~10"
                    else:
                        print(f"Using latest tag as from_tag: {from_tag}")
            else:
                # For 'main' or default case, use latest tag as before
                from_tag = await self.get_latest_tag()
                if not from_tag:
                    print(
                        "Warning: No tags found in repository. Using 'HEAD~10' as fallback."
                    )
                    from_tag = "HEAD~10"
                else:
                    print(f"Using latest tag as from_tag: {from_tag}")

        print(f"Comparing commits from {from_tag} to {to_tag}")

        # Get commits between the two references
        commits = await self.get_commits_between_refs(from_tag, to_tag)

        # Analyze each commit for packaging changes
        packaging_commits = []

        # Print simple message with commit count
        if commits:
            print(f"Anazlying {len(commits)} commits")

        for commit in commits:
            commit_summary = await self.analyze_commit_for_packaging_changes(commit)
            if commit_summary:
                packaging_commits.append(commit_summary)

        if self.patches_dir:
            print(
                f"Found {len(packaging_commits)} commits touching files from patches directory"
            )
            if self.patch_file_paths:
                print("Monitored files:")
                for file_path in sorted(self.patch_file_paths):
                    print(f"  - {file_path}")
        else:
            print(f"Found {len(packaging_commits)} commits with packaging changes")

        for commit_summary in packaging_commits:
            commit_summary.ai_summary = self.generate_ai_summary(commit_summary)

        return packaging_commits

    def print_results(self, results: List[CommitSummary]):
        # Show information about file patterns being used
        if self.patches_dir:
            print(f"Using custom file paths from patches directory: {self.patches_dir}")
            print(f"Monitoring {len(self.patch_file_paths)} specific file paths")
        else:
            print(
                f"Using default packaging file patterns ({len(self.file_patterns)} patterns)"
            )
        print("-" * 40)

        if not results:
            print("No commits with packaging changes found.")
            return

        for i, commit in enumerate(results, 1):
            print(f"\n{i}. Commit {commit.sha[:8]}: {commit.title}")
            print(f"   Author: {commit.author}")
            print(f"   Date: {commit.date}")
            print(f"   URL: {commit.url}")
            print(f"   Files changed ({len(commit.packaging_changes)}):")

            for change in commit.packaging_changes:
                print(
                    f"     - {change.file_path} ({change.change_type}) +{change.additions}/-{change.deletions}"
                )

            print("\n   AI Summary:")
            print(f"   {commit.ai_summary}")
            print("-" * 40)
