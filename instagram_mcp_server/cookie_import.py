"""
Manual cookie import for Instagram MCP Server.

When automated browser login fails due to Instagram's bot detection,
users can manually log in via their regular browser and export cookies.
"""

import json
import logging
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

INSTAGRAM_COOKIES = {"sessionid", "csrftoken", "ds_user_id", "ig_did", "mid"}


def get_brave_cookie_db() -> Path | None:
    """Find Brave browser's cookie database."""
    possible_paths = [
        Path.home() / ".config/BraveSoftware/Brave-Browser/Default/Cookies",
        Path.home() / ".config/brave/Default/Cookies",
        Path.home()
        / ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser/Default/Cookies",
    ]

    for path in possible_paths:
        if path.exists():
            return path
    return None


def extract_instagram_cookies() -> dict[str, str] | None:
    """Extract Instagram cookies from Brave browser's SQLite database."""
    cookie_db = get_brave_cookie_db()
    if not cookie_db:
        print("   Could not find Brave cookie database")
        return None

    # Copy to temp file since SQLite DB is locked by browser
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        tmp_path = Path(tmp.name)

    try:
        import shutil

        shutil.copy2(cookie_db, tmp_path)

        conn = sqlite3.connect(str(tmp_path))
        cursor = conn.cursor()

        # Query Instagram cookies
        cursor.execute("""
            SELECT name, value, encrypted_value 
            FROM cookies 
            WHERE host_key LIKE '%instagram.com%'
        """)

        cookies = {}
        for row in cursor.fetchall():
            name, value, encrypted_value = row

            if name in INSTAGRAM_COOKIES:
                if value:
                    cookies[name] = value
                elif encrypted_value:
                    # Encrypted cookies need decryption (Linux only)
                    # For now, skip encrypted cookies
                    logger.debug(f"Skipping encrypted cookie: {name}")

        conn.close()

        if cookies:
            return cookies
        return None

    finally:
        tmp_path.unlink(missing_ok=True)


def save_cookies_to_profile(cookies: dict[str, str], profile_dir: Path) -> bool:
    """Save cookies to the MCP profile directory."""
    cookie_file = profile_dir / "cookies.json"

    try:
        cookie_data = {
            "cookies": [
                {
                    "name": name,
                    "value": value,
                    "domain": ".instagram.com",
                    "path": "/",
                    "secure": True,
                }
                for name, value in cookies.items()
            ],
            "imported_from": "brave_manual",
        }

        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cookie_file, "w") as f:
            json.dump(cookie_data, f, indent=2)

        # Set restrictive permissions
        cookie_file.chmod(0o600)

        return True
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")
        return False


def manual_cookie_import_guide() -> None:
    """Print instructions for manual cookie import."""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  Instagram Cookie Import - Manual Method                         ║
╠══════════════════════════════════════════════════════════════════╣
║  When automated login fails due to bot detection, follow these  ║
║  steps to import cookies from your regular browser:             ║
║                                                                  ║
║  1. Open Instagram in your regular Brave/Chrome browser         ║
║     https://www.instagram.com/                                  ║
║                                                                  ║
║  2. Log in normally (complete any 2FA/captcha)                  ║
║                                                                  ║
║  3. Install a cookie editor extension:                          ║
║     - EditThisCookie (Chrome/Brave Web Store)                   ║
║     - Cookie Editor (Firefox Add-ons)                           ║
║                                                                  ║
║  4. On Instagram, click the cookie editor extension             ║
║                                                                  ║
║  5. Export cookies as JSON                                      ║
║                                                                  ║
║  6. Save to: ~/.instagram-mcp/profile/cookies.json              ║
║                                                                  ║
║  7. Run the MCP server again                                    ║
║                                                                  ║
║  Required cookies: sessionid, csrftoken                         ║
╚══════════════════════════════════════════════════════════════════╝
""")


def import_cookies_interactive() -> bool:
    """Interactive cookie import flow."""
    print("\nAttempting to import cookies from Brave browser...")

    cookies = extract_instagram_cookies()

    if not cookies:
        print("   Could not find Instagram cookies in Brave.")
        print("   Please log into Instagram in Brave first, then try again.")
        manual_cookie_import_guide()
        return False

    print(f"   Found {len(cookies)} Instagram cookies: {list(cookies.keys())}")

    # Check for required cookies
    required = {"sessionid", "csrftoken"}
    missing = required - set(cookies.keys())

    if missing:
        print(f"   Warning: Missing required cookies: {missing}")
        print("   You may need to log in again in Brave.")
        return False

    profile_dir = Path.home() / ".instagram-mcp" / "profile"

    if save_cookies_to_profile(cookies, profile_dir):
        print(f"   Cookies saved to: {profile_dir}/cookies.json")
        print("   You can now run the MCP server.")
        return True
    else:
        print("   Failed to save cookies.")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = import_cookies_interactive()
    exit(0 if success else 1)
