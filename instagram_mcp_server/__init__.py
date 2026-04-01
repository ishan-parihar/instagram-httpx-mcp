# src/linkedin_mcp_server/__init__.py
"""
Instagram MCP Server package.

A Model Context Protocol (MCP) server that provides Instagram integration capabilities
for AI assistants. This package enables secure Instagram profile, company, and job
data scraping through a standardized MCP interface.

Key Features:
- Secure Instagram authentication via session files
- Instagram profile, company, and job data scraping
- MCP-compliant server implementation using FastMCP
- Playwright browser automation with session persistence
- Layered configuration system with secure credential storage
- Docker containerization for easy deployment
- Claude Desktop MCP Bundle (MCPB, formerly DXT) support

Architecture:
- Clean separation between authentication, driver management, and MCP server
- Singleton pattern for browser session management
- Comprehensive error handling and logging
- Cross-platform compatibility (macOS, Windows, Linux)
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("instagram-scraper-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"  # Running from source without install
