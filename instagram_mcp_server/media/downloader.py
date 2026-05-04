"""Shared media download utility using httpx with Instagram cookie authentication."""

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


async def download_media(
    media_url: str,
    output_path: str | Path,
    cookies: dict[str, str] | None = None,
    *,
    timeout: float = 60.0,
) -> bool:
    """
    Download media from Instagram CDN with cookie auth.

    Args:
        media_url: The CDN URL to download
        output_path: Where to save the file
        cookies: Instagram session cookies dict for auth
        timeout: Request timeout in seconds

    Returns:
        True if download succeeded, False otherwise
    """
    try:
        headers: dict[str, str] = {
            "Referer": "https://www.instagram.com/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        }
        if cookies:
            cookie_header = "; ".join(
                f"{k}={v}" for k, v in cookies.items() if v
            )
            if cookie_header:
                headers["Cookie"] = cookie_header

        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            async with client.stream("GET", media_url, timeout=timeout) as response:
                if response.status_code != 200:
                    logger.error("Download failed: HTTP %d for %s", response.status_code, media_url[:80])
                    return False
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
        logger.info("Downloaded: %s", output_path.name)
        return True
    except Exception as e:
        logger.error("Download error: %s", e)
        return False


async def download_bytes(
    media_url: str,
    cookies: dict[str, str] | None = None,
    *,
    timeout: float = 30.0,
) -> bytes | None:
    """
    Download media bytes (for in-memory processing like Gemini upload).

    Args:
        media_url: The CDN URL to download
        cookies: Instagram session cookies dict for auth
        timeout: Request timeout in seconds

    Returns:
        Raw bytes or None on failure
    """
    try:
        headers: dict[str, str] = {
            "Referer": "https://www.instagram.com/",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        }
        if cookies:
            cookie_header = "; ".join(
                f"{k}={v}" for k, v in cookies.items() if v
            )
            if cookie_header:
                headers["Cookie"] = cookie_header

        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            response = await client.get(media_url, timeout=timeout)
            if response.status_code == 200:
                return response.content
            logger.warning("Download returned HTTP %d for %s", response.status_code, media_url[:80])
            return None
    except Exception as e:
        logger.error("Download error: %s", e)
        return None
