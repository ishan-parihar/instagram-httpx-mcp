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
        - media_type (1=image, 2=video, 8=carousel)
        - media_url, video_url, thumbnail_url
        - engagement (likes, views, comments)
        - audio info (for reels)
        - location, usertags, sponsor_tags
        - carousel children
        - optional comments

        Args:
            post_url: Full Instagram post URL
            include_comments: Whether to include comments in the response
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with post details from the Instagram API.
        """
        try:
            extractor = await get_ready_extractor(ctx, tool_name="get_post_details")

            logger.info(
                "Fetching post details: %s (include_comments=%s)",
                post_url,
                include_comments,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Fetching post details"
            )

            result = await extractor.get_post_details(
                post_url, include_comments=include_comments
            )

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

            logger.info(
                "Fetching location posts: %s (max_posts=%s)",
                location_id,
                max_posts,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Fetching location posts"
            )

            result = await extractor.get_location_posts(
                location_id, max_posts=max_posts
            )

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

            logger.info(
                "Fetching hashtag posts: %s (max_posts=%s)",
                hashtag,
                max_posts,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Fetching hashtag posts"
            )

            result = await extractor.get_hashtag_posts(
                hashtag, max_posts=max_posts
            )

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_hashtag_posts")
        except Exception as e:
            raise_tool_error(e, "get_hashtag_posts")  # NoReturn
