#!/usr/bin/env python3
"""
SpyPip - Python Packaging PR Analyzer

Entry point for running SpyPip as a module.
"""

import asyncio
import sys

from .analyzer import PackagingPRAnalyzer
from .config import load_environment_variables, get_required_env_var


async def async_main():
    # Load environment variables from .env file if it exists
    load_environment_variables()

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

    # Get required environment variables
    openai_api_key = get_required_env_var("OPENAI_API_KEY")
    # Ensure GitHub token is available (used by the analyzer internally)
    get_required_env_var(
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "This is required for the GitHub MCP server to authenticate with GitHub API",
    )

    # Run the analysis
    async with PackagingPRAnalyzer(repo_owner, repo_name, openai_api_key) as analyzer:
        results = await analyzer.analyze_repository()
        analyzer.print_results(results)


def main():
    """Synchronous entry point for the spypip command."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
