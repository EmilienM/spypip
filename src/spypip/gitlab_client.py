"""
GitLab client module for MCP operations.
"""

import json
import os
from typing import Any, cast

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .constants import ENV_VARS
from .exceptions import MCPError


class GitLabMCPClient:
    """GitLab MCP client for repository operations."""

    def __init__(self, json_output: bool = False):
        self.json_output = json_output
        self.mcp_client: Any | None = None
        self.mcp_session: ClientSession | None = None

    async def __aenter__(self) -> "GitLabMCPClient":
        """Initialize MCP client and session."""
        gitlab_token = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN")
        if not gitlab_token:
            raise MCPError("GitLab token not found in environment variables")

        # Create server parameters with different logging settings for JSON mode
        env_vars = {**os.environ, "GITLAB_PERSONAL_ACCESS_TOKEN": gitlab_token}

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
            command = "npx"
            args = ["-y", "@zereight/mcp-gitlab"]
        else:  # Windows
            command = "npx.cmd"
            args = ["-y", "@zereight/mcp-gitlab"]

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

    async def get_latest_tag(self, project_id: str) -> str | None:
        """Get the latest tag from the repository."""
        if not self.mcp_session:
            raise MCPError("MCP session not initialized")

        try:
            result = await self.mcp_session.call_tool(
                "list_tags",
                {
                    "project_id": project_id,
                    "per_page": 1,
                    "page": 1,
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                text = getattr(first_content, "text", None)
                if text:
                    data = json.loads(text)
                    if isinstance(data, list) and len(data) > 0:
                        return str(data[0]["name"])
            return None

        except Exception as e:
            raise MCPError(f"Error fetching latest tag: {e}") from e

    async def get_previous_tag(self, project_id: str, to_tag: str) -> str | None:
        """Get the tag that comes before the specified tag in chronological order."""
        if not self.mcp_session:
            raise MCPError("MCP session not initialized")

        try:
            result = await self.mcp_session.call_tool(
                "list_tags",
                {
                    "project_id": project_id,
                    "per_page": 100,
                    "page": 1,
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                text = getattr(first_content, "text", None)
                if text:
                    data = json.loads(text)
                    if isinstance(data, list) and len(data) > 0:
                        tags = [str(tag["name"]) for tag in data]
                        try:
                            to_tag_index = tags.index(to_tag)
                            if to_tag_index + 1 < len(tags):
                                return tags[to_tag_index + 1]
                        except ValueError:
                            if not self.json_output:
                                print(
                                    f"Warning: Tag '{to_tag}' not found in the first {len(tags)} tags"
                                )
            return None

        except Exception as e:
            raise MCPError(f"Error fetching previous tag for {to_tag}: {e}") from e

    async def get_commits_between_refs(
        self,
        project_id: str,
        from_ref: str,
        to_ref: str,
        max_commits: int = 50,
    ) -> list[dict[str, Any]]:
        """Get commits between two references (tags/branches)."""
        if not self.mcp_session:
            raise MCPError("MCP session not initialized")

        try:
            from_commit = await self.get_commit_info(project_id, from_ref)
            from_sha = from_commit["id"] if from_commit else None

            all_commits: list[dict[str, Any]] = []
            page = 1
            per_page = 100

            while len(all_commits) < max_commits:
                result = await self.mcp_session.call_tool(
                    "list_commits",
                    {
                        "project_id": project_id,
                        "ref_name": to_ref,
                        "per_page": per_page,
                        "page": page,
                    },
                )

                if not (hasattr(result, "content") and result.content):
                    break

                first_content = result.content[0]
                text = getattr(first_content, "text", None)
                if not text:
                    break

                data = json.loads(text)
                if not isinstance(data, list) or len(data) == 0:
                    break

                page_commits = cast(list[dict[str, Any]], data)

                found_from_ref = False
                for commit in page_commits:
                    if from_sha and commit["id"] == from_sha:
                        found_from_ref = True
                        break
                    all_commits.append(commit)
                    if len(all_commits) >= max_commits:
                        break

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

    async def get_commit_info(self, project_id: str, ref: str) -> dict[str, Any] | None:
        """Get information about a specific commit/tag/branch."""
        if not self.mcp_session:
            raise MCPError("MCP session not initialized")

        try:
            result = await self.mcp_session.call_tool(
                "get_commit",
                {
                    "project_id": project_id,
                    "sha": ref,
                    "stats": False,
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                text = getattr(first_content, "text", None)
                if text:
                    data = json.loads(text)
                    return cast(dict[str, Any], data)
            return None

        except Exception as e:
            raise MCPError(f"Error fetching commit info for {ref}: {e}") from e

    async def get_commit_files(
        self, project_id: str, commit_sha: str
    ) -> list[dict[str, Any]]:
        """Get files changed in a specific commit."""
        if not self.mcp_session:
            raise MCPError("MCP session not initialized")

        try:
            result = await self.mcp_session.call_tool(
                "get_commit_diff",
                {
                    "project_id": project_id,
                    "sha": commit_sha,
                },
            )

            if hasattr(result, "content") and result.content:
                first_content = result.content[0]
                text = getattr(first_content, "text", None)
                if text:
                    data = json.loads(text)
                    if isinstance(data, list):
                        return data
            return []

        except Exception as e:
            raise MCPError(f"Error fetching files for commit {commit_sha}: {e}") from e
