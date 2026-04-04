"""
Instagram account action tools.

Provides follow/unfollow, like/unlike, save, and comment actions
with destructive annotations for client-side confirmation prompts.
"""

import logging
from typing import Any

from fastmcp import Context, FastMCP

from instagram_mcp_server.constants import TOOL_TIMEOUT_SECONDS
from instagram_mcp_server.core.exceptions import AuthenticationError
from instagram_mcp_server.dependencies import get_ready_extractor, handle_auth_error
from instagram_mcp_server.error_handler import raise_tool_error

logger = logging.getLogger(__name__)


def register_action_tools(mcp: FastMCP) -> None:
    """Register all action-related tools with the MCP server."""

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Follow User",
        annotations={"destructiveHint": True, "openWorldHint": True},
        tags={"actions", "social"},
    )
    async def follow_user(
        username: str,
        ctx: Context,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Follow a user or send a follow request for private accounts.

        Navigates to the user's profile and clicks the Follow button.
        For private accounts, a follow request is sent.

        Args:
            username: Instagram username to follow (e.g., "natgeo")
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with url, status, and optional message.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="follow_user"
            )
            logger.info("Following user: %s", username)

            result = await extractor.follow_user(
                username,
            )

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "follow_user")
        except Exception as e:
            raise_tool_error(e, "follow_user")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Unfollow User",
        annotations={"destructiveHint": True, "openWorldHint": True},
        tags={"actions", "social"},
    )
    async def unfollow_user(
        username: str,
        ctx: Context,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Unfollow a user.

        Navigates to the user's profile and clicks the Unfollow button.

        Args:
            username: Instagram username to unfollow (e.g., "natgeo")
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with url, status, and optional message.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="unfollow_user"
            )
            logger.info("Unfollowing user: %s", username)

            result = await extractor.unfollow_user(
                username,
            )

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "unfollow_user")
        except Exception as e:
            raise_tool_error(e, "unfollow_user")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Like Post",
        annotations={"destructiveHint": True, "openWorldHint": True},
        tags={"actions", "social"},
    )
    async def like_post(
        post_url: str,
        ctx: Context,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Like a post.

        Navigates to the post and clicks the Like button.

        Args:
            post_url: Instagram post URL (e.g., "https://www.instagram.com/p/ABC123/")
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with url, status, and optional message.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="like_post"
            )
            logger.info("Liking post: %s", post_url)

            result = await extractor.like_post(post_url)

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "like_post")
        except Exception as e:
            raise_tool_error(e, "like_post")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Unlike Post",
        annotations={"destructiveHint": True, "openWorldHint": True},
        tags={"actions", "social"},
    )
    async def unlike_post(
        post_url: str,
        ctx: Context,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Unlike a post.

        Navigates to the post and clicks the Unlike button.

        Args:
            post_url: Instagram post URL (e.g., "https://www.instagram.com/p/ABC123/")
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with url, status, and optional message.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="unlike_post"
            )
            logger.info("Unliking post: %s", post_url)

            result = await extractor.unlike_post(post_url)

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "unlike_post")
        except Exception as e:
            raise_tool_error(e, "unlike_post")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Save Post",
        annotations={"destructiveHint": True, "openWorldHint": True},
        tags={"actions"},
    )
    async def save_post(
        post_url: str,
        ctx: Context,
        collection: str | None = None,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Save a post to a collection.

        Navigates to the post and clicks the Save button.
        Optionally saves to a specific collection.

        Args:
            post_url: Instagram post URL (e.g., "https://www.instagram.com/p/ABC123/")
            ctx: FastMCP context for progress reporting
            collection: Optional collection name to save the post into

        Returns:
            Dict with url, status, and optional message.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="save_post"
            )
            logger.info(
                "Saving post: %s (collection=%s)",
                post_url,
                collection,
            )

            result = await extractor.save_post(post_url, collection)

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "save_post")
        except Exception as e:
            raise_tool_error(e, "save_post")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Comment on Post",
        annotations={"destructiveHint": True, "openWorldHint": True},
        tags={"actions", "social"},
    )
    async def comment_on_post(
        post_url: str,
        comment: str,
        confirm_post: bool,
        ctx: Context,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Post a comment on a post.

        Navigates to the post and submits the comment. confirm_post
        must be True for the comment to be posted.

        Args:
            post_url: Instagram post URL (e.g., "https://www.instagram.com/p/ABC123/")
            comment: The comment text to post
            confirm_post: Must be True to actually post the comment
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with url, status, and optional message.
        """
        if not confirm_post:
            return {
                "url": post_url,
                "status": "cancelled",
                "message": "Comment not posted. Set confirm_post=True to post.",
            }

        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="comment_on_post"
            )
            logger.info("Commenting on post: %s", post_url)

            result = await extractor.comment_on_post(post_url, comment)

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "comment_on_post")
        except Exception as e:
            raise_tool_error(e, "comment_on_post")  # NoReturn
