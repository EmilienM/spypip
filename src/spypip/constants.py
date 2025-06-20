"""
Constants and configuration values for SpyPip.
"""

# Default packaging file patterns
DEFAULT_PACKAGING_PATTERNS: list[str] = [
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

# Default values for configuration
DEFAULT_MAX_COMMITS = 50
DEFAULT_PAGINATION_SIZE = 100
DEFAULT_TAGS_LIMIT = 100
DEFAULT_MAX_TOKENS = 500
DEFAULT_TEMPERATURE = 0.1
DEFAULT_CLONE_TIMEOUT = 1800  # 30 minutes

# Patch file extensions
PATCH_EXTENSIONS = {".patch", ".diff", ".txt"}

# Git diff extensions for regeneration
SUPPORTED_FILE_EXTENSIONS = (
    ".txt",
    ".py",
    ".c",
    ".cpp",
    ".h",
    ".cmake",
    ".toml",
    ".cfg",
    ".yml",
    ".yaml",
)

# OpenAI model configuration
DEFAULT_OPENAI_ENDPOINT = "https://models.github.ai/inference"
DEFAULT_MODEL_NAME = "openai/gpt-4.1"

# Environment variable names
ENV_VARS = {
    "OPENAI_API_KEY": "OPENAI_API_KEY",
    "GITHUB_TOKEN": "GITHUB_PERSONAL_ACCESS_TOKEN",
    "OPENAI_ENDPOINT": "OPENAI_ENDPOINT_URL",
    "MODEL_NAME": "MODEL_NAME",
    "MCP_LOG_LEVEL": "MCP_LOG_LEVEL",
    "RUST_LOG": "RUST_LOG",
}

# Error messages
ERROR_MESSAGES = {
    "NO_PATCHES_DIR": "No patches directory specified",
    "PATCHES_DIR_NOT_EXIST": "Patches directory '{path}' does not exist or is not a directory",
    "REPO_FORMAT_ERROR": "Repository must be in format 'owner/repo'",
    "CLONE_TIMEOUT": "Repository clone timed out",
    "NO_MCP_SESSION": "MCP session is not available",
}

# Success messages
SUCCESS_MESSAGES = {
    "ALL_PATCHES_APPLIED": "✓ ALL PATCHES CAN BE APPLIED SUCCESSFULLY",
    "PATCH_APPLIED": "✓ Patch {name} can be applied successfully",
    "PATCH_REGENERATED": "✓ Successfully regenerated patch for {name}",
    "REPO_CLONED": "Successfully cloned repository",
}

# Warning messages
WARNING_MESSAGES = {
    "SOME_PATCHES_FAILED": "✗ SOME PATCHES FAILED TO APPLY",
    "PATCH_FAILED": "✗ Patch {name} FAILED to apply",
    "NO_TAGS_FOUND": "No tags found in repository. Using 'HEAD~10' as fallback.",
    "TAG_NOT_FOUND": "Tag '{tag}' not found in the first {count} tags",
    "PATCHES_DIR_NOT_FOUND": "Patches directory '{path}' does not exist. Using default patterns.",
    "NO_FILE_PATHS": "No file paths found in patch files. Using default patterns.",
}
