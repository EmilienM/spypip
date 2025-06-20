#!/usr/bin/env python3
"""
SpyPip - Python Packaging PR Analyzer

Entry point for running SpyPip as a module.
"""

import argparse
import asyncio
import sys

from .analyzer import PackagingVersionAnalyzer
from .config import get_required_env_var, load_environment_variables
from .utils import validate_repository_format


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
  python -m spypip vllm-project/vllm --max-commits 100
  python -m spypip vllm-project/vllm --patches-dir ./patches
  python -m spypip vllm-project/vllm --patches-dir ./patches --check-patch-apply-only
  python -m spypip vllm-project/vllm --patches-dir ./patches --check-patch-apply-only --json-output
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

    parser.add_argument(
        "--check-patch-apply-only",
        action="store_true",
        help="Only check if patches can be applied. Requires --patches-dir. Checkouts the repository in a temporary location and tests patch application without running the full analysis.",
    )

    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Output patch failures in JSON format suitable for creating Jira tickets. Only used with --check-patch-apply-only.",
    )

    parser.add_argument(
        "--max-commits",
        type=int,
        default=50,
        help="Maximum number of commits to inspect when analyzing PRs. Default is 50.",
    )

    args = parser.parse_args()

    # Validate that --check-patch-apply-only requires --patches-dir
    if args.check_patch_apply_only and not args.patches_dir:
        parser.error("--check-patch-apply-only requires --patches-dir to be specified")

    # Validate that --json-output requires --check-patch-apply-only
    if args.json_output and not args.check_patch_apply_only:
        parser.error("--json-output requires --check-patch-apply-only to be specified")

    # Validate that --max-commits is positive
    if args.max_commits <= 0:
        parser.error("--max-commits must be a positive integer")

    return args


async def async_main():
    # Load environment variables from .env file if it exists
    load_environment_variables()

    args = parse_arguments()

    # Parse repository argument
    try:
        repo_owner, repo_name = validate_repository_format(args.repository)
    except ValueError as e:
        print(f"Error: {e}")
        print("Example: python -m spypip vllm-project/vllm")
        sys.exit(1)

    # Get required environment variables
    openai_api_key = get_required_env_var("OPENAI_API_KEY")
    # Ensure GitHub token is available (used by the analyzer internally)
    get_required_env_var(
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "This is required for the GitHub MCP server to authenticate with GitHub API",
    )

    # Run the analysis or patch check
    success = True
    try:
        async with PackagingVersionAnalyzer(
            args.repository,
            openai_api_key,
            patches_dir=args.patches_dir,
            json_output=args.json_output,
            max_commits=args.max_commits,
        ) as analyzer:
            if args.check_patch_apply_only:
                # Only check patch application
                success = await analyzer.check_patch_application(args.to_tag)
            else:
                # Run full analysis
                results = await analyzer.analyze_repository(
                    from_tag=args.from_tag, to_tag=args.to_tag
                )
                analyzer.print_results(results)
    except Exception as e:
        print(f"Error during analysis: {e}")
        success = False

    # Exit with error code after the context manager is properly closed
    if args.check_patch_apply_only and not success:
        sys.exit(1)


def main():
    """Synchronous entry point for the spypip command."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
