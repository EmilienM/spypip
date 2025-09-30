# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SpyPip is a Python CLI tool that analyzes GitHub and GitLab repositories to identify and summarize packaging-related changes between Git tags/versions using AI-powered analysis. It uses async/await patterns, MCP (Model Context Protocol) for Git platform APIs, and OpenAI for generating intelligent summaries of dependency changes.

## Common Development Commands

### Testing
```bash
# Run all tests with tox (recommended - tests Python 3.11, 3.12, 3.13)
tox

# Run specific test environments
tox -e py313                    # Test with Python 3.13
tox -e tests                    # Run with coverage
tox -e linter                   # Run linting (Ruff)
tox -e mypy                     # Type checking
tox -e fix                      # Auto-fix code formatting (Black + Ruff)

# Direct pytest for faster iteration
pytest tests/                   # Run all tests
pytest tests/test_basic.py      # Run single test file
pytest tests/ --cov=spypip --cov-report=term-missing  # With coverage report
```

### Development Setup
```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Install github-mcp-server dependency
./scripts/install-github-mcp-server.sh

# Set up environment (copy .env.example to .env and configure)
cp .env.example .env
```

### Running the Application
```bash
# Run via module (preferred)
python -m spypip <repository-url>

# Or via installed command
spypip <repository-url>
```

### Container Development
```bash
# Build container
podman build -t spypip .

# Run container
podman run --rm -e OPENAI_API_KEY=$OPENAI_API_KEY spypip <repository-url>
```

## Architecture Overview

### Core Components

**Modular Client-Service Architecture** with clear separation of concerns:

1. **CLI Layer** (`src/spypip/__main__.py`)
   - Entry point with argparse-based command parsing
   - Environment variable loading and validation
   - Async coordination of main workflow

2. **Analysis Orchestration** (`src/spypip/analyzer.py`)
   - `PackagingVersionAnalyzer`: Main orchestrator class
   - Coordinates between MCP clients, LLM services, and patch operations
   - Uses async context manager pattern for resource lifecycle

3. **Client Layer** (async context managers for external APIs)
   - `GitHubMCPClient` (`github_client.py`): GitHub API via MCP
   - `GitLabMCPClient` (`gitlab_client.py`): GitLab API via MCP
   - `LLMClient` (`llm_client.py`): OpenAI API integration

4. **Operations Layer**
   - `PatchManager` (`patch_operations.py`): Handles .patch/.diff/.txt files
   - Supports AI-powered patch regeneration when patches fail to apply
   - Validates patch application without full analysis

5. **Data Models** (`src/spypip/models.py`)
   - `PackagingChange`: File changes with metadata
   - `CommitSummary`: Commits containing packaging changes
   - `PatchFailure`: Failed patch information
   - All use dataclasses for clean, typed structures

### Key Patterns

- **Async Context Managers**: All external resources (MCP sessions, API clients)
- **Dependency Injection**: Clients passed to analyzer for testability
- **Strategy Pattern**: Pluggable MCP clients (GitHub/GitLab) with common interface
- **Error Hierarchy**: Custom exceptions extending `SpyPipError` (`exceptions.py`)

### File Detection Logic

SpyPip identifies packaging-related files using 19 default patterns defined in `constants.py`:
- Python packaging: `requirements*.txt`, `pyproject.toml`, `setup.py`, `Pipfile*`
- Containers: `Dockerfile*`, `Containerfile*`, `docker-compose*.yml`
- CI/CD: `.github/workflows/*.yml`, `tox.ini`, various config files
- Custom overrides: `.patch`, `.diff`, `.txt` files in repository root

## Configuration and Environment

### Required Environment Variables
```bash
OPENAI_API_KEY=your_openai_key           # For AI summary generation
GITHUB_PERSONAL_ACCESS_TOKEN=your_token  # GitHub API access
```

