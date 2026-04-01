"""
Instagram post scraping tools.

Uses innerText extraction for resilient post data capture
with support for individual posts, hashtags, and locations.
"""

import logging
from typing import Any

from fastmcp import Context, FastMCP

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
        exclude_args=["extractor"],
    )
    async def get_post_details(
        post_url: str,
        ctx: Context,
        include_comments: bool = False,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get detailed post information.

        Args:
            post_url: Full Instagram post URL
            ctx: FastMCP context for progress reporting
            include_comments: Whether to include comments in the response

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text in each section.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_post_details"
            )

            logger.info(
                "Scraping post: %s (include_comments=%s)",
                post_url,
                include_comments,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Navigating to post"
            )

            extracted = await extractor.extract_page(post_url, section_name="main")

            sections: dict[str, str] = {}
            if extracted.text:
                sections["main"] = extracted.text

            if include_comments and extracted.text:
                sections["comments"] = extracted.text

            result: dict[str, Any] = {"url": post_url, "sections": sections}

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
        title="Get Hashtag Posts",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"post", "scraping", "hashtag"},
        exclude_args=["extractor"],
    )
    async def get_hashtag_posts(
        hashtag: str,
        ctx: Context,
        max_posts: int = 50,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get posts for a hashtag.

        Args:
            hashtag: Hashtag to search (without the # symbol)
            ctx: FastMCP context for progress reporting
            max_posts: Maximum number of posts to load (default 50)

        Returns:
            Dict with url, sections (name -> raw text).
            The LLM should parse the raw text to extract individual posts.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_hashtag_posts"
            )

            hashtag_url = f"https://www.instagram.com/explore/tags/{hashtag}/"

            logger.info(
                "Scraping hashtag: %s (max_posts=%s)",
                hashtag,
                max_posts,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Navigating to hashtag page"
            )

            extracted = await extractor.extract_page(hashtag_url, section_name="main")

            sections: dict[str, str] = {}
            if extracted.text:
                sections["main"] = extracted.text

            result: dict[str, Any] = {"url": hashtag_url, "sections": sections}

            if extracted.references:
                result["references"] = {"main": extracted.references}

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_hashtag_posts")
        except Exception as e:
            raise_tool_error(e, "get_hashtag_posts")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Location Posts",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"post", "scraping", "location"},
        exclude_args=["extractor"],
    )
    async def get_location_posts(
        location_id: str,
        ctx: Context,
        max_posts: int = 50,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get posts tagged at a location.

        Args:
            location_id: Instagram location ID
            ctx: FastMCP context for progress reporting
            max_posts: Maximum number of posts to load (default 50)

        Returns:
            Dict with url, sections (name -> raw text).
            The LLM should parse the raw text to extract individual posts.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_location_posts"
            )

            location_url = f"https://www.instagram.com/explore/locations/{location_id}/"

            logger.info(
                "Scraping location: %s (max_posts=%s)",
                location_id,
                max_posts,
            )

            await ctx.report_progress(
                progress=0, total=100, message="Navigating to location page"
            )

            extracted = await extractor.extract_page(location_url, section_name="main")

            sections: dict[str, str] = {}
            if extracted.text:
                sections["main"] = extracted.text

            result: dict[str, Any] = {"url": location_url, "sections": sections}

            if extracted.references:
                result["references"] = {"main": extracted.references}

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_location_posts")
        except Exception as e:
            raise_tool_error(e, "get_location_posts")  # NoReturn
