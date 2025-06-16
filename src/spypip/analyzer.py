#!/usr/bin/env python3
"""
Python Packaging Version Analyzer

This script compares commits between two versions/tags to find packaging changes
and uses an LLM to summarize packaging-related changes.
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, cast

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
    ):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.patches_dir = patches_dir
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
        server_params = StdioServerParameters(
            command="github-mcp-server",
            args=["stdio", "--toolsets", "all"],
            env={**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": github_token or ""},
        )

        self.mcp_client = stdio_client(server_params)
        read_stream, write_stream = await self.mcp_client.__aenter__()
        self.mcp_session = ClientSession(read_stream, write_stream)
        await self.mcp_session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.mcp_session:
            await self.mcp_session.__aexit__(exc_type, exc_val, exc_tb)
        if self.mcp_client:
            await self.mcp_client.__aexit__(exc_type, exc_val, exc_tb)

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

        print(f"Loading file patterns from patches directory: {self.patches_dir}")
        file_paths = self._extract_file_paths_from_patches(patches_path)

        if not file_paths:
            print(
                "Warning: No file paths found in patch files. Using default patterns."
            )
            return self.PACKAGING_PATTERNS

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

            # Get commits from the to_ref branch, then filter by date/commits after from_ref
            result = await self.mcp_session.call_tool(
                "list_commits",
                {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "sha": to_ref,
                    "perPage": 100,
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                if hasattr(first_content, "text"):
                    data = json.loads(first_content.text)
                    if isinstance(data, list):
                        all_commits = cast(List[Dict[str, Any]], data)

                        # Get the commit SHA for from_ref to know where to stop
                        from_commit = await self.get_commit_info(from_ref)
                        if from_commit:
                            from_sha = from_commit["sha"]
                            # Filter commits to only include those after from_ref
                            filtered_commits = []
                            for commit in all_commits:
                                if commit["sha"] == from_sha:
                                    break
                                filtered_commits.append(commit)
                            return filtered_commits
                        else:
                            return all_commits
            return []

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
        print(f"Analyzing commit {commit_sha[:8]}: {commit_title}")

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

    async def analyze_repository(
        self, from_tag: Optional[str] = None, to_tag: str = "main"
    ) -> List[CommitSummary]:
        print(f"Starting analysis of {self.repo_owner}/{self.repo_name}")

        # Determine the from_tag if not provided
        if not from_tag:
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
        print(f"Found {len(commits)} commits between {from_tag} and {to_tag}")

        # Analyze each commit for packaging changes
        packaging_commits = []
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
        print("\n" + "=" * 80)
        print("PYTHON PACKAGING VERSION ANALYSIS RESULTS")
        print("=" * 80)

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
