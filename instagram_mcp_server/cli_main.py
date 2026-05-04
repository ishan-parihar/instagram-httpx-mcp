"""Instagram MCP Server main CLI application entry point."""

import asyncio
import logging
import sys
from typing import Literal

import inquirer
import httpx

from instagram_mcp_server.authentication import clear_auth_state
from instagram_mcp_server.config import get_config
from instagram_mcp_server.drivers.browser import (
    close_browser,
    get_profile_dir,
    load_cookies,
    profile_exists,
)
from instagram_mcp_server.logging_config import (
    configure_logging,
    teardown_trace_logging,
)
from instagram_mcp_server.server import create_mcp_server
from instagram_mcp_server.session_state import (
    get_runtime_id,
    load_source_state,
    portable_cookie_path,
    source_state_path,
)
from instagram_mcp_server.setup import run_profile_creation

logger = logging.getLogger(__name__)


def choose_transport_interactive() -> Literal["stdio", "streamable-http"]:
    questions = [
        inquirer.List(
            "transport",
            message="Choose mcp transport mode",
            choices=[
                ("stdio (Default CLI mode)", "stdio"),
                ("streamable-http (HTTP server mode)", "streamable-http"),
            ],
            default="stdio",
        )
    ]
    answers = inquirer.prompt(questions)
    if not answers:
        raise KeyboardInterrupt("Transport selection cancelled by user")
    return answers["transport"]


def clear_profile_and_exit() -> None:
    """Clear Instagram profile and exit."""
    config = get_config()
    configure_logging(
        log_level=config.server.log_level,
        json_format=not config.is_interactive and config.server.log_level != "DEBUG",
    )

    profile_dir = get_profile_dir()
    if not (
        profile_exists(profile_dir)
        or portable_cookie_path(profile_dir).exists()
        or source_state_path(profile_dir).exists()
    ):
        print("No authentication state found")
        print("Nothing to clear.")
        sys.exit(0)

    print(f"Clear Instagram authentication state from {profile_dir.parent}?")
    try:
        confirmation = (
            input("Are you sure you want to clear the profile? (y/N): ").strip().lower()
        )
        if confirmation not in ("y", "yes"):
            print("Operation cancelled")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\nOperation cancelled")
        sys.exit(0)

    if clear_auth_state(profile_dir):
        print("Authentication state cleared successfully!")
    else:
        print("Failed to clear authentication state")
        sys.exit(1)
    sys.exit(0)


def get_profile_and_exit() -> None:
    """Create profile interactively and exit."""
    config = get_config()
    configure_logging(
        log_level=config.server.log_level,
        json_format=not config.is_interactive and config.server.log_level != "DEBUG",
    )

    profile_dir = get_profile_dir()
    browser_id = config.cookie.preferred_browser
    success = run_profile_creation(str(profile_dir), browser_id=browser_id)
    sys.exit(0 if success else 1)


def profile_info_and_exit() -> None:
    """Check profile validity and display info, then exit."""
    config = get_config()
    configure_logging(
        log_level=config.server.log_level,
        json_format=not config.is_interactive and config.server.log_level != "DEBUG",
    )

    profile_dir = get_profile_dir()
    cookies_path = portable_cookie_path(profile_dir)
    source_state = load_source_state(profile_dir)

    if not source_state or not profile_exists(profile_dir) or not cookies_path.exists():
        print(f"No valid source session found at {profile_dir}")
        print("   Run with --login to create a source session")
        sys.exit(1)

    print(f"Profile directory: {profile_dir}")
    print(f"Runtime ID: {get_runtime_id()}")
    if source_state:
        print(f"Source runtime: {source_state.source_runtime_id}")
        print(f"Login generation: {source_state.login_generation}")

    # Validate session by making a test API call
    valid = asyncio.run(_check_session_api())

    if valid:
        print("Session is valid")
        sys.exit(0)

    print("Session expired or invalid")
    print("   Run with --login to re-authenticate")
    sys.exit(1)


async def _check_session_api() -> bool:
    """Check Instagram session validity by calling the web profile API."""
    try:
        cookies = load_cookies()
        if not cookies:
            return False

        headers = {
            "X-CSRFToken": cookies.get("csrftoken", ""),
            "X-IG-App-ID": "936619743392459",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
            ),
        }
        async with httpx.AsyncClient(
            cookies=cookies, headers=headers, timeout=15
        ) as client:
            resp = await client.get(
                "https://www.instagram.com/api/v1/users/web_profile_info/"
                "?username=instagram"
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("status") == "ok":
                print("Instagram session is valid")
                return True
            print(f"Instagram API returned: {resp.status_code} - {data}")
            return False
    except Exception as e:
        print(f"Session check failed: {e}")
        return False


def get_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        for package_name in ("instagram-scraper-mcp", "instagram-mcp-server"):
            try:
                return version(package_name)
            except PackageNotFoundError:
                continue
    except Exception:
        pass
    try:
        import os
        import tomllib

        pyproject_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "pyproject.toml"
        )
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data["project"]["version"]
    except Exception:
        return "unknown"


def main() -> None:
    """Main application entry point."""
    config = get_config()

    configure_logging(
        log_level=config.server.log_level,
        json_format=not config.is_interactive and config.server.log_level != "DEBUG",
    )

    version = get_version()

    if config.is_interactive:
        print(f"Instagram MCP Server v{version}")
        print("=" * 40)

    logger.info(f"Instagram MCP Server v{version}")

    try:
        # Handle --logout flag
        if config.server.logout:
            clear_profile_and_exit()

        # Handle --login flag
        if config.server.login:
            get_profile_and_exit()

        # Handle --status flag
        if config.server.status:
            profile_info_and_exit()

        logger.debug(f"Server configuration: {config}")

        try:
            transport = config.server.transport

            if config.is_interactive and not config.server.transport_explicitly_set:
                print("\nServer ready! Choose transport mode:")
                transport = choose_transport_interactive()

            mcp = create_mcp_server()

            if transport == "streamable-http":
                mcp.run(
                    transport=transport,
                    host=config.server.host,
                    port=config.server.port,
                    path=config.server.path,
                )
            else:
                mcp.run(transport=transport)

        except KeyboardInterrupt:
            exit_gracefully(0)
        except Exception as e:
            logger.exception(f"Server runtime error: {e}")
            if config.is_interactive:
                print(f"\nServer error: {e}")
            exit_gracefully(1)
    finally:
        teardown_trace_logging(keep_traces=False)


def exit_gracefully(exit_code: int = 0) -> None:
    try:
        asyncio.run(close_browser())
    except Exception:
        pass
    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        exit_gracefully(0)
    except Exception as e:
        logger.exception(
            f"Error running MCP server: {e}",
            extra={"exception_type": type(e).__name__, "exception_message": str(e)},
        )
        exit_gracefully(1)
