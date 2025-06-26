"""
Refactored Python Packaging Version Analyzer

This module provides the main analyzer class with improved separation of concerns,
better error handling, and cleaner architecture.
"""

from typing import Any

from .constants import (
    DEFAULT_MAX_COMMITS,
    DEFAULT_PACKAGING_PATTERNS,
    WARNING_MESSAGES,
)
from .exceptions import ConfigurationError
from .github_client import GitHubMCPClient
from .gitlab_client import GitLabMCPClient
from .llm_client import LLMClient
from .models import CommitSummary, PackagingChange
from .patch_operations import PatchManager
from .utils import validate_repository_format


class PackagingVersionAnalyzer:
    """
    Analyzes GitHub repositories to compare commits between versions/tags
    that touch Python packaging files and provides AI-powered summaries.
    """

    def __init__(
        self,
        repository: str,
        openai_api_key: str,
        patches_dir: str | None = None,
        json_output: bool = False,
        max_commits: int = DEFAULT_MAX_COMMITS,
    ):
        """
        Initialize the analyzer.

        Args:
            repository: Repository in format 'owner/repo' or full URL
            openai_api_key: OpenAI API key for LLM operations
            patches_dir: Optional directory containing patch files
            json_output: Whether to output in JSON format
            max_commits: Maximum number of commits to analyze

        Raises:
            ConfigurationError: If configuration is invalid
        """
        try:
            self.service, self.repo_owner, self.repo_name = validate_repository_format(
                repository
            )
        except ValueError as e:
            raise ConfigurationError(str(e)) from e

        # For GitLab, store the full project path
        self.project_path: str | None = None
        if self.service == "gitlab":
            self.project_path = self.repo_owner.rstrip("/")  # Ensure no trailing slash
        else:
            self.project_path = None

        self.patches_dir = patches_dir
        self.json_output = json_output
        self.max_commits = max_commits

        # Initialize components
        self.mcp_client: Any = None
        self.llm_client = LLMClient(openai_api_key)
        self.patch_manager = PatchManager(patches_dir, json_output)

        # Initialize file patterns
        self.file_patterns = self.patch_manager.load_file_patterns(
            DEFAULT_PACKAGING_PATTERNS
        )

    async def __aenter__(self) -> "PackagingVersionAnalyzer":
        """Initialize MCP client for the appropriate service, unless already set (for testing)."""
        # Patch for test compatibility: if github_client is set, use it as mcp_client
        github_client = getattr(self, "github_client", None)
        if github_client is not None:
            self.mcp_client = github_client
        if self.mcp_client is None:
            if self.service == "github":
                self.mcp_client = GitHubMCPClient(self.json_output)
            elif self.service == "gitlab":
                self.mcp_client = GitLabMCPClient(self.json_output)
            else:
                raise ConfigurationError(f"Unsupported service: {self.service}")
            await self.mcp_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Clean up MCP client."""
        if self.mcp_client and hasattr(self.mcp_client, "__aexit__"):
            result = await self.mcp_client.__aexit__(exc_type, exc_val, exc_tb)
            return bool(result)
        return False

    def is_patched(self, file_path: str) -> bool:
        """
        Check if a file path is covered by patches or patterns.

        Args:
            file_path: File path to check

        Returns:
            True if file is covered by patches/patterns
        """
        return self.patch_manager.is_patched(file_path, self.file_patterns)

    async def get_latest_tag(self) -> str | None:
        """Get the latest tag from the repository."""
        if not self.mcp_client:
            return None
        if self.service == "gitlab":
            result = await self.mcp_client.get_latest_tag(self.project_path, "")
        else:
            result = await self.mcp_client.get_latest_tag(
                self.repo_owner, self.repo_name
            )
        if isinstance(result, str) or result is None:
            return result
        return str(result)

    async def get_previous_tag(self, to_tag: str) -> str | None:
        """Get the tag that comes before the specified tag in chronological order."""
        if not self.mcp_client:
            return None
        if self.service == "gitlab":
            result = await self.mcp_client.get_previous_tag(
                self.project_path, "", to_tag
            )
        else:
            result = await self.mcp_client.get_previous_tag(
                self.repo_owner, self.repo_name, to_tag
            )
        if isinstance(result, str) or result is None:
            return result
        return str(result)

    async def get_commits_between_refs(
        self, from_ref: str, to_ref: str
    ) -> list[dict[str, Any]]:
        """Get commits between two references (tags/branches)."""
        if not self.mcp_client:
            return []

        print(
            f"Fetching commits between {from_ref} and {to_ref} for {self.repo_owner}/{self.repo_name}..."
        )

        if self.service == "gitlab":
            commits = await self.mcp_client.get_commits_between_refs(
                self.project_path, from_ref, to_ref, self.max_commits
            )
        else:
            commits = await self.mcp_client.get_commits_between_refs(
                self.repo_owner, self.repo_name, from_ref, to_ref, self.max_commits
            )

        if not isinstance(commits, list):
            return []
        # Defensive: ensure each item is a dict
        commits = [c for c in commits if isinstance(c, dict)]

        if len(commits) >= self.max_commits:
            print(
                f"Found {len(commits)} commits between {from_ref} and {to_ref} (limited to {self.max_commits})"
            )
        else:
            print(f"Found {len(commits)} commits between {from_ref} and {to_ref}")

        return commits

    async def get_commit_info(self, ref: str) -> dict[str, Any] | None:
        """Get information about a specific commit/tag/branch."""
        if not self.mcp_client:
            return None
        if self.service == "gitlab":
            result = await self.mcp_client.get_commit_info(self.project_path, "", ref)
        else:
            result = await self.mcp_client.get_commit_info(
                self.repo_owner, self.repo_name, ref
            )
        if isinstance(result, dict) or result is None:
            return result
        return None

    async def get_commit_files(self, *args) -> list[dict[str, Any]]:
        """Get files changed in a specific commit. Accepts either (project_id, commit_sha) for GitLab or (repo_owner, repo_name, commit_sha) for GitHub."""
        if not self.mcp_client:
            return []
        if self.service == "gitlab":
            if len(args) != 2:
                raise ValueError("Expected (project_id, commit_sha) for GitLab")
            project_id, commit_sha = args
            result = await self.mcp_client.get_commit_files(project_id, commit_sha)
        else:
            if len(args) != 3:
                raise ValueError(
                    "Expected (repo_owner, repo_name, commit_sha) for GitHub"
                )
            repo_owner, repo_name, commit_sha = args
            result = await self.mcp_client.get_commit_files(
                repo_owner, repo_name, commit_sha
            )
        if not isinstance(result, list):
            return []
        return [f for f in result if isinstance(f, dict)]

    async def analyze_commit_for_packaging_changes(
        self, commit: dict[str, Any]
    ) -> CommitSummary | None:
        """
        Analyze a commit for packaging-related changes.

        Args:
            commit: Commit data from GitHub or GitLab API

        Returns:
            CommitSummary if packaging changes found, None otherwise
        """
        commit_sha = commit.get("sha") or commit.get("id")
        if not commit_sha:
            raise ValueError("Commit object missing both 'sha' and 'id' keys")

        # Extract commit metadata for GitHub and GitLab
        if "commit" in commit:  # GitHub
            commit_title = commit["commit"]["message"].split("\n")[0]
            author = commit["commit"]["author"]["name"]
            date = commit["commit"]["author"]["date"]
            url = commit.get("html_url", "")
        else:  # GitLab
            commit_title = commit.get("title", commit.get("message", "")).split("\n")[0]
            author = commit.get("author_name", "")
            date = commit.get("authored_date", "")
            url = commit.get("web_url", "")

        if self.service == "gitlab":
            if self.project_path is None:
                raise ValueError("project_path is None for GitLab repository")
            # Get the commit info and diffs (as MCP returns them)
            commit_info = commit  # This is a dict from MCP, may contain 'diffs'
            diffs = commit_info.get("diffs")
            if diffs is None:
                # fallback: try to fetch diffs via get_commit_files
                diffs = await self.get_commit_files(self.project_path, commit_sha)
            packaging_changes = []
            for diff in diffs:
                # Check both old_path and new_path
                for file_path in [diff.get("old_path", ""), diff.get("new_path", "")]:
                    if file_path and self.is_patched(file_path):
                        change = PackagingChange(
                            file_path=file_path,
                            change_type=(
                                "added"
                                if diff.get("new_file")
                                else "removed"
                                if diff.get("deleted_file")
                                else "renamed"
                                if diff.get("renamed_file")
                                else "modified"
                            ),
                            additions=0,  # Not available in diff, could be parsed from diff text if needed
                            deletions=0,  # Not available in diff, could be parsed from diff text if needed
                            patch=diff.get("diff", ""),
                        )
                        packaging_changes.append(change)
                        break  # Only add once per diff
            if packaging_changes:
                return CommitSummary(
                    sha=commit_sha,
                    title=commit_title,
                    author=author,
                    url=url,
                    date=date,
                    packaging_changes=packaging_changes,
                )
            return None
        else:
            files = await self.get_commit_files(
                self.repo_owner, self.repo_name, commit_sha
            )
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
                    author=author,
                    url=url,
                    date=date,
                    packaging_changes=packaging_changes,
                )
            return None

    def generate_ai_summary(self, commit_summary: CommitSummary) -> str:
        """Generate AI summary for a commit with packaging changes."""
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

        return self.llm_client.generate_commit_summary(context)

    async def check_patch_application(self, ref: str = "main") -> bool:
        """
        Check if patches can be applied to the repository at the specified ref.

        Args:
            ref: The git reference to check patches against

        Returns:
            True if all patches apply successfully, False otherwise
        """
        if self.service == "gitlab":
            project_path = self.project_path or ""
            return await self.patch_manager.check_patch_application(
                self.service, project_path, "", ref, self.llm_client
            )
        else:
            return await self.patch_manager.check_patch_application(
                self.service, self.repo_owner, self.repo_name, ref, self.llm_client
            )

    async def analyze_repository(
        self, from_tag: str | None = None, to_tag: str = "main"
    ) -> list[CommitSummary]:
        """
        Analyze repository for packaging changes between two references.

        Args:
            from_tag: Starting reference (if None, will be determined automatically)
            to_tag: Ending reference

        Returns:
            List of commit summaries with packaging changes
        """
        print(f"Starting analysis of {self.repo_owner}/{self.repo_name}")

        # Determine the from_tag if not provided
        if not from_tag:
            from_tag = await self._determine_from_tag(to_tag)

        print(f"Comparing commits from {from_tag} to {to_tag}")

        # Get commits between the two references
        commits = await self.get_commits_between_refs(from_tag, to_tag)

        # Analyze each commit for packaging changes
        packaging_commits = []

        # Print simple message with commit count
        if commits:
            print(f"Analyzing {len(commits)} commits")

        for commit in commits:
            commit_summary = await self.analyze_commit_for_packaging_changes(commit)
            if commit_summary:
                packaging_commits.append(commit_summary)

        self._print_analysis_summary(packaging_commits)

        # Generate AI summaries for all commits
        for commit_summary in packaging_commits:
            commit_summary.ai_summary = self.generate_ai_summary(commit_summary)

        return packaging_commits

    async def _determine_from_tag(self, to_tag: str) -> str:
        """Determine the from_tag automatically based on to_tag."""
        if to_tag != "main":
            from_tag = await self.get_previous_tag(to_tag)
            if from_tag:
                print(f"Using previous tag as from_tag: {from_tag}")
                return from_tag
            else:
                print(
                    f"Warning: Could not find a tag before '{to_tag}'. Using latest tag as fallback."
                )
                from_tag = await self.get_latest_tag()
                if not from_tag:
                    print(WARNING_MESSAGES["NO_TAGS_FOUND"])
                    return "HEAD~10"
                else:
                    print(f"Using latest tag as from_tag: {from_tag}")
                    return from_tag
        else:
            # For 'main' or default case, use latest tag as before
            from_tag = await self.get_latest_tag()
            if not from_tag:
                print(WARNING_MESSAGES["NO_TAGS_FOUND"])
                return "HEAD~10"
            else:
                print(f"Using latest tag as from_tag: {from_tag}")
                return from_tag

    def _print_analysis_summary(self, packaging_commits: list[CommitSummary]) -> None:
        """Print summary of analysis results."""
        if self.patches_dir:
            print(
                f"Found {len(packaging_commits)} commits touching files from patches directory"
            )
            if self.patch_manager.patch_file_paths:
                print("Monitored files:")
                for file_path in sorted(self.patch_manager.patch_file_paths):
                    print(f"  - {file_path}")
        else:
            print(f"Found {len(packaging_commits)} commits with packaging changes")

    def print_results(self, results: list[CommitSummary]) -> None:
        """
        Print analysis results in a formatted way.

        Args:
            results: List of commit summaries to print
        """
        # Show information about file patterns being used
        if self.patches_dir:
            print(f"Using custom file paths from patches directory: {self.patches_dir}")
            print(
                f"Monitoring {len(self.patch_manager.patch_file_paths)} specific file paths"
            )
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