### Optional Environment Variables
```bash
GITLAB_PERSONAL_ACCESS_TOKEN=your_token  # For GitLab repositories
GITLAB_USERNAME=your_username            # For GitLab patch testing
OPENAI_ENDPOINT_URL=custom_endpoint      # Default: GitHub AI models
MODEL_NAME=model_name                    # Default: openai/gpt-4.1
```

### Configuration Loading
- Environment loaded via `config.py` using python-dotenv
- Searches for `.env` files in: current directory, parent directory, home directory
- Supports both direct environment variables and .env file configuration

## Testing Architecture

### Test Organization (9 test files)
- `test_basic.py`: Core functionality, version detection, data models
- `test_config.py`: Environment variable loading and validation
- `test_patches.py` / `test_patch_removals.py`: Patch file operations
- `test_llm_patch_regeneration.py`: AI-powered patch regeneration
- `test_reasoning_models.py`: Advanced LLM model support (thinking steps)
- `test_tag_logic.py` / `test_max_commits.py`: Core analysis logic

### Test Dependencies
- **pytest** with **pytest-asyncio** for async test support
- **pytest-cov** for coverage reporting
- Tests require MCP server binary (installed via setup script)

### Running Single Tests
```bash
# Test specific functionality
pytest tests/test_basic.py::test_version_detection -v
pytest tests/test_patches.py::test_patch_application -v
pytest tests/test_llm_patch_regeneration.py -v -s  # AI tests with output
```

## Build System and Tooling

### Modern Python Packaging
- **Build Backend**: Hatchling (defined in `pyproject.toml`)
- **Version Management**: Dynamic from `src/spypip/__init__.py`
- **Entry Point**: `spypip` command maps to `spypip.__main__:main`

### Code Quality Tools
- **Ruff**: All-in-one linter (replaces flake8, isort, pyupgrade)
  - Line length: 88 characters
  - Target: Python 3.12
  - Rules: pycodestyle, pyflakes, isort, flake8-bugbear, comprehensions
- **Black**: Code formatter (88 char line length)
- **Mypy**: Type checking (configured for Python 3.11+)
- **Pre-commit**: Git hooks for code quality enforcement

### Supported Python Versions
- **Minimum**: Python 3.11
- **Tested**: 3.11, 3.12, 3.13 (in CI matrix)
- **Target**: Python 3.12 for linting rules

## Container and Deployment

### Container Configuration (`Containerfile`)
- **Base Image**: UBI9 Python 3.12 (Red Hat Universal Base Image)
- **Dependencies**: git, nodejs, npm, github-mcp-server binary
- **Entry Point**: `python -m spypip`
- **Published**: `quay.io/emilien/spypip:latest`

### GitHub Actions CI (`.github/workflows/test.yml`)
- **Triggers**: Push to main/master, pull requests
- **Matrix**: Python 3.11, 3.12, 3.13
- **Integration**: Uses tox-gh-actions for environment mapping

## Key Features and Capabilities

1. **Smart Change Detection**: Identifies packaging changes across 19 file patterns
2. **Version Comparison**: Compare between tags, commits, or latest tag to main branch
3. **AI-Powered Summaries**: LLM analysis of dependency and configuration changes
4. **Custom Patch Monitoring**: Override defaults with repository-specific .patch/.diff/.txt files
5. **Patch Validation**: Test patch application separately from full analysis
6. **AI Patch Regeneration**: Automatically regenerate failed patches using LLM context
7. **Multi-Platform Support**: GitHub and GitLab via MCP protocol
8. **Reasoning Model Support**: Compatible with LLMs that include thinking/reasoning steps
9. **JSON Output**: Machine-readable output for CI/CD pipeline integration
10. **Cross-Repository Analysis**: Works with any public GitHub/GitLab repository

## Development Notes

- **Async-First Design**: All external operations use async/await patterns
- **Type Safety**: Full type annotations with `py.typed` marker
- **Error Handling**: Comprehensive custom exception hierarchy
- **Resource Management**: Proper cleanup via async context managers
- **Modular Design**: Clear boundaries between networking, AI, and business logic layers
- **Testing**: Comprehensive test coverage including async operations and AI integration