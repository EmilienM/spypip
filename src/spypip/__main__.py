#!/usr/bin/env python3
"""
SpyPip - Python Packaging PR Analyzer

Entry point for running SpyPip as a module.
"""

import asyncio
import os
import sys

from .analyzer import PackagingPRAnalyzer


async def async_main():
    if len(sys.argv) < 2:
        print("Usage: python -m spypip <owner>/<repo>")
        print("Example: python -m spypip vllm-project/vllm")
        sys.exit(1)

    repo_arg = sys.argv[1]
    if "/" not in repo_arg:
        print("Error: Repository must be in format 'owner/repo'")
        print("Example: python -m spypip vllm-project/vllm")
        sys.exit(1)

    repo_owner, repo_name = repo_arg.split("/", 1)

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)

    github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not github_token:
        print("Error: GITHUB_PERSONAL_ACCESS_TOKEN environment variable not set")
        print(
            "This is required for the GitHub MCP server to authenticate with GitHub API"
        )
        sys.exit(1)

    # Run the analysis
    async with PackagingPRAnalyzer(repo_owner, repo_name, openai_api_key) as analyzer:
        results = await analyzer.analyze_repository()
        analyzer.print_results(results)


def main():
    """Synchronous entry point for the spypip command."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
