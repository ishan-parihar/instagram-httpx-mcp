"""
Configuration loading and argument parsing for Instagram MCP Server.

Loads settings from CLI arguments and environment variables.
"""

import argparse
import logging
import os
import sys
from typing import Literal, cast

from dotenv import load_dotenv

from .schema import AppConfig, ConfigurationError

load_dotenv()

logger = logging.getLogger(__name__)

FALSY_VALUES = ("0", "false", "no", "off")
TRUTHY_VALUES = ("1", "true", "yes", "on")


def _normalize_env(value: str) -> str:
    return value.strip().lower()


def positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"must be positive, got {value}")
    return ivalue


class EnvironmentKeys:
    LOG_LEVEL = "LOG_LEVEL"
    TRANSPORT = "TRANSPORT"
    HOST = "HOST"
    PORT = "PORT"
    HTTP_PATH = "HTTP_PATH"
    PROFILE_DIR = "USER_DATA_DIR"
    PREFERRED_BROWSER = "INSTAGRAM_PREFERRED_BROWSER"
    INSTAGRAM_COOKIES = "INSTAGRAM_COOKIES"


def is_interactive_environment() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, OSError):
        return False


def load_from_env(config: AppConfig) -> AppConfig:
    """Load configuration from environment variables."""
    if log_level_env := os.environ.get(EnvironmentKeys.LOG_LEVEL):
        log_level_upper = log_level_env.strip().upper()
        if log_level_upper in ("DEBUG", "INFO", "WARNING", "ERROR"):
            config.server.log_level = cast(
                Literal["DEBUG", "INFO", "WARNING", "ERROR"], log_level_upper
            )

    if transport_env := os.environ.get(EnvironmentKeys.TRANSPORT):
        config.server.transport_explicitly_set = True
        transport_value = _normalize_env(transport_env)
        if transport_value == "stdio":
            config.server.transport = "stdio"
        elif transport_value == "streamable-http":
            config.server.transport = "streamable-http"
        else:
            raise ConfigurationError(f"Invalid TRANSPORT: '{transport_env}'.")

    if profile_dir_env := os.environ.get(EnvironmentKeys.PROFILE_DIR):
        config.cookie.profile_dir = profile_dir_env

    if host_env := os.environ.get(EnvironmentKeys.HOST):
        config.server.host = host_env

    if port_env := os.environ.get(EnvironmentKeys.PORT):
        try:
            config.server.port = int(port_env)
        except ValueError:
            raise ConfigurationError(f"Invalid PORT: '{port_env}'. Must be an integer.")

    if path_env := os.environ.get(EnvironmentKeys.HTTP_PATH):
        config.server.path = path_env

    if browser_env := os.environ.get(EnvironmentKeys.PREFERRED_BROWSER):
        config.cookie.preferred_browser = browser_env.strip().lower()

    return config


def load_from_args(config: AppConfig) -> AppConfig:
    """Load configuration from command line arguments."""
    parser = argparse.ArgumentParser(
        description="Instagram MCP Server - A Model Context Protocol server for Instagram integration"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level (default: WARNING)",
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=None,
        help="Specify the transport mode (stdio or streamable-http)",
    )

    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="HTTP server host (default: 127.0.0.1)",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP server port (default: 8000)",
    )

    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="HTTP server path (default: /mcp)",
    )

    # Session management
    parser.add_argument(
        "--login",
        action="store_true",
        help="Login interactively by importing cookies from your browser",
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Check if current session is valid and exit",
    )

    parser.add_argument(
        "--logout",
        action="store_true",
        help="Clear stored Instagram profile",
    )

    parser.add_argument(
        "--user-data-dir",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to profile directory (default: ~/.instagram-mcp/profile)",
    )

    parser.add_argument(
        "--browser",
        type=str,
        default=None,
        metavar="BROWSER",
        help="Browser to import cookies from (brave, chrome, edge, firefox, zen, ...)",
    )

    args = parser.parse_args()

    if args.log_level:
        config.server.log_level = args.log_level

    if args.transport:
        config.server.transport = args.transport
        config.server.transport_explicitly_set = True

    if args.host:
        config.server.host = args.host

    if args.port:
        config.server.port = args.port

    if args.path:
        config.server.path = args.path

    if args.login:
        config.server.login = True

    if args.status:
        config.server.status = True

    if args.logout:
        config.server.logout = True

    if args.user_data_dir:
        config.cookie.profile_dir = args.user_data_dir

    if args.browser:
        config.cookie.preferred_browser = args.browser.lower()

    return config


def load_config() -> AppConfig:
    """
    Load configuration with clear precedence order:
    1. Command line arguments (highest priority)
    2. Environment variables
    3. Defaults (lowest priority)
    """
    config = AppConfig()
    config.is_interactive = is_interactive_environment()
    logger.debug(f"Interactive mode: {config.is_interactive}")

    config = load_from_env(config)
    config = load_from_args(config)
    config.validate()

    return config
