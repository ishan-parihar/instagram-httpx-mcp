"""
Instagram search tools for users and locations.

Uses innerText extraction for resilient search result capture.
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


def register_search_tools(mcp: FastMCP) -> None:
    """Register all search-related tools with the MCP server."""

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Search Users",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"search", "scraping"},
    )
    async def search_users(
        query: str,
        max_results: int = 50,
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        Search for Instagram users.

        Args:
            query: Search query (e.g., "john doe", "photographer")
            ctx: FastMCP context for progress reporting
            max_results: Maximum number of results to return (default 50)

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text to extract individual users and their profiles.
        """
        try:
            extractor = await get_ready_extractor(ctx, tool_name="search_users")
            logger.info(
                "Searching users: query='%s', max_results=%d", query, max_results
            )

            await ctx.report_progress(
                progress=0, total=100, message="Starting user search"
            )

            result = await extractor.search_users(query, max_results=max_results)

            # Rename section key from generic search_results to users
            if "sections" in result and "search_results" in result["sections"]:
                result["sections"]["users"] = result["sections"].pop("search_results")
            if "references" in result and "search_results" in result["references"]:
                result["references"]["users"] = result["references"].pop(
                    "search_results"
                )

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "search_users")
        except Exception as e:
            logger.error("search_users failed: %s", e, exc_info=True)
            return {
                "url": f"https://www.instagram.com/explore/search/people/?q={query}",
                "sections": {},
                "section_errors": {
                    "users": {
                        "error_type": "search_failed",
                        "error_message": (
                            f"User search failed: {e}. Instagram's search requires "
                            f"interactive login. Try searching directly on instagram.com."
                        ),
                    }
                },
                "warnings": [
                    "Instagram search uses client-side rendering and may require "
                    "an active browser session with valid authentication."
                ],
            }

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Search Locations",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"search", "scraping"},
    )
    async def search_locations(
        query: str,
        max_results: int = 50,
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        Search for Instagram locations.

        Args:
            query: Search query (e.g., "New York", "Paris cafe")
            ctx: FastMCP context for progress reporting
            max_results: Maximum number of results to return (default 50)

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text to extract individual locations and their details.
        """
        try:
            extractor = await get_ready_extractor(ctx, tool_name="search_locations")
            logger.info(
                "Searching locations: query='%s', max_results=%d", query, max_results
            )

            await ctx.report_progress(
                progress=0, total=100, message="Starting location search"
            )

            result = await extractor.search_locations(query, max_results=max_results)

            # Rename section key from generic search_results to locations
            if "sections" in result and "search_results" in result["sections"]:
                result["sections"]["locations"] = result["sections"].pop(
                    "search_results"
                )
            if "references" in result and "search_results" in result["references"]:
                result["references"]["locations"] = result["references"].pop(
                    "search_results"
                )

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "search_locations")
        except Exception as e:
            logger.error("search_locations failed: %s", e, exc_info=True)
            return {
                "url": f"https://www.instagram.com/explore/search/location/?q={query}",
                "sections": {},
                "section_errors": {
                    "locations": {
                        "error_type": "search_failed",
                        "error_message": (
                            f"Location search failed: {e}. Instagram's search requires "
                            f"interactive login. Try searching directly on instagram.com."
                        ),
                    }
                },
                "warnings": [
                    "Instagram search uses client-side rendering and may require "
                    "an active browser session with valid authentication."
                ],
            }
