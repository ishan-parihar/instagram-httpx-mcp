"""
Instagram post scraping tools.

Uses innerText extraction for resilient post data capture
with support for individual posts and locations.
"""

import logging
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext

from instagram_mcp_server.constants import TOOL_TIMEOUT_SECONDS
from instagram_mcp_server.core.exceptions import AuthenticationError
from instagram_mcp_server.dependencies import get_ready_extractor, handle_auth_error
from instagram_mcp_server.error_handler import raise_tool_error

logger = logging.getLogger(__name__)


def register_post_tools(mcp: FastMCP) -> None:
    """Register all post-related tools with the MCP server."""

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Post Details",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"post", "scraping"},
    )
    async def get_post_details(
        post_url: str,
        include_comments: bool = False,
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        Get detailed post/reel information with structured data.

        Returns structured data including:
        - id, shortcode, url
        - caption, timestamp
        - media_type (reel, video, image, carousel)
        - video_url, thumbnail_url
        - engagement (likes, views, comments, shares)
        - audio info (for reels)

        Args:
            post_url: Full Instagram post URL
            ctx: FastMCP context for progress reporting
            include_comments: Whether to include comments in the response

        Returns:
            Dict with structured post data:
            {
                url, id, shortcode, media_type,
                caption, timestamp,
                video_url, thumbnail_url,
                engagement: {likes, views, comments, shares},
                audio: {audio_name, audio_artist},
                sections: {main: text} (legacy format)
            }
        """
        try:
            extractor = await get_ready_extractor(ctx, tool_name="get_post_details")

            logger.info(
                "Scraping post: %s (include_comments=%s)",
                post_url,
                include_comments,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Navigating to post"
            )

            # Navigate to the post page
            await extractor._navigate_to_page(post_url)

            await ctx.report_progress(
                progress=20, total=100, message="Extracting structured data"
            )

            # Extract structured data using new methods
            import asyncio

            # Wait for the post content to render (article or main region)
            try:
                await extractor._page.wait_for_selector(
                    'article, [role="main"], main',
                    timeout=10000,
                )
            except Exception:
                logger.debug(
                    "Post content selector not found, proceeding with available data"
                )

            # Additional short delay for dynamic content to settle
            await asyncio.sleep(1.5)

            og_data = await extractor.extract_og_metadata()
            video_url = await extractor.extract_video_url()
            thumbnail_url = await extractor.extract_thumbnail_url()
            engagement = await extractor.extract_engagement_from_meta()
            timestamp = await extractor.extract_timestamp()
            audio_info = await extractor.extract_audio_info()
            caption_text = await extractor.extract_caption_from_page()

            # Also get the raw text for backward compatibility
            extracted = await extractor.extract_page(post_url, section_name="main")

            # Parse post ID/shortcode from URL
            post_id = None
            for part in post_url.rstrip("/").split("/"):
                if part and part not in (
                    "https:",
                    "",
                    "www.instagram.com",
                    "p",
                    "reel",
                    "reels",
                    "tv",
                ):
                    post_id = part
                    break

            # Determine media type
            media_type = "image"
            if video_url or "og:video" in og_data:
                media_type = "reel" if "/reel/" in post_url else "video"

            sections: dict[str, str] = {}
            if extracted.text:
                sections["main"] = extracted.text

            if include_comments:
                # Extract comments from the page's comment section
                try:
                    comments_text = await extractor._page.evaluate("""() => {
                        const comments = [];
                        // Instagram comment sections use aria-label or data attributes
                        const commentElements = document.querySelectorAll('[data-pressable-container] li, [role="list"] li, ul[role="presentation"] li');
                        commentElements.forEach((el, i) => {
                            if (i < 20) {  // Limit to first 20 comments
                                const text = el.innerText?.trim();
                                if (text && text.length > 2) {
                                    comments.push(text);
                                }
                            }
                        });
                        return comments.join('\\n');
                    }""")
                    if comments_text:
                        sections["comments"] = comments_text
                except Exception as e:
                    logger.debug("Could not extract comments: %s", e)
                    sections["comments"] = "(Comments extraction unavailable)"

            result: dict[str, Any] = {
                "url": post_url,
                "id": post_id,
                "shortcode": post_id,
                "media_type": media_type,
                "caption": caption_text,
                "timestamp": timestamp,
                "video_url": video_url,
                "thumbnail_url": thumbnail_url,
                "engagement": engagement,
                "audio": audio_info,
                "sections": sections,
            }

            if extracted.references:
                result["references"] = {"main": extracted.references}

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_post_details")
        except Exception as e:
            raise_tool_error(e, "get_post_details")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Location Posts",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"post", "scraping", "location"},
    )
    async def get_location_posts(
        location_id: str,
        max_posts: int = 50,
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        Get posts tagged at a location.

        Extracts post links from the location grid page and returns them as
        structured references. Use `get_post_details` for individual post enrichment.

        Args:
            location_id: Instagram location ID
            ctx: FastMCP context for progress reporting
            max_posts: Maximum number of posts to load (default 50)

        Returns:
            Dict with url, sections (name -> raw text), references (post links),
            and total_posts count.
        """
        try:
            extractor = await get_ready_extractor(ctx, tool_name="get_location_posts")

            location_url = f"https://www.instagram.com/explore/locations/{location_id}/"

            logger.info(
                "Scraping location: %s (max_posts=%s)",
                location_id,
                max_posts,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Navigating to location page"
            )

            await extractor._navigate_to_page(location_url)

            from instagram_mcp_server.core.utils import scroll_to_bottom

            # Wait for the location grid to render
            try:
                await extractor._page.wait_for_selector(
                    'a[href*="/p/"], a[href*="/reel/"]',
                    timeout=10000,
                )
            except Exception:
                logger.debug("Location grid not fully loaded, proceeding anyway")

            # Scroll with timeout guard (max 25 seconds)
            import time

            scroll_start = time.time()
            scrolls = 0
            while scrolls < 10 and (time.time() - scroll_start) < 25:
                await scroll_to_bottom(extractor._page, pause_time=0.5, max_scrolls=1)
                scrolls += 1

            # Extract post links as structured references
            post_links = await extractor._extract_post_links(max_posts)

            # Extract text for backward compatibility
            raw_result = await extractor._extract_root_content(["main"])
            raw = raw_result["text"]
            from instagram_mcp_server.scraping.extractor import strip_instagram_noise

            cleaned = strip_instagram_noise(raw, page_type="grid") if raw else ""

            sections: dict[str, str] = {}
            if cleaned:
                sections["main"] = cleaned

            result: dict[str, Any] = {
                "url": location_url,
                "sections": sections,
                "references": {"posts": post_links} if post_links else {},
                "total_posts": len(post_links),
            }

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_location_posts")
        except Exception as e:
            raise_tool_error(e, "get_location_posts")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Hashtag Posts",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"post", "scraping", "hashtag"},
    )
    async def get_hashtag_posts(
        hashtag: str,
        max_posts: int = 50,
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        Get posts for a hashtag.

        Extracts post links from the hashtag grid page and returns them as
        structured references. Use `get_post_details` for individual post enrichment.

        Args:
            hashtag: Hashtag to search (without the # symbol)
            ctx: FastMCP context for progress reporting
            max_posts: Maximum number of posts to load (default 50)

        Returns:
            Dict with url, sections (name -> raw text), references (post links),
            and total_posts count.
        """
        try:
            extractor = await get_ready_extractor(ctx, tool_name="get_hashtag_posts")

            hashtag_url = f"https://www.instagram.com/explore/tags/{hashtag}/"

            logger.info(
                "Scraping hashtag: %s (max_posts=%s)",
                hashtag,
                max_posts,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Navigating to hashtag page"
            )

            await extractor._navigate_to_page(hashtag_url)

            from instagram_mcp_server.core.utils import scroll_to_bottom
            import asyncio

            # Wait for the main grid to render (look for post links)
            try:
                await extractor._page.wait_for_selector(
                    'a[href*="/p/"], a[href*="/reel/"]',
                    timeout=10000,
                )
            except Exception:
                logger.debug(
                    "No post links found on hashtag page after initial load: %s",
                    hashtag_url,
                )

            # Scroll with timeout guard (max 30 seconds) and verify posts load
            import time

            scroll_start = time.time()
            scrolls = 0
            while scrolls < 15 and (time.time() - scroll_start) < 30:
                await scroll_to_bottom(extractor._page, pause_time=0.3, max_scrolls=1)
                scrolls += 1
                await asyncio.sleep(0.3)
                # Check if we have enough post links
                post_count = await extractor._page.evaluate(
                    """() => document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]').length"""
                )
                if post_count >= max_posts:
                    break

            # Extract post links as structured references
            post_links = await extractor._extract_post_links(max_posts)

            # Extract text for backward compatibility
            raw_result = await extractor._extract_root_content(["main"])
            raw = raw_result["text"]
            from instagram_mcp_server.scraping.extractor import strip_instagram_noise

            cleaned = strip_instagram_noise(raw, page_type="grid") if raw else ""

            sections: dict[str, str] = {}
            if cleaned:
                sections["main"] = cleaned

            result: dict[str, Any] = {
                "url": hashtag_url,
                "sections": sections,
                "references": {"posts": post_links} if post_links else {},
                "total_posts": len(post_links),
            }

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_hashtag_posts")
        except Exception as e:
            raise_tool_error(e, "get_hashtag_posts")  # NoReturn
