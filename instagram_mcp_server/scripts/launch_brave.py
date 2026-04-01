"""
Launch Brave browser with remote debugging enabled.

This script helps users start Brave in the correct mode for CDP connection.
It connects to your EXISTING Brave profile - do NOT use if you want to keep
your current Instagram session separate.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

BRAVE_PATHS_UNIX = [
    "/opt/brave-bin/brave",
    "/usr/bin/brave-browser",
    "/usr/bin/brave",
    Path.home() / ".local/bin/brave",
]

BRAVE_PATHS_WINDOWS = [
    Path("C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
    Path(
        "C:\\Program Files (x86)\\BraveSoftware\\Brave-Browser\\Application\\brave.exe"
    ),
    Path.home() / "AppData/Local/BraveSoftware/Brave-Browser/Application/brave.exe",
]

DEBUGGING_PORT = 9222


def find_brave_executable() -> Path | None:
    """Find Brave browser executable."""
    if sys.platform == "win32":
        for path in BRAVE_PATHS_WINDOWS:
            if path.exists():
                return path
        # Try finding via PATH
        try:
            result = subprocess.run(
                ["where", "brave"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0,
            )
            if result.returncode == 0 and result.stdout.strip():
                return Path(result.stdout.strip().split("\n")[0])
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return None
    else:
        for path in BRAVE_PATHS_UNIX:
            if path.exists():
                return path
        # Try finding via PATH
        try:
            result = subprocess.run(
                ["which", "brave-browser"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                return Path(result.stdout.strip())
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return None


def find_existing_brave() -> int | None:
    """Find existing Brave process (any)."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "brave"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            return int(pids[0]) if pids else None
        return None
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return None


def find_brave_with_debugging() -> int | None:
    """Find Brave process with remote debugging enabled."""
    try:
        result = subprocess.run(
            ["pgrep", "-af", "brave.*remote-debugging-port"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            for line in lines:
                parts = line.split()
                if parts and parts[0].isdigit():
                    return int(parts[0])
        return None
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        return None


def launch_brave() -> int:
    """Launch Brave with remote debugging enabled using DEFAULT profile."""
    brave_exe = find_brave_executable()

    if not brave_exe:
        print("Error: Brave browser not found.")
        print("\nPlease install Brave browser:")
        print("  Ubuntu/Debian: sudo apt install brave-browser")
        print("  Fedora: sudo dnf install brave-browser")
        print("  Or download from: https://brave.com")
        return 1

    # Check if Brave is already running with debugging
    existing_debug = find_brave_with_debugging()
    if existing_debug:
        print(
            f"✓ Brave is already running with remote debugging (PID: {existing_debug})"
        )
        print(f"\nNow run the MCP server:")
        print(f"  uv run -m instagram_mcp_server")
        return 0

    # Check if Brave is running without debugging
    existing_brave = find_existing_brave()
    if existing_brave:
        print(
            f"⚠ Brave is already running (PID: {existing_brave}) but without remote debugging."
        )
        print("\nTo use CDP mode, you need to restart Brave with remote debugging.")
        print("\nOption 1: Quick restart (closes all Brave windows)")
        print("  Run: pkill brave && sleep 2 && uv run instagram-launch-brave")
        print("\nOption 2: Manual restart (keeps your session)")
        print("  1. Save your work and close Brave manually")
        print("  2. Run: brave-browser --remote-debugging-port=9222")
        print("\nOption 3: Add flag permanently")
        print(
            "  Edit your Brave desktop shortcut to include: --remote-debugging-port=9222"
        )
        return 1

    print(f"Found Brave: {brave_exe}")
    print(f"Launching with remote debugging on port {DEBUGGING_PORT}...")
    print("\n⚠ IMPORTANT: This uses your DEFAULT Brave profile.")
    print("   Your existing Instagram session (if logged in) will be available.")
    print("\nPlease log into Instagram if not already logged in.")
    print("Press Ctrl+C to stop.")

    # Launch WITHOUT --user-data-dir to use default profile
    cmd = [
        str(brave_exe),
        f"--remote-debugging-port={DEBUGGING_PORT}",
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
        print("\n✓ Brave launched successfully with your default profile!")
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
