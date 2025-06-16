#!/usr/bin/env python3
"""
SpyPip - Python Packaging PR Analyzer

Entry point for running SpyPip as a module.
"""

import argparse
import asyncio
import sys

from .analyzer import PackagingVersionAnalyzer
from .config import load_environment_variables, get_required_env_var


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="SpyPip - Python Packaging Version Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m spypip vllm-project/vllm
  python -m spypip vllm-project/vllm --from-tag v1.0.0 --to-tag v1.1.0
  python -m spypip vllm-project/vllm --from-tag v1.0.0
  python -m spypip vllm-project/vllm --patches-dir ./patches
        """,
    )

    parser.add_argument(
        "repository",
        help="Repository in format 'owner/repo' (e.g., vllm-project/vllm)",
    )

    parser.add_argument(
        "--from-tag",
        type=str,
        help="Starting tag/commit to compare from. If not provided, will use the latest tag.",
    )

    parser.add_argument(
        "--to-tag",
        type=str,
        help="Ending tag/commit to compare to. Defaults to 'main' if not provided.",
        default="main",
    )

    parser.add_argument(
        "--patches-dir",
        type=str,
        help="Path to directory containing patch files. When specified, SpyPip will read these files and override the default list of packaging files to look for commits touching these files.",
    )

    return parser.parse_args()


async def async_main():
    # Load environment variables from .env file if it exists
    load_environment_variables()

    args = parse_arguments()

    # Parse repository argument
    if "/" not in args.repository:
        print("Error: Repository must be in format 'owner/repo'")
        print("Example: python -m spypip vllm-project/vllm")
        sys.exit(1)

    repo_owner, repo_name = args.repository.split("/", 1)

    # Get required environment variables
    openai_api_key = get_required_env_var("OPENAI_API_KEY")
    # Ensure GitHub token is available (used by the analyzer internally)
    get_required_env_var(
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "This is required for the GitHub MCP server to authenticate with GitHub API",
    )

    # Run the analysis
    async with PackagingVersionAnalyzer(
        repo_owner, repo_name, openai_api_key, patches_dir=args.patches_dir
    ) as analyzer:
        results = await analyzer.analyze_repository(
            from_tag=args.from_tag, to_tag=args.to_tag
        )
        analyzer.print_results(results)


def main():
    """Synchronous entry point for the spypip command."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
