"""
LLM client module for AI operations.
"""

import os

import openai

from .constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL_NAME,
    DEFAULT_OPENAI_ENDPOINT,
    DEFAULT_TEMPERATURE,
    ENV_VARS,
)
from .exceptions import LLMError
from .utils import clean_reasoning_response


class LLMClient:
    """Client for LLM operations."""

    def __init__(self, api_key: str):
        """
        Initialize LLM client.

        Args:
            api_key: OpenAI API key
        """
        base_url = os.getenv(ENV_VARS["OPENAI_ENDPOINT"], DEFAULT_OPENAI_ENDPOINT)
        self.model_name = os.getenv(ENV_VARS["MODEL_NAME"], DEFAULT_MODEL_NAME)
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def generate_commit_summary(self, commit_context: str) -> str:
        """
        Generate AI summary for a commit with packaging changes.

        Args:
            commit_context: Context information about the commit

        Returns:
            Generated summary text

        Raises:
            LLMError: If summary generation fails
        """
        prompt = f"""
Analyze the following commit that touches Python packaging files.
Provide a concise summary of what packaging-related changes are being made.
Focus on:
- Dependencies being added, removed, or updated
- Build configuration changes
- Containerization changes
- Version constraints modifications
- New packaging tools or methods introduced

Context:
{commit_context}

Please provide a clear, concise summary of the packaging implications of this commit.
"""

        system_message = """You are an expert Python packaging and dependency management analyst specializing in analyzing GitHub commits for packaging-related changes. Your role is to provide clear, actionable insights about how changes to packaging files impact project dependencies, build processes, and deployment.

Key areas of expertise:
- Python packaging files: requirements.txt, pyproject.toml, setup.py, setup.cfg, poetry.lock, Pipfile
- Build and dependency management: pip, poetry, conda, tox configurations
- Containerization: Dockerfiles, Containerfiles, and container-specific requirements
- Version constraints and dependency resolution conflicts
- Security implications of dependency updates
- Performance and compatibility impacts of package changes

When analyzing commits, focus on:
1. **Dependency Changes**: New packages added, removed, or updated with version implications
2. **Version Constraints**: Changes to version pinning, ranges, or compatibility requirements
3. **Build Configuration**: Modifications to build tools, scripts, or packaging metadata
4. **Environment Management**: Changes to virtual environments, conda environments, or containerization
5. **Security & Compliance**: Dependency vulnerabilities, license changes, or policy violations
6. **Performance Impact**: Dependencies that may affect runtime performance or bundle size
7. **Breaking Changes**: Updates that may introduce compatibility issues or require code changes

Provide concise, technical summaries that help developers understand the packaging implications and potential risks or benefits of the changes made in each commit."""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=DEFAULT_TEMPERATURE,
            )

            content = response.choices[0].message.content
            if content:
                # Handle reasoning models that include reasoning steps
                final_content = clean_reasoning_response(content)
                return final_content.strip()
            else:
                return "No summary generated"

        except Exception as e:
            raise LLMError(f"Error generating AI summary: {e}") from e

    def regenerate_patch(
        self, original_patch: str, current_files_content: dict, ref: str
    ) -> str | None:
        """
        Use LLM to regenerate a patch file when the original fails to apply.

        Args:
            original_patch: Content of the original patch that failed
            current_files_content: Dict mapping file paths to their current content
            ref: Git reference being tested

        Returns:
            The regenerated patch content if successful, None otherwise

        Raises:
            LLMError: If patch regeneration fails
        """
        # Prepare the file context
        files_context = ""
        for file_path, content in current_files_content.items():
            files_context += f"\n--- Current content of {file_path} ---\n{content}\n"

        prompt = f"""You are a patch regeneration expert. A patch file failed to apply to a repository at reference '{ref}'.

Your task is to analyze the original patch and the current file content, then generate a new patch that achieves the same intended changes but applies cleanly to the current codebase.

Original patch that failed:
```
{original_patch}
```

Current file content:{files_context}

IMPORTANT ANALYSIS GUIDELINES:
1. Look at what lines the original patch REMOVED (lines starting with '-') and ensure they are removed from the current content
2. Look at what lines the original patch ADDED (lines starting with '+') and ensure they are added in the appropriate location
3. If a line that should be removed has moved to a different location in the current file, find it and remove it from there
4. If dependencies or content have been reordered, adapt the patch to work with the current structure
5. Maintain the same intent: removals should still be removed, additions should still be added

Please generate a new patch in unified diff format that:
1. Achieves the EXACT SAME INTENT as the original patch (same additions, same removals)
2. Applies cleanly to the current file content by finding the correct locations
3. Uses proper unified diff format with correct line numbers
4. Includes appropriate context lines
5. Can be applied using 'patch -p1' command

Return ONLY the patch content, no explanations or markdown formatting."""

        system_message = """You are an expert patch regeneration system that creates unified diff patches. You understand patch formats and can adapt patches to different codebases while preserving the original intent.

Key principles:
1. PRESERVE INTENT: If the original patch removed a line, the new patch must also remove that line (even if it moved)
2. PRESERVE INTENT: If the original patch added a line, the new patch must also add that line
3. ADAPT LOCATIONS: Find where removed lines are located in the current file and remove them from there
4. ADAPT LOCATIONS: Add new lines in the most appropriate location based on the current file structure
5. HANDLE REORDERING: Account for content that may have been reordered or moved since the original patch

Always generate valid unified diff format patches that can be applied with 'patch -p1' and achieve the exact same end result as the original patch intended."""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=DEFAULT_TEMPERATURE,
            )

            content = response.choices[0].message.content
            if content:
                # Handle reasoning models that include reasoning steps
                regenerated_patch = clean_reasoning_response(content)
                return regenerated_patch.strip()
            return None

        except Exception as e:
            raise LLMError(f"LLM patch regeneration failed: {e}") from e
