#!/bin/bash
set -e

echo "Installing GitHub MCP Server..."

# Get the latest release info from GitHub API
LATEST_RELEASE=$(curl -s https://api.github.com/repos/github/github-mcp-server/releases/latest)

# Extract the latest version tag
LATEST_VERSION=$(echo "$LATEST_RELEASE" | grep '"tag_name":' | sed -E 's/.*"tag_name": "([^"]+)".*/\1/')

if [ -z "$LATEST_VERSION" ]; then
    echo "Error: Could not determine latest version"
    exit 1
fi

echo "Latest version: $LATEST_VERSION"

# Construct download URL
DOWNLOAD_URL="https://github.com/github/github-mcp-server/releases/download/${LATEST_VERSION}/github-mcp-server_Linux_x86_64.tar.gz"

echo "Downloading from: $DOWNLOAD_URL"

# Create temporary directory
TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR"

# Download the release
curl -L -o github-mcp-server.tar.gz "$DOWNLOAD_URL"

# Extract the binary
tar -xzf github-mcp-server.tar.gz

# Find the binary (it might be in a subdirectory)
BINARY_PATH=$(find . -name "github-mcp-server" -type f -executable | head -n 1)

if [ -z "$BINARY_PATH" ]; then
    echo "Error: Could not find github-mcp-server binary in archive"
    ls -la
    exit 1
fi

echo "Found binary at: $BINARY_PATH"

# Create bin directory in user's home and install there
mkdir -p "$HOME/bin"
cp "$BINARY_PATH" "$HOME/bin/github-mcp-server"
chmod +x "$HOME/bin/github-mcp-server"

# Clean up
cd /
rm -rf "$TEMP_DIR"

echo "GitHub MCP Server $LATEST_VERSION installed successfully!"

# Verify installation
if [ -x "$HOME/bin/github-mcp-server" ]; then
    echo "Installation verified: github-mcp-server installed at $HOME/bin/github-mcp-server"
else
    echo "Warning: github-mcp-server not found at $HOME/bin/github-mcp-server"
    exit 1
fi