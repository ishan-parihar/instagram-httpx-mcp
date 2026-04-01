# instagram_mcp_server/tools/__init__.py
"""
Instagram scraping tools package.

This package contains the MCP tool implementations for Instagram data extraction.
Each tool module provides specific functionality for different Instagram entities
while sharing common error handling and driver management patterns.

Available Tools:
- User tools: Instagram profile scraping and analysis
- Insights tools: Company/business profile and information extraction
- Post tools: Post details and search functionality
- Search tools: Search users, posts, and content
- Action tools: Actions like follow, like, comment
- Messaging tools: Inbox, conversations, search, and sending messages

Architecture:
- FastMCP integration for MCP-compliant tool registration
- Depends()-based dependency injection for browser/extractor setup
- ToolError-based error handling through centralized raise_tool_error()
- Singleton driver pattern for session persistence
- Structured data return format for consistent MCP responses
"""
