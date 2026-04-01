"""
Launch Brave browser with remote debugging enabled.

This script helps users start Brave in the correct mode for CDP connection.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

BRAVE_PATHS = [
    "/opt/brave-bin/brave",
    "/usr/bin/brave-browser",
    "/usr/bin/brave",
    Path.home() / ".local/bin/brave",
    "brave-browser",
    "brave",
]

DEBUGGING_PORT = 9222
USER_DATA_DIR = Path.home() / ".instagram-mcp" / "brave-profile"


def find_brave_executable() -> Path | None:
    """Find Brave browser executable."""
    for path in BRAVE_PATHS:
        if isinstance(path, Path):
            if path.exists():
                return path
        else:
            try:
                result = subprocess.run(
                    ["which", path],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return Path(result.stdout.strip())
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
    return None


def launch_brave() -> int:
    """Launch Brave with remote debugging enabled."""
    brave_exe = find_brave_executable()

    if not brave_exe:
        print("Error: Brave browser not found.")
        print("\nPlease install Brave browser:")
        print("  Ubuntu/Debian: sudo apt install brave-browser")
        print("  Fedora: sudo dnf install brave-browser")
        print("  Or download from: https://brave.com")
        return 1

    print(f"Found Brave: {brave_exe}")
    print(f"Launching with remote debugging on port {DEBUGGING_PORT}...")
    print(f"Profile directory: {USER_DATA_DIR}")
    print("\nPlease log into Instagram in the Brave window.")
    print("Press Ctrl+C to stop.")

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(brave_exe),
        f"--remote-debugging-port={DEBUGGING_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.instagram.com/",
    ]

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print("\n✓ Brave launched successfully!")
        print(f"\nNow run the MCP server:")
        print(f"  uv run -m instagram_mcp_server")
        return 0

    except Exception as e:
        print(f"Error launching Brave: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    return launch_brave()


if __name__ == "__main__":
    sys.exit(main())
