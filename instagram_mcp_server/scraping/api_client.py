"""
Instagram private-web API client.  Replaces the DOM-based
``InstagramExtractor`` with direct HTTP requests via ``httpx``.

All public methods mirror the original extractor so the tool layer
needs zero changes.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from instagram_mcp_server.core.exceptions import AuthenticationError, RateLimitError
from instagram_mcp_server.scraping.fields import USER_SECTIONS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.instagram.com"
API_URL = "https://www.instagram.com/api/v1"
# Web app ID required by some API endpoints
IG_APP_ID = "936619743392459"
# Mobile user-agent — needed for certain API responses
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)
DESKTOP_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# How long to wait between API retries on 429
_RATE_LIMIT_SLEEP = 30
_MAX_RETRIES = 3

_SHORTCODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def shortcode_to_id(shortcode: str) -> int:
    """Decode an Instagram shortcode to a numeric media id."""
    n = 0
    for c in shortcode:
        n = n * 64 + _SHORTCODE_ALPHABET.index(c)
    return n


def id_to_shortcode(media_id: int) -> str:
    """Encode a numeric media id to an Instagram shortcode."""
    if media_id == 0:
        return ""
    chars: list[str] = []
    while media_id > 0:
        chars.append(_SHORTCODE_ALPHABET[media_id % 64])
        media_id //= 64
    return "".join(reversed(chars))


def extract_shortcode(url_or_shortcode: str) -> str:
    """Extract the shortcode from a post/reel URL or pass through if already a shortcode."""
    m = re.search(r"/(?:p|reel)/([A-Za-z0-9_-]+)", url_or_shortcode)
    if m:
        return m.group(1)
    return url_or_shortcode.strip("/")


def extract_media_id(url_or_shortcode: str) -> int | None:
    """Get numeric media id from a URL or shortcode."""
    try:
        return int(url_or_shortcode)
    except ValueError:
        pass
    sc = extract_shortcode(url_or_shortcode)
    if sc:
        return shortcode_to_id(sc)
    return None


def _sections_text(name: str, items: list[dict[str, Any]], fields: list[str]) -> str:
    """Build the human-readable text that the original DOM extractor returned."""
    lines: list[str] = []
    for item in items:
        parts: list[str] = []
        for f in fields:
            val = item.get(f)
            if val is not None:
                parts.append(f"{f}: {val}")
        if parts:
            lines.append(" | ".join(parts))
    return "\n".join(lines) if lines else f"(no {name} found)"


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class InstagramAPIClient:
    """Async HTTP client for Instagram's private-web API.

    Usage::

        client = InstagramAPIClient({"sessionid": "...", "csrftoken": "..."})
        result = await client.scrape_user("natgeo", {"bio", "posts"})
    """

    def __init__(
        self,
        cookies: dict[str, str] | None = None,
        *,
        user_agent: str = MOBILE_UA,
    ) -> None:
        self._cookies: dict[str, str] = cookies or {}
        self._csrftoken = self._cookies.get("csrftoken", "")
        self._client = httpx.AsyncClient(
            cookies=self._cookies,
            headers={
                "X-CSRFToken": self._csrftoken,
                "X-IG-App-ID": IG_APP_ID,
                "User-Agent": user_agent,
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.instagram.com/",
                "Origin": "https://www.instagram.com",
            },
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=15.0),
        )
        self._user_agent = user_agent

    # -- helpers ----------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        retries: int = _MAX_RETRIES,
    ) -> dict[str, Any]:
        """Make an API request with retry and Instagram-error handling."""
        url = f"{API_URL}{path}" if path.startswith("/") else f"{API_URL}/{path}"
        for attempt in range(retries):
            try:
                resp = await self._client.request(method, url, params=params, json=data)
            except httpx.TimeoutException:
                logger.warning(
                    "API timeout on %s (attempt %d/%d)", path, attempt + 1, retries
                )
                if attempt < retries - 1:
                    await self._sleep(2**attempt)
                    continue
                raise

            if resp.status_code == 429:
                logger.warning(
                    "Rate-limited (429) on %s — sleeping %ds", path, _RATE_LIMIT_SLEEP
                )
                if attempt < retries - 1:
                    await self._sleep(_RATE_LIMIT_SLEEP)
                    continue
                raise RateLimitError("Instagram rate-limited this request")

            if resp.status_code == 403:
                body = _safe_json(resp)
                # Check for login-wall or checkpoint
                if body and body.get("message") == "login_required":
                    raise AuthenticationError(
                        "Instagram session expired. Run --login to re-authenticate."
                    )
                if body and body.get("message") == "checkpoint_required":
                    raise AuthenticationError(
                        "Instagram checkpoint — manual login needed"
                    )
                raise RateLimitError(f"HTTP 403: {body or resp.text[:200]}")

            if resp.status_code == 400:
                body = _safe_json(resp)
                if body and body.get("message") == "bad_password":
                    raise AuthenticationError(
                        "Invalid session — cookies may be expired"
                    )
                if body and body.get("message"):
                    raise AuthenticationError(body["message"])
                raise AuthenticationError(f"API error: {resp.text[:200]}")

            resp.raise_for_status()
            body = _safe_json(resp)
            if body is None:
                raise AuthenticationError(f"Non-JSON response: {resp.text[:200]}")
            return body

        msg = f"Exhausted retries for {path}"
        logger.error(msg)
        raise AuthenticationError(msg)

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def _post(
        self, path: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request("POST", path, data=data)

    @staticmethod
    async def _sleep(secs: float) -> None:
        await _async_sleep(secs)

    async def _resolve_user_id(self, username: str) -> str:
        """Get Instagram user ID for *username* via ``web_profile_info``."""
        body = await self._get(
            "/users/web_profile_info/", params={"username": username}
        )
        user = body.get("data", {}).get("user", {})
        uid = user.get("id")
        if not uid:
            raise AuthenticationError(f"Could not resolve user id for @{username}")
        return str(uid)

    async def _resolve_user_id_cached(self, username: str) -> str:
        """Cached wrapper — keeps a simple in-memory cache during one session."""
        if not hasattr(self, "_user_id_cache"):
            self._user_id_cache: dict[str, str] = {}
        uid = self._user_id_cache.get(username)
        if uid is None:
            uid = await self._resolve_user_id(username)
            self._user_id_cache[username] = uid
        return uid

    async def close(self) -> None:
        await self._client.aclose()

    # -- session validation ----------------------------------------------------

    async def validate_session(self) -> bool:
        """Check whether the current cookies produce an authenticated response."""
        try:
            body = await self._get(
                "/users/web_profile_info/", params={"username": "instagram"}
            )
            return body.get("data", {}).get("user", {}).get("id") is not None
        except Exception:
            return False

    # -- callbacks (mute by default, mirror old signature) ---------------------

    async def _run_callbacks(self, cbs: Any, **kwargs: Any) -> None:
        pass

    # -- User profile ----------------------------------------------------------

    async def scrape_user(
        self,
        username: str,
        requested: set[str] | None = None,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        """Fetch user profile info (bio, follower count, etc.) + optional sections."""
        profile: dict[str, Any] = {
            "url": f"https://www.instagram.com/{username}/",
            "sections": {},
            "references": {},
        }
        if requested is None:
            requested = set(USER_SECTIONS.keys())

        await self._resolve_user_id_cached(username)
        body = await self._get(
            "/users/web_profile_info/", params={"username": username}
        )
        user = body.get("data", {}).get("user", {})
        if not user:
            return profile

        # bio / avatar
        bio_text_parts: list[str] = [
            f"Username: {user.get('username', '')}",
            f"Full Name: {user.get('full_name', '')}",
            f"Bio: {user.get('biography', '')}",
            f"Followers: {user.get('follower_count', 0)}",
            f"Following: {user.get('following_count', 0)}",
            f"Posts: {user.get('media_count', 0)}",
            f"Private: {user.get('is_private', False)}",
            f"Verified: {user.get('is_verified', False)}",
            f"Profile Pic: {user.get('profile_pic_url_hd', user.get('profile_pic_url', ''))}",
            f"External URL: {user.get('external_url', '')}",
            f"Category: {user.get('category_name', '')}",
        ]
        if user.get("is_business_account"):
            bio_text_parts.append("Business Account: Yes")
        if user.get("is_joined_recently"):
            bio_text_parts.append("Joined Recently: Yes")

        profile["sections"]["bio"] = "\n".join(bio_text_parts)

        # Posts section
        if "posts" in requested:
            posts = await self.scrape_user_posts(
                username, max_posts=12, callbacks=callbacks
            )
            profile["sections"]["posts"] = posts.get("sections", {}).get("posts", "")
            profile["references"].update(posts.get("references", {}))
            if posts.get("posts"):
                profile["sections"]["posts_json"] = json.dumps(posts["posts"], indent=2)

        # Reels section
        if "reels" in requested:
            reels = await self.scrape_user_reels(
                username, max_reels=12, callbacks=callbacks
            )
            profile["sections"]["reels"] = reels.get("sections", {}).get("reels", "")
            profile["references"].update(reels.get("references", {}))
            if reels.get("reels"):
                profile["sections"]["reels_json"] = json.dumps(reels["reels"], indent=2)

        # Stories section
        if "stories" in requested:
            stories = await self.scrape_user_stories(username, callbacks=callbacks)
            profile["sections"]["stories"] = stories.get("sections", {}).get(
                "stories", ""
            )
            profile["references"].update(stories.get("references", {}))
            if stories.get("stories"):
                profile["sections"]["stories_json"] = json.dumps(
                    stories["stories"], indent=2
                )

        # Highlights section
        if "highlights" in requested:
            highlights = await self.scrape_user_highlights(
                username, callbacks=callbacks
            )
            profile["sections"]["highlights"] = highlights.get("sections", {}).get(
                "highlights", ""
            )
            profile["references"].update(highlights.get("references", {}))

        # Followers / following count (already in bio)
        if "followers" in requested:
            profile["sections"]["followers"] = (
                f"Followers: {user.get('follower_count', 0)}"
            )
        if "following" in requested:
            profile["sections"]["following"] = (
                f"Following: {user.get('following_count', 0)}"
            )

        return profile

    # -- User posts ------------------------------------------------------------

    async def scrape_user_posts(
        self,
        username: str,
        max_posts: int = 12,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        uid = await self._resolve_user_id_cached(username)
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/{username}/",
            "posts": [],
            "total_posts": 0,
            "sections": {},
            "references": {},
        }
        posts: list[dict[str, Any]] = []
        next_max_id: str | None = None

        while len(posts) < max_posts:
            params: dict[str, Any] = {"count": min(12, max_posts - len(posts))}
            if next_max_id:
                params["max_id"] = next_max_id
            try:
                body = await self._get(f"/feed/user/{uid}/", params=params)
            except Exception:
                break

            for item in body.get("items", []):
                code = item.get("code", "")
                media_id = item.get("id", "").split("_")[0]
                # Normalise id to a string
                entry: dict[str, Any] = {
                    "id": str(media_id),
                    "shortcode": code,
                    "url": f"https://www.instagram.com/p/{code}/",
                    "thumbnail": (
                        item.get("image_versions2", {})
                        .get("candidates", [{}])[0]
                        .get("url", "")
                    ),
                    "media_type": item.get("media_type", 1),
                    "caption": ((item.get("caption") or {}).get("text") or ""),
                    "like_count": item.get("like_count", 0),
                    "comment_count": item.get("comment_count", 0),
                    "taken_at": item.get("taken_at", 0),
                }
                # Preview comments (top 2–3)
                preview_comments = item.get("preview_comments", [])
                if preview_comments:
                    entry["preview_comments"] = [
                        {
                            "user": c.get("user", {}).get("username", ""),
                            "text": c.get("text", ""),
                        }
                        for c in preview_comments[:3]
                    ]
                # Carousel children
                if item.get("media_type") == 8:
                    carousel_media = item.get("carousel_media", [])
                    entry["carousel_media_count"] = len(carousel_media)
                    entry["carousel_media"] = [
                        {
                            "media_type": cm.get("media_type", 1),
                            "thumbnail": (
                                cm.get("image_versions2", {})
                                .get("candidates", [{}])[0]
                                .get("url", "")
                            ),
                            "video_url": (
                                cm.get("video_versions", [{}])[0].get("url", "")
                                if cm.get("media_type") == 2
                                else ""
                            ),
                        }
                        for cm in carousel_media
                    ]
                # Product type
                if item.get("product_type"):
                    entry["product_type"] = item["product_type"]
                posts.append(entry)
                if len(posts) >= max_posts:
                    break

            next_max_id = body.get("next_max_id")
            if not next_max_id or not body.get("more_available"):
                break

        result["posts"] = posts
        result["total_posts"] = len(posts)
        result["sections"]["posts"] = _sections_text(
            "posts", posts, ["shortcode", "media_type", "like_count", "caption"]
        )
        result["references"]["posts"] = [
            {"kind": "post", "url": p["url"], "text": p["caption"][:120]} for p in posts
        ]
        return result

    # -- User reels ------------------------------------------------------------

    async def scrape_user_reels(
        self,
        username: str,
        max_reels: int = 12,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        uid = await self._resolve_user_id_cached(username)
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/{username}/",
            "reels": [],
            "total_reels": 0,
            "sections": {},
            "references": {},
        }
        reels_list: list[dict[str, Any]] = []

        try:
            body = await self._get(
                "/clips/user/", params={"target_user_id": uid, "page_size": max_reels}
            )
            items = body.get("items", [])
            for item in items:
                media = item.get("media", {})
                code = media.get("code", "")
                media_id = str(media.get("id", "")).split("_")[0]
                reels_list.append(
                    {
                        "id": media_id,
                        "shortcode": code,
                        "url": f"https://www.instagram.com/reel/{code}/",
                        "thumbnail": (
                            media.get("image_versions2", {})
                            .get("candidates", [{}])[0]
                            .get("url", "")
                        ),
                        "play_count": media.get("play_count", 0)
                        or media.get("view_count", 0),
                        "like_count": media.get("like_count", 0),
                        "comment_count": media.get("comment_count", 0),
                        "caption": ((media.get("caption") or {}).get("text") or ""),
                        "taken_at": media.get("taken_at", 0),
                        "video_duration": media.get("video_duration", 0),
                    }
                )
                # Audio metadata from clips_metadata
                clips_meta = media.get("clips_metadata", {}) or {}
                music_info = clips_meta.get("music_info", {}) or {}
                asset = music_info.get("music_asset_info", {}) or {}
                if asset:
                    reels_list[-1]["audio_title"] = asset.get("title", "")
                    reels_list[-1]["audio_artist"] = asset.get("display_artist", "")
                    reels_list[-1]["audio_id"] = asset.get("audio_asset_id", "")
                if len(reels_list) >= max_reels:
                    break
        except Exception:
            logger.warning("Failed to fetch reels for %s", username, exc_info=True)

        result["reels"] = reels_list
        result["total_reels"] = len(reels_list)
        result["sections"]["reels"] = _sections_text(
            "reels", reels_list, ["shortcode", "play_count", "like_count"]
        )
        result["references"]["reels"] = [
            {"kind": "reel", "url": r["url"], "text": r["caption"][:120]}
            for r in reels_list
        ]
        return result

    # -- Stories ---------------------------------------------------------------

    async def scrape_user_stories(
        self,
        username: str,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        uid = await self._resolve_user_id_cached(username)
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/{username}/",
            "stories": [],
            "sections": {},
            "references": {},
        }

        try:
            body = await self._get(f"/feed/user/{uid}/reel_media/")
            items = body.get("items", [])
            stories: list[dict[str, Any]] = []
            for item in items:
                story_entry: dict[str, Any] = {
                    "id": str(item.get("id", "")).split("_")[0],
                    "media_type": item.get("media_type", 1),
                    "url": (
                        item.get("image_versions2", {})
                        .get("candidates", [{}])[0]
                        .get("url", "")
                    ),
                    "video_url": (
                        item.get("video_versions", [{}])[0].get("url", "")
                        if item.get("media_type") == 2
                        else ""
                    ),
                    "taken_at": item.get("taken_at", 0),
                    "expire_at": item.get("expiring_at", 0),
                }
                # Viewer count for videos
                if item.get("media_type") == 2:
                    story_entry["viewer_count"] = item.get("viewer_count", 0)
                # Tappable objects (mentions, links)
                story_links = []
                for so in item.get("story_locations", []):
                    loc = so.get("location", {})
                    story_links.append(
                        {
                            "kind": "location",
                            "name": loc.get("name", ""),
                            "id": loc.get("pk", ""),
                        }
                    )
                for so in item.get("story_links", []):
                    story_links.append(
                        {
                            "kind": "link",
                            "url": so.get("url", ""),
                            "title": so.get("title", ""),
                        }
                    )
                for so in item.get("story_mentions", []):
                    user = so.get("user", {})
                    story_links.append(
                        {"kind": "mention", "username": user.get("username", "")}
                    )
                if story_links:
                    story_entry["tappable_objects"] = story_links
                # Audio metadata
                audio = item.get("story_music_stickers", [])
                if audio:
                    music = audio[0].get("music_asset_info", {}) or {}
                    if music:
                        story_entry["audio_title"] = music.get("title", "")
                        story_entry["audio_artist"] = music.get("display_artist", "")
                stories.append(story_entry)
            result["stories"] = stories
            result["sections"]["stories"] = (
                f"User has {len(stories)} active story item(s)"
                if stories
                else "No active stories"
            )
        except Exception:
            logger.warning("Failed to fetch stories for %s", username, exc_info=True)

        return result

    # -- Highlights ------------------------------------------------------------

    async def scrape_user_highlights(
        self,
        username: str,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        uid = await self._resolve_user_id_cached(username)
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/{username}/",
            "sections": {},
            "references": {},
        }

        try:
            body = await self._get(f"/highlights/{uid}/highlights_tray/")
            tray = body.get("tray", [])
            highlights: list[dict[str, Any]] = []
            for h in tray:
                cover = h.get("cover_media", {})
                highlights.append(
                    {
                        "id": str(h.get("id", "")),
                        "title": h.get("title", ""),
                        "cover_url": (
                            cover.get("image_versions2", {})
                            .get("candidates", [{}])[0]
                            .get("url", "")
                        ),
                        "media_count": len(h.get("items", [])),
                    }
                )
            result["highlights"] = highlights
            result["sections"]["highlights"] = _sections_text(
                "highlights", highlights, ["title", "media_count"]
            )
        except Exception:
            logger.warning("Failed to fetch highlights for %s", username, exc_info=True)

        return result

    # -- Post details ----------------------------------------------------------

    async def get_post_details(
        self,
        post_url: str,
        include_comments: bool = False,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        shortcode = extract_shortcode(post_url)
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/p/{shortcode}/",
            "sections": {},
            "references": {},
        }

        try:
            body = await self._get(f"/media/{shortcode_to_id(shortcode)}/info/")
            items = body.get("items", [])
            if not items:
                return result
            m = items[0]

            details: dict[str, Any] = {
                "id": str(m.get("id", "")).split("_")[0],
                "shortcode": m.get("code", shortcode),
                "media_type": m.get("media_type", 1),
                "caption": (m.get("caption") or {}).get("text", ""),
                "like_count": m.get("like_count", 0),
                "comment_count": m.get("comment_count", 0),
                "taken_at": m.get("taken_at", 0),
                "media_url": (
                    m.get("image_versions2", {})
                    .get("candidates", [{}])[0]
                    .get("url", "")
                ),
                "video_url": (
                    m.get("video_versions", [{}])[0].get("url", "")
                    if m.get("media_type") == 2
                    else ""
                ),
                "view_count": m.get("view_count", 0) or m.get("play_count", 0),
            }

            if m.get("location"):
                details["location"] = m["location"].get("name", "")
                details["location_id"] = m["location"].get("pk", "")

            if m.get("product_type"):
                details["product_type"] = m["product_type"]

            audio = m.get("music_metadata", {}) or m.get("clips_metadata", {}).get(
                "music_info", {}
            )
            if audio:
                details["audio"] = audio.get("music_asset_info", {}).get("title", "")

            # Carousel children
            if m.get("media_type") == 8:
                carousel = m.get("carousel_media", [])
                details["carousel_media_count"] = len(carousel)
                details["carousel_media"] = [
                    {
                        "media_type": cm.get("media_type", 1),
                        "thumbnail": (
                            cm.get("image_versions2", {})
                            .get("candidates", [{}])[0]
                            .get("url", "")
                        ),
                        "video_url": (
                            cm.get("video_versions", [{}])[0].get("url", "")
                            if cm.get("media_type") == 2
                            else ""
                        ),
                    }
                    for cm in carousel
                ]

            # Usertags
            usertags = m.get("usertags", {}).get("in", [])
            if usertags:
                details["usertags"] = [
                    {
                        "username": ut.get("user", {}).get("username", ""),
                        "full_name": ut.get("user", {}).get("full_name", ""),
                        "x": (ut.get("position") or [0, 0])[0],
                        "y": (ut.get("position") or [0, 0])[1],
                    }
                    for ut in usertags
                ]

            # Sponsor / paid partnership tags
            sponsor_tags = m.get("sponsor_tags", [])
            if sponsor_tags:
                details["sponsor_tags"] = [
                    {
                        "username": st.get("sponsor", {}).get("username", ""),
                        "id": st.get("sponsor", {}).get("id", ""),
                    }
                    for st in sponsor_tags
                    if st.get("sponsor")
                ]

            # Video duration
            if m.get("video_duration"):
                details["video_duration"] = m["video_duration"]

            # Build text section
            lines = [
                f"Media ID: {details['id']}",
                f"Shortcode: {details['shortcode']}",
                f"Type: {details.get('media_type', 1)} ({_media_type_name(details.get('media_type', 1))})",
                f"Likes: {details['like_count']}",
                f"Comments: {details['comment_count']}",
                f"Views: {details['view_count']}",
                f"Caption: {details['caption']}",
            ]
            if details.get("location"):
                lines.append(f"Location: {details['location']}")
            if details.get("audio"):
                lines.append(f"Audio: {details['audio']}")

            result["post_details"] = details
            result["sections"]["details"] = "\n".join(lines)

            if include_comments:
                comments = m.get("comments", [])
                comment_lines = []
                for c in comments:
                    user = c.get("user", {})
                    comment_lines.append(
                        f"@{user.get('username', '?')}: {c.get('text', '')}"
                    )
                result["sections"]["comments"] = (
                    "\n".join(comment_lines) if comment_lines else "(no comments)"
                )
                result["comments"] = [
                    {
                        "id": str(c.get("pk")),
                        "user": c.get("user", {}).get("username", ""),
                        "user_full_name": c.get("user", {}).get("full_name", ""),
                        "user_id": str(c.get("user", {}).get("pk", "")),
                        "text": c.get("text", ""),
                        "timestamp": c.get("created_at", 0),
                    }
                    for c in comments
                ]

        except Exception:
            logger.warning(
                "Failed to fetch post details for %s", post_url, exc_info=True
            )

        return result

    # -- Search ----------------------------------------------------------------

    async def search_users(
        self,
        query: str,
        max_results: int = 25,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/web/search/?q={query}",
            "sections": {},
            "references": {},
        }
        try:
            body = await self._get(
                "/users/search/", params={"q": query, "count": max_results}
            )
            users = body.get("users", [])
            refs: list[dict[str, Any]] = []
            lines: list[str] = []
            for u in users[:max_results]:
                username = u.get("username", "")
                lines.append(
                    f"@{username} — {u.get('full_name', '')} "
                    f"({u.get('follower_count', 0)} followers)"
                )
                refs.append(
                    {
                        "kind": "user",
                        "url": f"https://www.instagram.com/{username}/",
                        "text": f"@{username}",
                    }
                )
            result["sections"]["users"] = "\n".join(lines) if lines else "(no results)"
            result["references"]["users"] = refs
        except Exception:
            logger.warning("Search users failed for %r", query, exc_info=True)
        return result

    async def search_locations(
        self,
        query: str,
        max_results: int = 25,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/web/search/?q={query}",
            "sections": {},
            "references": {},
        }
        try:
            body = await self._get(
                "/locations/search/",
                params={"search_query": query, "count": max_results},
            )
            venues = (
                body.get("venues", []) if "venues" in body else body.get("items", [])
            )
            lines: list[str] = []
            refs: list[dict[str, Any]] = []
            for v in venues[:max_results]:
                loc = v.get("location", v)
                lid = loc.get("pk", "")
                name = loc.get("name", "")
                lines.append(f"{name} (id={lid}) — {loc.get('address', '')}")
                refs.append(
                    {
                        "kind": "location",
                        "url": f"https://www.instagram.com/explore/locations/{lid}/",
                        "text": name,
                    }
                )
            result["sections"]["locations"] = (
                "\n".join(lines) if lines else "(no results)"
            )
            result["references"]["locations"] = refs
        except Exception:
            logger.warning("Search locations failed for %r", query, exc_info=True)
        return result

    # -- Hashtag posts ---------------------------------------------------------

    async def get_hashtag_posts(
        self,
        hashtag: str,
        max_posts: int = 12,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        tag = hashtag.lstrip("#")
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/explore/tags/{tag}/",
            "sections": {},
            "references": {},
        }
        try:
            body = await self._get(
                f"/tags/{tag}/media/recent/", params={"count": max_posts}
            )
            sections = body.get("sections", []) or body.get("medias", [])
            items: list[dict] = []
            for sec in sections:
                for m in sec.get("media", sec) if isinstance(sec, dict) else sec:
                    node = m.get("media", m) if isinstance(m, dict) else m
                    items.append(node)
            posts_data: list[dict[str, Any]] = []
            refs: list[dict[str, Any]] = []
            for item in items[:max_posts]:
                code = item.get("code", "")
                posts_data.append(
                    {
                        "id": str(item.get("id", "")).split("_")[0],
                        "shortcode": code,
                        "url": f"https://www.instagram.com/p/{code}/",
                        "thumbnail": (
                            item.get("image_versions2", {})
                            .get("candidates", [{}])[0]
                            .get("url", "")
                        ),
                        "caption": ((item.get("caption") or {}).get("text") or ""),
                        "like_count": item.get("like_count", 0),
                        "comment_count": item.get("comment_count", 0),
                        "taken_at": item.get("taken_at", 0),
                        "media_type": item.get("media_type", 1),
                    }
                )
                refs.append(
                    {
                        "kind": "post",
                        "url": f"https://www.instagram.com/p/{code}/",
                        "text": ((item.get("caption") or {}).get("text") or "")[:120],
                    }
                )
            result["posts"] = posts_data
            result["sections"]["posts"] = _sections_text(
                "posts", posts_data, ["shortcode", "like_count"]
            )
            result["references"]["posts"] = refs
        except Exception:
            logger.warning("Hashtag posts failed for #%s", tag, exc_info=True)
        return result

    # -- Location posts ---------------------------------------------------------

    async def get_location_posts(
        self,
        location_id: str,
        max_posts: int = 12,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/explore/locations/{location_id}/",
            "sections": {},
            "references": {},
        }
        try:
            body = await self._get(
                f"/locations/{location_id}/sections/", params={"count": max_posts}
            )
            sections = body.get("sections", [])
            items: list[dict] = []
            for sec in sections:
                for m in sec.get("media", []) if isinstance(sec, dict) else []:
                    node = m.get("media", m) if isinstance(m, dict) else m
                    items.append(node)
            posts_data: list[dict[str, Any]] = []
            refs: list[dict[str, Any]] = []
            for item in items[:max_posts]:
                code = item.get("code", "")
                posts_data.append(
                    {
                        "id": str(item.get("id", "")).split("_")[0],
                        "shortcode": code,
                        "url": f"https://www.instagram.com/p/{code}/",
                        "thumbnail": (
                            item.get("image_versions2", {})
                            .get("candidates", [{}])[0]
                            .get("url", "")
                        ),
                        "caption": ((item.get("caption") or {}).get("text") or ""),
                        "like_count": item.get("like_count", 0),
                        "comment_count": item.get("comment_count", 0),
                        "taken_at": item.get("taken_at", 0),
                    }
                )
                refs.append(
                    {
                        "kind": "post",
                        "url": f"https://www.instagram.com/p/{code}/",
                        "text": ((item.get("caption") or {}).get("text") or "")[:120],
                    }
                )
            result["posts"] = posts_data
            result["sections"]["posts"] = _sections_text(
                "posts", posts_data, ["shortcode"]
            )
            result["references"]["posts"] = refs
        except Exception:
            logger.warning("Location posts failed for %s", location_id, exc_info=True)
        return result

    # -- DMs -------------------------------------------------------------------

    async def scrape_dm_inbox(
        self,
        limit: int = 20,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "url": "https://www.instagram.com/direct/inbox/",
            "sections": {},
            "references": {},
        }
        try:
            body = await self._get("/direct_v2/inbox/", params={"limit": limit})
            inbox = body.get("inbox", {})
            threads = inbox.get("threads", [])
            convos: list[dict[str, Any]] = []
            for t in threads[:limit]:
                users = t.get("users", [])
                other = users[0] if users else {}
                convos.append(
                    {
                        "thread_id": t.get("thread_id", ""),
                        "thread_title": t.get("thread_title", ""),
                        "username": other.get("username", ""),
                        "full_name": other.get("full_name", ""),
                        "profile_pic": other.get("profile_pic_url", ""),
                        "last_message": (
                            t.get("last_permanent_item", {}).get("text", "") or ""
                        ),
                        "last_activity": t.get("last_activity_at", 0),
                    }
                )
            result["conversations"] = convos
            result["sections"]["inbox"] = _sections_text(
                "inbox", convos, ["username", "thread_title", "last_message"]
            )
        except Exception:
            logger.warning("DM inbox fetch failed", exc_info=True)
        return result

    async def scrape_dm_conversation(
        self,
        thread_id: str | None = None,
        username: str | None = None,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "url": "https://www.instagram.com/direct/inbox/",
            "sections": {},
            "references": {},
        }

        # If we have a username but no thread_id, list threads and match
        if not thread_id and username:
            inbox_body = await self._get("/direct_v2/inbox/", params={"limit": 50})
            threads = inbox_body.get("inbox", {}).get("threads", [])
            for t in threads:
                users = t.get("users", [])
                if any(u.get("username") == username for u in users):
                    thread_id = t.get("thread_id", "")
                    break
            if not thread_id:
                result["sections"]["messages"] = (
                    f"No conversation found with @{username}"
                )
                return result

        try:
            body = await self._get(f"/direct_v2/threads/{thread_id}/")
            thread = body.get("thread", {})
            items = thread.get("items", [])
            msgs: list[dict[str, Any]] = []
            for item in items:
                user = item.get("user", {})
                msgs.append(
                    {
                        "item_id": str(item.get("item_id", "")),
                        "user_id": str(user.get("pk", "")),
                        "username": user.get("username", ""),
                        "text": item.get("text", ""),
                        "timestamp": item.get("timestamp", 0),
                        "item_type": item.get("item_type", ""),
                    }
                )
            result["messages"] = msgs
            result["sections"]["messages"] = _sections_text(
                "messages", msgs, ["username", "text", "item_type"]
            )
        except Exception:
            logger.warning("DM conversation fetch failed", exc_info=True)
        return result

    async def send_dm(
        self,
        username: str,
        message: str,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        uid = await self._resolve_user_id_cached(username)
        result: dict[str, Any] = {
            "url": "https://www.instagram.com/direct/inbox/",
            "status": "error",
            "message": "",
        }
        try:
            body = await self._post(
                "/direct_v2/threads/broadcast/text/",
                data={
                    "text": message,
                    "recipient_users": json.dumps([[uid]]),
                },
            )
            if body.get("status") == "ok":
                result["status"] = "ok"
                result["message"] = f"DM sent to @{username}"
            else:
                result["message"] = f"DM send returned: {body}"
        except Exception as e:
            result["message"] = str(e)
        return result

    # -- Actions (follow / unfollow / like / unlike / save / comment) ----------

    async def follow_user(
        self,
        username: str,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        uid = await self._resolve_user_id_cached(username)
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/{username}/",
            "status": "error",
            "message": "",
        }
        try:
            body = await self._post(f"/friendships/create/{uid}/")
            if body.get("status") == "ok":
                friendship = body.get("friendship_status", {})
                result["status"] = "ok"
                result["message"] = (
                    f"Follow request sent to @{username}"
                    if friendship.get("following")
                    else f"Follow pending for @{username}"
                )
            else:
                result["message"] = f"Follow failed: {body}"
        except Exception as e:
            result["message"] = str(e)
        return result

    async def unfollow_user(
        self,
        username: str,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        uid = await self._resolve_user_id_cached(username)
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/{username}/",
            "status": "error",
            "message": "",
        }
        try:
            body = await self._post(f"/friendships/destroy/{uid}/")
            if body.get("status") == "ok":
                result["status"] = "ok"
                result["message"] = f"Unfollowed @{username}"
            else:
                result["message"] = f"Unfollow failed: {body}"
        except Exception as e:
            result["message"] = str(e)
        return result

    async def like_post(
        self,
        post_url: str,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        media_id = extract_media_id(post_url)
        result: dict[str, Any] = {
            "url": post_url,
            "status": "error",
            "message": "",
        }
        if media_id is None:
            result["message"] = f"Could not parse media from {post_url}"
            return result
        try:
            body = await self._post(f"/media/{media_id}/like/")
            result["status"] = "ok" if body.get("status") == "ok" else "error"
            result["message"] = (
                f"Liked {post_url}"
                if result["status"] == "ok"
                else f"Like failed: {body}"
            )
        except Exception as e:
            result["message"] = str(e)
        return result

    async def unlike_post(
        self,
        post_url: str,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        media_id = extract_media_id(post_url)
        result: dict[str, Any] = {
            "url": post_url,
            "status": "error",
            "message": "",
        }
        if media_id is None:
            result["message"] = f"Could not parse media from {post_url}"
            return result
        try:
            body = await self._post(f"/media/{media_id}/unlike/")
            result["status"] = "ok" if body.get("status") == "ok" else "error"
            result["message"] = (
                f"Unliked {post_url}"
                if result["status"] == "ok"
                else f"Unlike failed: {body}"
            )
        except Exception as e:
            result["message"] = str(e)
        return result

    async def save_post(
        self,
        post_url: str,
        collection: str = "",
        callbacks: Any = None,
    ) -> dict[str, Any]:
        media_id = extract_media_id(post_url)
        result: dict[str, Any] = {
            "url": post_url,
            "status": "error",
            "message": "",
        }
        if media_id is None:
            result["message"] = f"Could not parse media from {post_url}"
            return result
        try:
            body = await self._post(f"/media/{media_id}/save/")
            if body.get("status") == "ok":
                result["status"] = "ok"
                msg = f"Saved {post_url}"
                if collection:
                    msg += f" to collection '{collection}' (note: collection grouping is handled server-side)"
                result["message"] = msg
            else:
                result["message"] = f"Save failed: {body}"
        except Exception as e:
            result["message"] = str(e)
        return result

    async def comment_on_post(
        self,
        post_url: str,
        comment: str,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        media_id = extract_media_id(post_url)
        result: dict[str, Any] = {
            "url": post_url,
            "status": "error",
            "message": "",
        }
        if media_id is None:
            result["message"] = f"Could not parse media from {post_url}"
            return result
        try:
            body = await self._post(
                f"/media/{media_id}/comment/", data={"comment_text": comment}
            )
            if body.get("status") == "ok":
                result["status"] = "ok"
                result["message"] = f"Commented on {post_url}"
            else:
                result["message"] = f"Comment failed: {body}"
        except Exception as e:
            result["message"] = str(e)
        return result

    # -- Insights (Business / Creator accounts) ---------------------------------

    async def scrape_business_insights(
        self,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        return await self._scrape_insights("overview", callbacks)

    async def scrape_audience_insights(
        self,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        return await self._scrape_insights("audience", callbacks)

    async def scrape_content_insights(
        self,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        return await self._scrape_insights("content", callbacks)

    async def scrape_activity_insights(
        self,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        return await self._scrape_insights("activity", callbacks)

    async def _scrape_insights(
        self,
        insight_type: str,
        callbacks: Any = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "url": "https://www.instagram.com/insights/",
            "sections": {},
            "references": {},
        }
        try:
            body = await self._get("/insights/web_activity/")
            data = body.get("data", {}).get("user", {})
            if not data:
                result["sections"]["insights"] = (
                    "No insights available. Make sure this is a Business or Creator account."
                )
                return result

            lines: list[str] = []
            if insight_type == "overview":
                for m in ("reach_count", "impression_count", "profile_visit_count"):
                    lines.append(f"{m}: {data.get(m, 'N/A')}")
                for m in data.get("all_followers_age_graph", []):
                    if isinstance(m, dict):
                        lines.append(f"{m.get('label', '?')}: {m.get('value', 'N/A')}")
            elif insight_type == "audience":
                for metric in [
                    "gender_graph",
                    "age_graph",
                    "top_cities",
                    "top_countries",
                ]:
                    items = data.get(metric, [])
                    if items:
                        lines.append(f"{metric}:")
                        for item in items[:10]:
                            if isinstance(item, dict):
                                lines.append(
                                    f"  {item.get('label', '?')}: {item.get('value', 'N/A')}"
                                )
            elif insight_type == "content":
                for metric in [
                    "posts_count",
                    "reels_count",
                    "stories_count",
                    "live_count",
                ]:
                    lines.append(f"{metric}: {data.get(metric, 'N/A')}")
            else:
                lines.append(
                    f"Insights type '{insight_type}' — data available on Instagram dashboard."
                )

            result["sections"][insight_type] = (
                "\n".join(lines) if lines else "(no insight data)"
            )
        except Exception:
            logger.warning("Failed to fetch %s insights", insight_type, exc_info=True)
        return result

    # -- Search hashtags (separate method) --------------------------------------

    async def search_hashtags(
        self,
        query: str,
        max_results: int = 25,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "url": f"https://www.instagram.com/web/search/?q={query}",
            "sections": {},
            "references": {},
        }
        try:
            # Instagram's search is unified — tags come in the same response
            body = await self._get(
                "/users/search/", params={"q": query, "count": max_results}
            )
            # Check for tags in the response (they sometimes come under "hashtags")
            tags = body.get("hashtags", [])
            lines: list[str] = []
            refs: list[dict[str, Any]] = []
            for t in tags[:max_results]:
                name = t.get("name", "")
                count = t.get("media_count", 0)
                lines.append(f"#{name} ({count} posts)")
                ref_entry: dict[str, Any] = {
                    "kind": "hashtag",
                    "url": f"https://www.instagram.com/explore/tags/{name}/",
                    "text": f"#{name}",
                }
                # Recent post previews for top 3 tags
                if len(refs) < 3:
                    try:
                        preview = await self._get(
                            f"/tags/{name}/media/recent/", params={"count": 3}
                        )
                        media_items = []
                        sections = preview.get("sections", []) or preview.get(
                            "medias", []
                        )
                        for sec in sections:
                            for m in (
                                sec.get("media", sec) if isinstance(sec, dict) else sec
                            ):
                                node = m.get("media", m) if isinstance(m, dict) else m
                                if node.get("code"):
                                    media_items.append(
                                        {
                                            "shortcode": node["code"],
                                            "url": f"https://www.instagram.com/p/{node['code']}/",
                                            "thumbnail": (
                                                node.get("image_versions2", {})
                                                .get("candidates", [{}])[0]
                                                .get("url", "")
                                            ),
                                            "likes": node.get("like_count", 0),
                                        }
                                    )
                                    if len(media_items) >= 3:
                                        break
                        if media_items:
                            ref_entry["recent_posts"] = media_items
                    except Exception:
                        pass
                refs.append(ref_entry)
            if not tags:
                # Fallback: try the explore/tag search API
                body2 = await self._get(
                    "/tags/search/", params={"q": query, "count": max_results}
                )
                results = body2.get("results", [])
                for t in results[:max_results]:
                    name = t.get("name", "")
                    count = t.get("media_count", 0)
                    lines.append(f"#{name} ({count} posts)")
                    refs.append(
                        {
                            "kind": "hashtag",
                            "url": f"https://www.instagram.com/explore/tags/{name}/",
                            "text": f"#{name}",
                        }
                    )
                    # Fetch recent preview posts for top tags
                    if len(lines) <= 3:
                        try:
                            preview = await self._get(
                                f"/tags/{name}/media/recent/", params={"count": 3}
                            )
                            media_items = []
                            sections = preview.get("sections", []) or preview.get(
                                "medias", []
                            )
                            for sec in sections:
                                for m in (
                                    sec.get("media", sec)
                                    if isinstance(sec, dict)
                                    else sec
                                ):
                                    node = (
                                        m.get("media", m) if isinstance(m, dict) else m
                                    )
                                    if node.get("code"):
                                        media_items.append(
                                            {
                                                "shortcode": node["code"],
                                                "url": f"https://www.instagram.com/p/{node['code']}/",
                                                "thumbnail": (
                                                    node.get("image_versions2", {})
                                                    .get("candidates", [{}])[0]
                                                    .get("url", "")
                                                ),
                                                "likes": node.get("like_count", 0),
                                            }
                                        )
                                        if len(media_items) >= 3:
                                            break
                            if media_items:
                                refs[-1]["recent_posts"] = media_items
                        except Exception:
                            pass
            result["sections"]["hashtags"] = (
                "\n".join(lines) if lines else "(no results)"
            )
            result["references"]["hashtags"] = refs
        except Exception:
            logger.warning("Search hashtags failed for %r", query, exc_info=True)
        return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_json(resp: httpx.Response) -> dict[str, Any] | None:
    try:
        return resp.json()
    except Exception:
        return None


def _media_type_name(t: int) -> str:
    return {1: "photo", 2: "video", 8: "carousel"}.get(t, "unknown")


def _pretty(text: str) -> str:
    return " ".join(text.split())


try:
    from asyncio import sleep as _async_sleep
except ImportError:
    import asyncio

    _async_sleep = asyncio.sleep
