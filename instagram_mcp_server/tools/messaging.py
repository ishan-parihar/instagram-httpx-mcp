"""
Instagram Direct Message tools.

Provides inbox listing, conversation reading, and message sending.
"""

import logging
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from instagram_mcp_server.callbacks import MCPContextProgressCallback
from instagram_mcp_server.constants import TOOL_TIMEOUT_SECONDS
from instagram_mcp_server.core.exceptions import (
    AuthenticationError,
    InstagramScraperException,
)
from instagram_mcp_server.dependencies import get_ready_extractor, handle_auth_error
from instagram_mcp_server.error_handler import raise_tool_error

logger = logging.getLogger(__name__)


def register_messaging_tools(mcp: FastMCP) -> None:
    """Register all messaging-related tools with the MCP server."""

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Direct Inbox",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"messaging", "scraping"},
    )
    async def get_direct_inbox(
        ctx: Context,
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        List recent DM conversations from the Instagram direct inbox.

        Args:
            ctx: FastMCP context for progress reporting
            limit: Maximum number of conversations to load (1-50, default 20)

        Returns:
            Dict with url, sections (inbox -> raw text), and optional references.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_direct_inbox"
            )
            logger.info("Fetching DM inbox (limit=%d)", limit)

            callback = MCPContextProgressCallback(ctx)
            await callback.on_progress("Loading direct inbox", 0)

            result = await extractor.scrape_dm_inbox(limit=limit)

            await callback.on_progress("Complete", 100)

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_direct_inbox")
        except Exception as e:
            raise_tool_error(e, "get_direct_inbox")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get DM Conversation",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"messaging", "scraping"},
    )
    async def get_dm_conversation(
        ctx: Context,
        thread_id: str | None = None,
        username: str | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Read a specific DM conversation.

        Provide either username or thread_id to identify the conversation.

        Args:
            ctx: FastMCP context for progress reporting
            thread_id: Instagram messaging thread ID
            username: Instagram username of the conversation participant
            limit: Maximum number of messages to load (1-100, default 50)

        Returns:
            Dict with url, sections (conversation -> raw text), and optional references.
        """
        if not username and not thread_id:
            raise_tool_error(
                InstagramScraperException(
                    "Provide at least one of username or thread_id"
                ),
                "get_dm_conversation",
            )

        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_dm_conversation"
            )
            logger.info(
                "Fetching DM conversation: username=%s, thread_id=%s",
                username,
                thread_id,
            )

            callback = MCPContextProgressCallback(ctx)
            await callback.on_progress("Loading conversation", 0)

            result = await extractor.scrape_dm_conversation(
                thread_id=thread_id,
                username=username,
            )

            await callback.on_progress("Complete", 100)

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_dm_conversation")
        except Exception as e:
            raise_tool_error(e, "get_dm_conversation")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Send DM",
        annotations={"destructiveHint": True, "openWorldHint": True},
        tags={"messaging", "actions"},
    )
    async def send_dm(
        username: str,
        message: str,
        confirm_send: bool,
        ctx: Context,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Send a direct message to an Instagram user.

        This is a write operation — confirm_send must be True to actually send.

        Args:
            username: Instagram username of the recipient
            message: The message text to send
            confirm_send: Must be True to send the message
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with url, status, sent (bool), and optional message.
        """
        if not confirm_send:
            return {
                "url": None,
                "status": "not_sent",
                "sent": False,
                "message": "confirm_send must be True to send a message",
            }

        try:
            extractor = extractor or await get_ready_extractor(ctx, tool_name="send_dm")
            logger.info("Sending DM to %s (confirm_send=%s)", username, confirm_send)

            callback = MCPContextProgressCallback(ctx)
            await callback.on_progress("Sending message", 0)

            result = await extractor.send_dm(username, message)

            await callback.on_progress("Complete", 100)

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "send_dm")
        except Exception as e:
            raise_tool_error(e, "send_dm")  # NoReturn
