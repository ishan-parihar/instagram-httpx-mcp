"""
Configuration schema definitions for Instagram MCP Server.

Defines the dataclass schemas that represent the application's configuration
structure with type-safe configuration objects and default values.
"""

import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration validation fails."""


@dataclass
class CookieConfig:
    """Configuration for cookie-based Instagram API access."""

    profile_dir: str = "~/.instagram-mcp/profile"
    preferred_browser: str | None = None

    def validate(self) -> None:
        """Validate configuration values."""
        pass


@dataclass
class ServerConfig:
    """MCP server configuration."""

    transport: Literal["stdio", "streamable-http"] = "stdio"
    transport_explicitly_set: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "WARNING"
    login: bool = False
    status: bool = False
    logout: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"


@dataclass
class AppConfig:
    """Main application configuration."""

    cookie: CookieConfig = field(default_factory=CookieConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    is_interactive: bool = field(default=False)

    def validate(self) -> None:
        """Validate all configuration values."""
        self.cookie.validate()
        if self.server.transport == "streamable-http":
            self._validate_transport_config()
            self._validate_path_format()
        self._validate_port_range()

    def _validate_transport_config(self) -> None:
        if not self.server.host:
            raise ConfigurationError("HTTP transport requires a valid host")
        if not self.server.port:
            raise ConfigurationError("HTTP transport requires a valid port")
        if self.server.host in ("0.0.0.0", "::"):
            logger.warning(
                "HTTP transport is binding to %s which exposes the server to "
                "all network interfaces. The MCP endpoint has no authentication "
                "— anyone on your network can use your Instagram session. "
                "Use 127.0.0.1 (default) unless you understand the risk.",
                self.server.host,
            )

    def _validate_port_range(self) -> None:
        if not (1 <= self.server.port <= 65535):
            raise ConfigurationError(
                f"Port {self.server.port} is not in valid range (1-65535)"
            )

    def _validate_path_format(self) -> None:
        if not self.server.path.startswith("/"):
            raise ConfigurationError(
                f"HTTP path '{self.server.path}' must start with '/'"
            )
        if len(self.server.path) < 2:
            raise ConfigurationError(
                f"HTTP path '{self.server.path}' must be at least 2 characters"
            )
