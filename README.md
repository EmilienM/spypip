# SpyPip - Python Packaging PR Analyzer

SpyPip is a tool that analyzes GitHub repositories to find open pull requests that touch Python packaging files and provides AI-powered summaries of packaging-related changes.

## Features

- 🔍 **Smart Detection**: Automatically identifies PRs that modify packaging files (requirements.txt, pyproject.toml, setup.py, Dockerfiles, etc.)
- 🤖 **AI Summaries**: Uses OpenAI GPT to generate concise summaries of packaging changes
- 📊 **Comprehensive Analysis**: Analyzes dependencies, build configurations, containerization changes, and version constraints
- 🔗 **GitHub Integration**: Seamlessly integrates with GitHub API via MCP (Model Context Protocol)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/EmilienM/spypip.git
cd spypip
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
export OPENAI_API_KEY="your-openai-api-key"
export GITHUB_PERSONAL_ACCESS_TOKEN="your-github-token"
# Optional: Override the default OpenAI endpoint
export OPENAI_ENDPOINT_URL="https://your-custom-inference-server.com"
```

## Usage

Run SpyPip by specifying the repository you want to analyze:

```bash
python -m spypip owner/repository-name
```

For example:
```bash
python -m spypip vllm-project/vllm
```

## Output

SpyPip will:

1. Fetch all open pull requests from the specified repository
2. Identify PRs that modify packaging files
3. Generate AI-powered summaries for each relevant PR
4. Display a comprehensive report showing:
   - PR details (number, title, author, URL)
   - Changed packaging files with statistics
   - AI analysis of packaging implications

## Environment Variables

- `OPENAI_API_KEY`: Required for AI summary generation
- `GITHUB_PERSONAL_ACCESS_TOKEN`: Required for GitHub API access
- `OPENAI_ENDPOINT_URL`: Optional. Override the default OpenAI inference server URL (defaults to `https://models.github.ai/inference`)

## Dependencies

- `openai`: For AI-powered analysis
- `mcp`: Model Context Protocol for GitHub integration
- Standard library modules for async operations and data handling

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.