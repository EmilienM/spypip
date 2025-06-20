"""
GitHub client module for MCP operations.
"""

import json
import os
from typing import Any, cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .constants import ENV_VARS
from .exceptions import MCPError


class GitHubMCPClient:
    """GitHub MCP client for repository operations."""

    def __init__(self, json_output: bool = False):
        self.json_output = json_output
        self.mcp_client: Any | None = None
        self.mcp_session: ClientSession | None = None

    async def __aenter__(self) -> "GitHubMCPClient":
        """Initialize MCP client and session."""
        github_token = os.getenv(ENV_VARS["GITHUB_TOKEN"])
        if not github_token:
            raise MCPError("GitHub token not found in environment variables")

        # Create server parameters with different logging settings for JSON mode
        env_vars = {**os.environ, ENV_VARS["GITHUB_TOKEN"]: github_token}

        # Try to suppress MCP server logging when in JSON mode
        if self.json_output:
            env_vars.update(
                {
                    ENV_VARS["MCP_LOG_LEVEL"]: "ERROR",
                    ENV_VARS["RUST_LOG"]: "error",
                }
            )

        # Always suppress MCP server startup messages by wrapping the command
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

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Clean up MCP client and session."""
        # Close MCP session
        if self.mcp_session:
            try:
                await self.mcp_session.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                if not self.json_output:
                    print(f"Warning: Error closing MCP session: {e}")

        # Close MCP client
        if self.mcp_client:
            try:
                await self.mcp_client.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                if not self.json_output:
                    print(f"Warning: Error closing MCP client: {e}")

        # Don't suppress any original exceptions
        return False

    async def get_latest_tag(self, owner: str, repo: str) -> str | None:
        """Get the latest tag from the repository."""
        if not self.mcp_session:
            raise MCPError("MCP session not initialized")

        try:
            result = await self.mcp_session.call_tool(
                "list_tags",
                {
                    "owner": owner,
                    "repo": repo,
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
            raise MCPError(f"Error fetching latest tag: {e}") from e

    async def get_previous_tag(self, owner: str, repo: str, to_tag: str) -> str | None:
        """Get the tag that comes before the specified tag in chronological order."""
        if not self.mcp_session:
            raise MCPError("MCP session not initialized")

        try:
            # Get all tags with a reasonable limit
            result = await self.mcp_session.call_tool(
                "list_tags",
                {
                    "owner": owner,
                    "repo": repo,
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
                            if not self.json_output:
                                print(
                                    f"Warning: Tag '{to_tag}' not found in the first {len(tags)} tags"
                                )
            return None

        except Exception as e:
            raise MCPError(f"Error fetching previous tag for {to_tag}: {e}") from e

    async def get_commits_between_refs(
        self, owner: str, repo: str, from_ref: str, to_ref: str, max_commits: int = 50
    ) -> list[dict[str, Any]]:
        """Get commits between two references (tags/branches)."""
        if not self.mcp_session:
            raise MCPError("MCP session not initialized")

        try:
            # Get the commit SHA for from_ref to know where to stop
            from_commit = await self.get_commit_info(owner, repo, from_ref)
            from_sha = from_commit["sha"] if from_commit else None

            all_commits: list[dict[str, Any]] = []
            page = 1
            per_page = 100

            while len(all_commits) < max_commits:
                # Get commits from the to_ref branch with pagination
                result = await self.mcp_session.call_tool(
                    "list_commits",
                    {
                        "owner": owner,
                        "repo": repo,
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

                page_commits = cast(list[dict[str, Any]], data)

                # Filter commits to only include those after from_ref
                found_from_ref = False
                for commit in page_commits:
                    if from_sha and commit["sha"] == from_sha:
                        found_from_ref = True
                        break
                    all_commits.append(commit)
                    # Check if we've reached the max commits limit
                    if len(all_commits) >= max_commits:
                        break

                # If we found the from_ref commit or got less than per_page commits, we're done
                # Also break if we've reached the max commits limit
                if (
                    found_from_ref
                    or len(page_commits) < per_page
                    or len(all_commits) >= max_commits
                ):
                    break

                page += 1

            return all_commits

        except Exception as e:
            raise MCPError(f"Error fetching commits: {e}") from e

    async def get_commit_info(
        self, owner: str, repo: str, ref: str
    ) -> dict[str, Any] | None:
        """Get information about a specific commit/tag/branch."""
        if not self.mcp_session:
            raise MCPError("MCP session not initialized")

        try:
            result = await self.mcp_session.call_tool(
                "get_commit",
                {
                    "owner": owner,
                    "repo": repo,
                    "sha": ref,
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                if hasattr(first_content, "text"):
                    data = json.loads(first_content.text)
                    return cast(dict[str, Any], data)
            return None

        except Exception as e:
            raise MCPError(f"Error fetching commit info for {ref}: {e}") from e

    async def get_commit_files(
        self, owner: str, repo: str, commit_sha: str
    ) -> list[dict[str, Any]]:
        """Get files changed in a specific commit."""
        if not self.mcp_session:
            raise MCPError("MCP session not initialized")

        try:
            result = await self.mcp_session.call_tool(
                "get_commit",
                {
                    "owner": owner,
                    "repo": repo,
                    "sha": commit_sha,
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                if hasattr(first_content, "text"):
                    data = json.loads(first_content.text)
                    files = data.get("files", [])
                    return (
                        cast(list[dict[str, Any]], files)
                        if isinstance(files, list)
                        else []
                    )
            return []

        except Exception as e:
            raise MCPError(f"Error fetching files for commit {commit_sha}: {e}") from e
