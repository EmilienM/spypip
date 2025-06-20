"""Tests for reasoning model response handling."""

import pytest
from spypip.utils import clean_reasoning_response


class TestReasoningModelSupport:
    """Test support for reasoning models that include reasoning steps."""

    def setup_method(self):
        """Set up test utilities."""
        # We're testing the utility function directly
        pass

    def test_extract_final_response_with_thinking_tags(self):
        """Test extraction from content with <thinking> tags."""
        content = """<thinking>
Let me analyze this PR. It seems to be adding a new dependency to requirements.txt.
I need to check if this is a major version change and if there are any security implications.
The patch shows that numpy is being updated from 1.21.0 to 1.24.0, which is a significant update.
</thinking>

This PR updates numpy from version 1.21.0 to 1.24.0 in requirements.txt. This is a significant version bump that may introduce breaking changes and should be tested thoroughly."""

        result = clean_reasoning_response(content)
        expected = "This PR updates numpy from version 1.21.0 to 1.24.0 in requirements.txt. This is a significant version bump that may introduce breaking changes and should be tested thoroughly."
        assert result == expected

    def test_extract_final_response_with_reasoning_tags(self):
        """Test extraction from content with <reasoning> tags."""
        content = """<reasoning>
The changes show modifications to pyproject.toml. Let me examine what's being changed:
1. New dependency added: requests>=2.28.0
2. Development dependency updated: pytest from 7.0.0 to 7.4.0
3. Build configuration changes in [build-system]

This affects both runtime and development environments.
</reasoning>

This PR introduces several packaging changes:
- Adds requests>=2.28.0 as a new runtime dependency
- Updates pytest from 7.0.0 to 7.4.0 in dev dependencies
- Modifies build system configuration in pyproject.toml"""

        result = clean_reasoning_response(content)
        expected = """This PR introduces several packaging changes:
- Adds requests>=2.28.0 as a new runtime dependency
- Updates pytest from 7.0.0 to 7.4.0 in dev dependencies
- Modifies build system configuration in pyproject.toml"""
        assert result == expected

    def test_extract_final_response_with_multiple_reasoning_blocks(self):
        """Test extraction from content with multiple reasoning blocks."""
        content = """<thinking>
First, let me understand what files are being changed.
</thinking>

<analysis>
The PR touches requirements.txt and Dockerfile, indicating both dependency and containerization changes.
</analysis>

The PR updates Docker base image and adds new Python dependencies for enhanced security features."""

        result = clean_reasoning_response(content)
        expected = "The PR updates Docker base image and adds new Python dependencies for enhanced security features."
        assert result == expected

    def test_extract_final_response_without_reasoning_tags(self):
        """Test that content without reasoning tags is returned unchanged."""
        content = "This is a straightforward dependency update that adds Flask 2.3.0 to the requirements."
        result = clean_reasoning_response(content)
        assert result == content

    def test_extract_final_response_with_case_insensitive_tags(self):
        """Test extraction with case-insensitive reasoning tags."""
        content = """<THINKING>
Let me analyze this carefully.
</THINKING>

<Analysis>
This looks like a security update.
</Analysis>

Critical security update: bumps cryptography from 3.4.8 to 41.0.4 to address CVE-2023-38325."""

        result = clean_reasoning_response(content)
        expected = "Critical security update: bumps cryptography from 3.4.8 to 41.0.4 to address CVE-2023-38325."
        assert result == expected

    def test_extract_final_response_empty_content(self):
        """Test handling of empty content."""
        assert clean_reasoning_response("") == ""
        assert clean_reasoning_response(None) is None

    def test_extract_final_response_only_reasoning_content(self):
        """Test handling when content contains only reasoning with no final answer."""
        content = """<thinking>
This is just internal reasoning with no actual response.
The user probably expects some analysis but there's no clear answer here.
</thinking>"""

        # Should return original content when cleaned result is too short
        result = clean_reasoning_response(content)
        assert result == content

    def test_extract_final_response_with_various_tags(self):
        """Test extraction with various reasoning tag formats."""
        content = """<internal_thought>
Processing the request...
</internal_thought>

<think>
What are the implications?
</think>

<reason>
This affects build processes.
</reason>

The PR modifies tox.ini to add Python 3.11 support and updates testing configurations."""

        result = clean_reasoning_response(content)
        expected = "The PR modifies tox.ini to add Python 3.11 support and updates testing configurations."
        assert result == expected

    def test_extract_final_response_preserves_formatting(self):
        """Test that final response formatting is preserved."""
        content = """<thinking>
Let me structure this analysis properly.
</thinking>

## Summary

This PR includes:

1. **Dependency Updates**:
   - Updates Django from 4.1.0 to 4.2.5
   - Adds django-extensions==3.2.3

2. **Configuration Changes**:
   - Modifies requirements/base.txt
   - Updates development requirements

**Risk Assessment**: Medium - version updates require testing."""

        result = clean_reasoning_response(content)
        
        # Should preserve the markdown formatting and structure
        assert "## Summary" in result
        assert "**Dependency Updates**:" in result
        assert "1." in result and "2." in result
        assert "**Risk Assessment**:" in result

    def test_extract_final_response_with_unclosed_think_tags(self):
        """Test extraction from content with unclosed think tags."""
        content = """<think>
Let me analyze this PR step by step.
This seems to be a dependency update.

This PR updates the requirements.txt file to include newer versions of critical dependencies."""

        result = clean_reasoning_response(content)
        expected = "This PR updates the requirements.txt file to include newer versions of critical dependencies."
        assert result == expected

    def test_extract_final_response_with_think_attributes(self):
        """Test extraction from content with think tags that have attributes."""
        content = """<think type="analysis">
I need to check what's being changed in the pyproject.toml file.
The changes show version updates for several packages.
</think>

This PR updates several development dependencies in pyproject.toml, including pytest and black formatting tool."""

        result = clean_reasoning_response(content)
        expected = "This PR updates several development dependencies in pyproject.toml, including pytest and black formatting tool."
        assert result == expected

    def test_extract_final_response_with_uppercase_think_tags(self):
        """Test extraction from content with uppercase THINK tags."""
        content = """<THINK>
What are the security implications of this change?
The update looks like it addresses known vulnerabilities.
</THINK>

Security update: This PR addresses CVE-2023-12345 by updating the vulnerable package from 1.0.0 to 1.2.3."""

        result = clean_reasoning_response(content)
        expected = "Security update: This PR addresses CVE-2023-12345 by updating the vulnerable package from 1.0.0 to 1.2.3."
        assert result == expected

    def test_extract_final_response_with_title_case_think_tags(self):
        """Test extraction from content with title case Think tags."""
        content = """<Think>
This appears to be a routine maintenance update.
Let me check if there are any breaking changes.
</Think>

Routine maintenance: Updates multiple dependencies to their latest stable versions with no breaking changes expected."""

        result = clean_reasoning_response(content)
        expected = "Routine maintenance: Updates multiple dependencies to their latest stable versions with no breaking changes expected."
        assert result == expected