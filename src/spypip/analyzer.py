#!/usr/bin/env python3
"""
Python Packaging PR Analyzer

This script finds open pull requests that touch Python packaging files
and uses an LLM to summarize packaging-related changes.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, cast

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
class PRSummary:
    number: int
    title: str
    author: str
    url: str
    packaging_changes: List[PackagingChange]
    ai_summary: Optional[str] = None


class PackagingPRAnalyzer:
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

    def __init__(self, repo_owner: str, repo_name: str, openai_api_key: str):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.openai_client = openai.OpenAI(
            api_key=openai_api_key, base_url="https://models.github.ai/inference"
        )
        self.mcp_client: Optional[Any] = None
        self.mcp_session: Optional[ClientSession] = None

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

    def is_packaging_file(self, file_path: str) -> bool:
        for pattern in self.PACKAGING_PATTERNS:
            if re.search(pattern, file_path, re.IGNORECASE):
                return True
        return False

    async def get_open_prs(self) -> List[Dict[str, Any]]:
        print(f"Fetching open PRs for {self.repo_owner}/{self.repo_name}...")

        try:
            if self.mcp_session is None:
                return []
            result = await self.mcp_session.call_tool(
                "list_pull_requests",
                {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "state": "open",
                    "perPage": 100,
                },
            )

            if hasattr(result, "content") and result.content:
                # Type guard to ensure we have text content
                first_content = result.content[0]
                if hasattr(first_content, "text"):
                    data = json.loads(first_content.text)
                    if isinstance(data, list):
                        return cast(List[Dict[str, Any]], data)
                    elif isinstance(data, dict):
                        result_data = data.get("data", data.get("pull_requests", []))
                        return cast(List[Dict[str, Any]], result_data)
            return []

        except Exception as e:
            print(f"Error fetching PRs: {e}")
            return []

    async def get_pr_files(self, pr_number: int) -> List[Dict[str, Any]]:
        try:
            if self.mcp_session is None:
                return []
            result = await self.mcp_session.call_tool(
                "get_pull_request_files",
                {
                    "owner": self.repo_owner,
                    "repo": self.repo_name,
                    "pullNumber": pr_number,
                },
            )

            if hasattr(result, "content") and result.content:
                # Type guard to ensure we have text content
                first_content = result.content[0]
                if hasattr(first_content, "text"):
                    data = json.loads(first_content.text)
                    return (
                        cast(List[Dict[str, Any]], data)
                        if isinstance(data, list)
                        else []
                    )
            return []

        except Exception as e:
            print(f"Error fetching files for PR #{pr_number}: {e}")
            return []

    async def analyze_pr_for_packaging_changes(
        self, pr: Dict[str, Any]
    ) -> Optional[PRSummary]:
        pr_number = pr["number"]
        print(f"Analyzing PR #{pr_number}: {pr['title']}")

        files = await self.get_pr_files(pr_number)
        packaging_changes = []

        for file_info in files:
            file_path = file_info.get("filename", "")

            if self.is_packaging_file(file_path):
                change = PackagingChange(
                    file_path=file_path,
                    change_type=file_info.get("status", "modified"),
                    additions=file_info.get("additions", 0),
                    deletions=file_info.get("deletions", 0),
                    patch=file_info.get("patch", ""),
                )
                packaging_changes.append(change)

        if packaging_changes:
            return PRSummary(
                number=pr_number,
                title=pr["title"],
                author=pr["user"]["login"],
                url=pr["html_url"],
                packaging_changes=packaging_changes,
            )

        return None

    def generate_ai_summary(self, pr_summary: PRSummary) -> str:
        print(f"Generating AI summary for PR #{pr_summary.number}...")

        context = f"""
PR #{pr_summary.number}: {pr_summary.title}
Author: {pr_summary.author}
URL: {pr_summary.url}

Packaging files changed:
"""

        for change in pr_summary.packaging_changes:
            context += f"\n- {change.file_path} ({change.change_type})"
            context += f" +{change.additions} -{change.deletions}"

            if change.patch:
                context += f"\n  Patch preview:\n{change.patch[:500]}..."

        prompt = f"""
Analyze the following pull request that touches Python packaging files.
Provide a concise summary of what packaging-related changes are being made.
Focus on:
- Dependencies being added, removed, or updated
- Build configuration changes
- Containerization changes
- Version constraints modifications
- New packaging tools or methods introduced

Context:
{context}

Please provide a clear, concise summary of the packaging implications of this PR.
"""

        try:
            response = self.openai_client.chat.completions.create(
                model="openai/gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert in Python packaging and dependency management. Analyze pull requests for packaging-related changes.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            return content.strip() if content else "No summary generated"

        except Exception as e:
            print(f"Error generating AI summary: {e}")
            return f"Error generating summary: {str(e)}"

    async def analyze_repository(self) -> List[PRSummary]:
        print(f"Starting analysis of {self.repo_owner}/{self.repo_name}")

        # Get all open PRs
        prs = await self.get_open_prs()
        print(f"Found {len(prs)} open PRs")

        # Analyze each PR for packaging changes
        packaging_prs = []
        for pr in prs:
            pr_summary = await self.analyze_pr_for_packaging_changes(pr)
            if pr_summary:
                packaging_prs.append(pr_summary)

        print(f"Found {len(packaging_prs)} PRs with packaging changes")

        for pr_summary in packaging_prs:
            pr_summary.ai_summary = self.generate_ai_summary(pr_summary)

        return packaging_prs

    def print_results(self, results: List[PRSummary]):
        print("\n" + "=" * 80)
        print("PYTHON PACKAGING PR ANALYSIS RESULTS")
        print("=" * 80)

        if not results:
            print("No open PRs with packaging changes found.")
            return

        for i, pr in enumerate(results, 1):
            print(f"\n{i}. PR #{pr.number}: {pr.title}")
            print(f"   Author: {pr.author}")
            print(f"   URL: {pr.url}")
            print(f"   Files changed ({len(pr.packaging_changes)}):")

            for change in pr.packaging_changes:
                print(
                    f"     - {change.file_path} ({change.change_type}) +{change.additions}/-{change.deletions}"
                )

            print("\n   AI Summary:")
            print(f"   {pr.ai_summary}")
            print("-" * 40)
