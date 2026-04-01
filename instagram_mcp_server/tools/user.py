"""
Instagram user profile scraping tools.

Provides tools for fetching user profiles, posts, reels,
stories, and highlights via innerText extraction.
"""

import logging
from typing import Any

from fastmcp import Context, FastMCP

from instagram_mcp_server.callbacks import MCPContextProgressCallback
from instagram_mcp_server.constants import TOOL_TIMEOUT_SECONDS
from instagram_mcp_server.core.exceptions import AuthenticationError
from instagram_mcp_server.dependencies import get_ready_extractor, handle_auth_error
from instagram_mcp_server.error_handler import raise_tool_error
from instagram_mcp_server.scraping import parse_user_sections

logger = logging.getLogger(__name__)


def register_user_tools(mcp: FastMCP) -> None:
    """Register all user-related tools with the MCP server."""

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get User Profile",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"user", "scraping"},
        exclude_args=["extractor"],
    )
    async def get_user_profile(
        username: str,
        ctx: Context,
        sections: str | None = None,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get an Instagram user's profile.

        Args:
            username: Instagram username (e.g., "instagram", "natgeo")
            ctx: FastMCP context for progress reporting
            sections: Comma-separated list of extra sections to scrape.
                The main profile page is always included.
                Available sections: posts, reels, tagged, followers, following
                Examples: "posts,reels", "tagged", "followers,following"
                Default (None) scrapes only the main profile page.

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            Sections may be absent if extraction yielded no content for that page.
            Includes unknown_sections list when unrecognised names are passed.
            The LLM should parse the raw text in each section.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_user_profile"
            )
            requested, unknown = parse_user_sections(sections)

            logger.info(
                "Scraping user profile: %s (sections=%s)",
                username,
                sections,
            )

            cb = MCPContextProgressCallback(ctx)
            result = await extractor.scrape_user(username, requested, callbacks=cb)

            if unknown:
                result["unknown_sections"] = unknown

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_user_profile")
        except Exception as e:
            raise_tool_error(e, "get_user_profile")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get User Posts",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"user", "scraping"},
        exclude_args=["extractor"],
    )
    async def get_user_posts(
        username: str,
        ctx: Context,
        max_posts: int = 50,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get an Instagram user's posts with engagement metrics.

        Args:
            username: Instagram username (e.g., "instagram", "natgeo")
            ctx: FastMCP context for progress reporting
            max_posts: Maximum number of posts to retrieve (default 50)

        Returns:
            Dict with url and posts list, where each post has:
            caption, likes, comments, timestamp, media_url.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_user_posts"
            )

            logger.info(
                "Scraping user posts: %s (max_posts=%d)",
                username,
                max_posts,
            )

            cb = MCPContextProgressCallback(ctx)
            result = await extractor.scrape_user_posts(
                username, max_posts, callbacks=cb
            )

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_user_posts")
        except Exception as e:
            raise_tool_error(e, "get_user_posts")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get User Reels",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"user", "scraping"},
        exclude_args=["extractor"],
    )
    async def get_user_reels(
        username: str,
        ctx: Context,
        max_reels: int = 50,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get an Instagram user's reels with view counts.

        Args:
            username: Instagram username (e.g., "instagram", "natgeo")
            ctx: FastMCP context for progress reporting
            max_reels: Maximum number of reels to retrieve (default 50)

        Returns:
            Dict with url and reels list, where each reel has:
            caption, views, likes, comments, video_url.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_user_reels"
            )

            logger.info(
                "Scraping user reels: %s (max_reels=%d)",
                username,
                max_reels,
            )

            cb = MCPContextProgressCallback(ctx)
            result = await extractor.scrape_user_reels(
                username, max_reels, callbacks=cb
            )

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_user_reels")
        except Exception as e:
            raise_tool_error(e, "get_user_reels")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get User Stories",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"user", "scraping"},
        exclude_args=["extractor"],
    )
    async def get_user_stories(
        username: str,
        ctx: Context,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get an Instagram user's active stories.

        Args:
            username: Instagram username (e.g., "instagram", "natgeo")
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with url and stories list, where each story has:
            media_url, timestamp, expires_at.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_user_stories"
            )

            logger.info("Scraping user stories: %s", username)

            await ctx.report_progress(
                progress=0, total=100, message="Fetching active stories"
            )

            result = await extractor.scrape_user_stories(username)

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_user_stories")
        except Exception as e:
            raise_tool_error(e, "get_user_stories")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get User Highlights",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"user", "scraping"},
        exclude_args=["extractor"],
    )
    async def get_user_highlights(
        username: str,
        ctx: Context,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get an Instagram user's story highlights.

        Args:
            username: Instagram username (e.g., "instagram", "natgeo")
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with url and highlights list, where each highlight has:
            title, cover_url, highlight_id.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_user_highlights"
            )

            logger.info("Scraping user highlights: %s", username)

            await ctx.report_progress(
                progress=0, total=100, message="Extracting story highlights"
            )

            result = await extractor.scrape_user_highlights(username)

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_user_highlights")
        except Exception as e:
            raise_tool_error(e, "get_user_highlights")  # NoReturn
