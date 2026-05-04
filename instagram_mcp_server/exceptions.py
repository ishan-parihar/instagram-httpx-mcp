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
    """Setup is still in progress."""


class BrowserSetupFailedError(InstagramMCPError):
    """Setup failed."""


class AuthenticationStartedError(InstagramMCPError):
    """Interactive Instagram login has been started."""


class AuthenticationInProgressError(InstagramMCPError):
    """Interactive Instagram login is already running."""


class AuthenticationBootstrapFailedError(InstagramMCPError):
    """Interactive Instagram login could not be completed."""


class DockerHostLoginRequiredError(InstagramMCPError):
    """Docker runtime requires host-side login creation."""


class CDPConnectionError(InstagramMCPError):
    """Failed to connect to a browser via CDP (legacy, unused)."""


class LinuxBrowserDependencyError(InstagramMCPError):
    """Linux host dependencies required for browser are missing (legacy, unused)."""
