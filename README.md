# SpyPip - Python Packaging Version Analyzer

<img src="logo.png" alt="SpyPip Logo" width="200">

SpyPip is a tool that analyzes GitHub repositories to compare commits between two versions/tags that touch Python packaging files and provides AI-powered summaries of packaging-related changes.

## Features

- 🔍 **Smart Detection**: Automatically identifies commits that modify packaging files (requirements.txt, pyproject.toml, setup.py, Dockerfiles, etc.)
- 🏷️ **Version Comparison**: Compare commits between two tags/versions or between latest tag and main branch
- � **Custom File Monitoring**: Override default patterns by providing patch files with custom file paths to monitor
- 🤖 **AI Summaries**: Leverages LLM to generate concise summaries of packaging changes
- 🔧 **AI Patch Regeneration**: When patches fail to apply, automatically attempts to regenerate them using LLM analysis of the current codebase
- 🔗 **GitHub Integration**: Seamlessly integrates with GitHub API via MCP (Model Context Protocol)
- 🧠 **Reasoning Model Support**: Compatible with reasoning models that include thinking steps in responses


## Demo

<details>
    <summary>Click to expand and see the tool in action</summary>

    podman run --name spypip --env-file .env --rm -it quay.io/emilien/spypip:latest pytorch/pytorch --from-tag v2.6.0 --to-tag v2.7.0
    Starting analysis of pytorch/pytorch
    Comparing commits from v2.6.0 to v2.7.0
    Fetching commits between v2.6.0 and v2.7.0 for pytorch/pytorch...
    GitHub MCP Server running on stdio
    Found 100 commits between v2.6.0 and v2.7.0
    Analyzing commit 13417947: Gracefully handle optree less than minimum version, part 2 (#151323)
    Analyzing commit 61f9b50e: [ROCm] Fix TORCH_CHECK for hdim 512 support added in AOTriton 0.9b (#148967)
    [snip]
    Analyzing commit 971606be: Add a stable TORCH_LIBRARY to C shim (#148124)
    Found 3 commits with packaging changes
    Generating AI summary for commit b766c020...
    Generating AI summary for commit 64ca70f8...
    Generating AI summary for commit 971606be...
    
    ================================================================================
    PYTHON PACKAGING VERSION ANALYSIS RESULTS
    ================================================================================
    Using default packaging file patterns (19 patterns)
    ----------------------------------------
    
    1. Commit b766c020: [Cherry-pick] Make PyTorch buildable with cmake-4 (#150460)
       Author: Nikita Shulga
       Date: 2025-04-02T02:37:52Z
       URL: https://github.com/pytorch/pytorch/commit/b766c0200a9d34c76a7c74cec5b78311f5cb8ae7
       Files changed (1):
         - requirements.txt (modified) +1/-1
    
       AI Summary:
       Looking at the packaging files changed, only requirements.txt was modified. The patch preview shows that the line for cmake was changed from "cmake==3.31.6  # Temp pin until we support 4.0.0?" to just "cmake". So, the version constraint is being removed.
    
    First, I should note that this is a dependency change. The cmake package is being updated, but not to a specific version. Instead, the version is being unpinned. Previously, it was pinned to 3.31.6, which was a temporary measure until support for cmake 4.0.0 was ready. Now, by removing the version constraint, the project will use the latest available version of cmake, which is likely 4.0.0 or higher.
    
    Next, I should consider the implications of this change. Unpinning a dependency can have both positive and negative effects. On the positive side, it allows the project to take advantage of newer features and bug fixes in cmake 4.x, which might be necessary for certain build configurations or improvements in PyTorch. This could make the build process more compatible with newer systems or environments that have cmake 4 installed.
    
    However, there are potential risks. If the project wasn't fully tested with cmake 4, there might be breaking changes or compatibility issues. This could lead to build failures or unexpected behavior in the future. It's also possible that some downstream dependencies or tools used in the build process might not be compatible with cmake 4 yet, which could introduce new bugs or vulnerabilities.
    
    Another consideration is the build configuration. Since the commit is about making PyTorch buildable with cmake-4, it's likely that other parts of the build process were updated to handle the new cmake version. This might include changes in CMakeLists.txt or other build scripts to ensure compatibility. However, since the packaging files only show a change in requirements.txt
    ----------------------------------------
    
    2. Commit 64ca70f8: Pin cmake==3.31.6 (#150193)
       Author: pytorchbot
       Date: 2025-03-28T16:09:29Z
       URL: https://github.com/pytorch/pytorch/commit/64ca70f83c62f1e2430634da42fbe2415c3766ce
       Files changed (1):
         - requirements.txt (modified) +1/-1
    
       AI Summary:
       The commit pins the cmake
    ----------------------------------------
    
    3. Commit 971606be: Add a stable TORCH_LIBRARY to C shim (#148124)
       Author: Jane Xu
       Date: 2025-03-11T14:44:21Z
       URL: https://github.com/pytorch/pytorch/commit/971606befac4f5638ec039c53ea2f78da44d0030
       Files changed (2):
         - setup.py (modified) +1/-0
         - test/cpp_extensions/libtorch_agnostic_extension/setup.py (added) +67/-0
    
       AI Summary:
       Looking at the packaging files changed, there are two files involved: setup.py and test/cpp_extensions/libtorch_agnostic_extension/setup.py. 
    
    First, setup.py is modified. The patch shows that a new include directory "include/torch/csrc/stable/*.h" is added. This means that the build process will now include headers from this new directory. Including new headers could indicate that there are new C++ extensions or APIs being exposed, which might require corresponding changes in the build setup.
    
    Next, a new file test/cpp_extensions/libtorch_agnostic_extension/setup.py is added. This file contains a setup script that uses setuptools and the torch.utils.cpp_extension module. It defines a custom clean command that removes build artifacts. The presence of this setup.py suggests that a new C++ extension module is being created or tested. This module is likely part of the PyTorch C++ API, allowing users to integrate PyTorch with C++ code more seamlessly.
    
    In terms of dependencies, I don't see any changes in files like requirements.txt or pyproject.toml, so it doesn't look like any Python packages are being added or removed. However, the addition of a new C++ extension might depend on specific compiler versions or build tools, which could affect the build configuration. The use of setuptools and CppExtension indicates that the build process is leveraging existing PyTorch build infrastructure, so it's probably compatible with the current setup.
    
    For containerization, there's no mention of Dockerfiles or similar files being changed, so I don't think this commit affects container builds directly. However, if the new C++ extension is included in the final package, it might require additional libraries or dependencies at runtime, which could impact the container's size or required base images.
    
    Version constraints aren't modified in the packaging files, so this change doesn't seem to affect how dependencies are resolved. The focus here is more on adding new build artifacts rather than changing how dependencies are managed.
    ----------------------------------------
    INFO[0094] shutting down server...
</details>

## Quickstart

1. Create .env file:

```bash
# Copy the example file and edit it with your values
cp .env.example .env
# Edit .env with your favorite editor
vi .env
```

2. Run SpyPip

```bash
podman run --name spypip --env-file .env --rm -it quay.io/emilien/spypip:latest ROCm/aotriton
```

Compare specific tags:

```bash
podman run --name spypip --env-file .env --rm -it quay.io/emilien/spypip:latest ROCm/aotriton --from-tag v1.0.0 --to-tag v1.1.0
```

With custom patches:

```bash
podman run --name spypip --env-file .env --rm -it \
  -v ./my-patches:/patches:ro,Z \
  quay.io/emilien/spypip:latest \
  ROCm/aotriton --patches-dir /patches
```

Validate patches before analysis:

```bash
podman run --name spypip --env-file .env --rm -it \
  -v ./my-patches:/patches:ro,Z \
  quay.io/emilien/spypip:latest \
  ROCm/aotriton --patches-dir /patches --check-patch-apply-only
```

Get JSON output for failed patches (useful for CI/CD integration):

```bash
podman run --name spypip --env-file .env --rm -it \
  -v ./my-patches:/patches:ro,Z \
  quay.io/emilien/spypip:latest \
  ROCm/aotriton --patches-dir /patches --check-patch-apply-only --json-output
```

## Install and run locally

1. Clone the repository:
```bash
git clone https://github.com/EmilienM/spypip.git
cd spypip
```

2. Install dependencies:
```bash
pip install -e .
```

3. Set up environment variables:

**Option A: Using .env file (recommended)**
```bash
# Copy the example file and edit it with your values
cp .env.example .env
# Edit .env with your favorite editor
vi .env
```

**Option B: Using shell environment variables**
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

For example (compares latest tag to main):
```bash
python -m spypip vllm-project/vllm
```

Compare specific tags:
```bash
python -m spypip vllm-project/vllm --from-tag v1.0.0 --to-tag v1.1.0
```

Compare from specific tag to main:
```bash
python -m spypip vllm-project/vllm --from-tag v1.0.0
```

Limit the number of commits to analyze (default is 50):
```bash
python -m spypip vllm-project/vllm --max-commits 100
```

### Custom File Monitoring with Patch Files

You can override the default list of packaging files by providing a directory containing patch files:

```bash
python -m spypip owner/repository-name --patches-dir /path/to/patches
```

Or combine with version comparison:

```bash
python -m spypip owner/repository-name --from-tag v1.0.0 --to-tag v1.1.0 --patches-dir /path/to/patches
```

### Patch Validation Mode

Before running the full analysis, you can validate that your patch files can be applied to the target repository using the `--check-patch-apply-only` option:

```bash
python -m spypip owner/repository-name --patches-dir /path/to/patches --check-patch-apply-only
```

Or test against a specific branch/tag:

```bash
python -m spypip owner/repository-name --patches-dir /path/to/patches --check-patch-apply-only --to-tag v2.0.0
```

For integration with CI/CD pipelines or automation tools, you can output failed patches in JSON format suitable for creating tickets or reports:

```bash
python -m spypip owner/repository-name --patches-dir /path/to/patches --check-patch-apply-only --json-output
```

This mode will:
1. Clone the repository to a temporary directory (including submodules)
2. Checkout the specified reference (defaults to `main`)
3. Test each `.patch` and `.diff` file to see if it can be applied
4. **AI Patch Regeneration**: When a patch fails to apply, automatically attempt to regenerate it using LLM analysis
5. Provide detailed diagnostic information for any patches that fail
6. Exit with status code 0 if all patches apply successfully, or 1 if any fail

#### JSON Output Format

When using `--json-output` with `--check-patch-apply-only`, failed patches are output in JSON format:

```json
{
  "title": "Failed to apply patches owner/repository for 'main'",
  "content": "Some patches for owner/repository failed to apply on main:\n\nApplying patch: example.patch\n✗ Patch example.patch FAILED to apply\n  Error: patch does not apply\n\nYou'll need to fix these patches manually."
}
```

This JSON output is designed to be consumed by automation tools for creating tickets, alerts, or reports when patch validation fails.

**Note:** The `--check-patch-apply-only` option requires `--patches-dir` to be specified and only works with `.patch` and `.diff` files (not plain text file lists). The `--json-output` flag can only be used with `--check-patch-apply-only`.

The patches directory can contain:

**Git patch files (.patch, .diff):**
```bash
# example_patches/changes.patch
diff --git a/custom-requirements.txt b/custom-requirements.txt
index 1234567..abcdefg 100644
--- a/custom-requirements.txt
+++ b/custom-requirements.txt
@@ -1,3 +1,4 @@
 flask==2.0.0
 requests==2.28.0
+numpy==1.21.0
 pytest==7.1.0
```

**Plain text files (.txt) with file paths:**
```bash
# example_patches/file_list.txt
# Custom packaging files to monitor
project/requirements-dev.txt
deployment/Containerfile.prod
config/environment-staging.yml
build-constraints.txt
```

When using `--patches-dir`, SpyPip will:
1. Read all `.patch`, `.diff`, and `.txt` files in the specified directory
2. Extract exact file paths from git patches or plain text lists
3. Monitor commits that touch exactly these file paths (no pattern matching)
4. Use exact path matching instead of the default packaging file patterns
5. Display a custom message showing which files are being monitored

## Output

SpyPip will:

1. Compare commits between the specified tags/versions (or latest tag to main by default)
2. Identify commits that modify packaging files
3. Generate AI-powered summaries for each relevant commit
4. Display a comprehensive report showing:
   - Commit details (SHA, title, author, date, URL)
   - Changed packaging files with statistics
   - AI analysis of packaging implications

## Environment Variables

SpyPip supports loading environment variables from `.env` files. It searches for `.env` files in the following order:
1. Current working directory
2. User's home directory
3. Project root directory

**Required Variables:**
- `OPENAI_API_KEY`: Required for AI summary generation
- `GITHUB_PERSONAL_ACCESS_TOKEN`: Required for GitHub API access

**Optional Variables:**
- `OPENAI_ENDPOINT_URL`: Override the default OpenAI inference server URL (defaults to `https://models.github.ai/inference`)
- `MODEL_NAME`: Specify the model to use for AI analysis (defaults to `openai/gpt-4.1`)

**Note:** Environment variables set in your shell will take precedence over those in `.env` files.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.
