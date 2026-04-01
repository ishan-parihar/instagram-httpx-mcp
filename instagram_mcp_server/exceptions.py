# instagram_mcp_server/exceptions.py
"""
Custom exceptions for Instagram MCP Server with specific error categorization.

Defines hierarchical exception types for different error scenarios including
authentication failures and MCP client reporting.
"""


class InstagramMCPError(Exception):
    """Base exception for Instagram MCP Server."""

    pass


class CredentialsNotFoundError(InstagramMCPError):
    """No credentials available in non-interactive mode."""

    pass


class SessionExpiredError(InstagramMCPError):
    """Session has expired and needs to be refreshed."""

    def __init__(self, message: str | None = None):
        default_msg = (
            "Instagram session has expired.\n\n"
            "To fix this:\n"
            "  Run with --login to create a new session"
        )
        super().__init__(message or default_msg)


class BrowserSetupInProgressError(InstagramMCPError):
    """Patchright Chromium browser setup is still running."""


class BrowserSetupFailedError(InstagramMCPError):
    """Patchright Chromium browser setup failed."""


class AuthenticationStartedError(InstagramMCPError):
    """Interactive Instagram login has been started."""


class AuthenticationInProgressError(InstagramMCPError):
    """Interactive Instagram login is already running."""


class AuthenticationBootstrapFailedError(InstagramMCPError):
    """Interactive Instagram login could not be completed."""


class DockerHostLoginRequiredError(InstagramMCPError):
    """Docker runtime requires host-side login creation."""


class LinuxBrowserDependencyError(InstagramMCPError):
    """Linux host dependencies required for Chromium are missing."""


class CDPConnectionError(InstagramMCPError):
    """Failed to connect to Brave browser via CDP.

    This error is raised when the server cannot establish a CDP connection
    to a running Brave browser instance.
    """

    default_message = (
        "Could not connect to Brave browser via CDP.\n\n"
        "To fix this:\n"
        "  1. Launch Brave with remote debugging:\n"
        "     uv run instagram-launch-brave\n"
        "  2. Or manually:\n"
        "     brave-browser --remote-debugging-port=9222\n"
        "  3. Log into Instagram in that browser window\n"
        "  4. Retry this tool\n\n"
        "For more information, see docs/CDP_MODE.md"
    )

    def __init__(self, message: str | None = None):
        super().__init__(message or self.default_message)
