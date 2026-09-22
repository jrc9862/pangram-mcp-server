"""MCP server for Pangram AI-text detection via a logged-in browser session."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-server-pangram")
except PackageNotFoundError:
    __version__ = "0.0.0"
