"""
Instagram Business/Creator insights tools (DEPRECATED).

These tools relied on browser-based navigation of the Professional Dashboard,
which is not available through Instagram's private-web API.
"""

import logging
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext


logger = logging.getLogger(__name__)

_DEPRECATION_MSG = (
    "Professional Dashboard insights are not available through Instagram's "
    "current API. These tools have been deprecated. "
    "Consider using get_user_profile with the 'posts' section for content-level "
    "engagement data instead."
)


def register_insights_tools(mcp: FastMCP) -> None:
    """Register deprecated insight tools with clear error messages."""

    @mcp.tool(
        timeout=30.0,
        title="Get Business Insights (Deprecated)",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "deprecated"},
    )
    async def get_business_insights(
        time_range: str = "7d",
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        [DEPRECATED] Get Business/Creator account insights from Professional Dashboard.

        This tool no longer functions. The Professional Dashboard is not accessible
        through Instagram's private-web API.

        Args:
            ctx: FastMCP context for progress reporting
            time_range: Ignored (tool is deprecated)

        Returns:
            Dict with deprecation notice and suggested alternatives.
        """
        return {
            "deprecated": True,
            "message": _DEPRECATION_MSG,
            "alternatives": [
                "Use get_user_profile with sections='posts' to see content engagement",
                "Use get_user_posts to get like/comment counts per post",
            ],
        }

    @mcp.tool(
        timeout=30.0,
        title="Get Audience Insights (Deprecated)",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "deprecated"},
    )
    async def get_audience_insights(
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        [DEPRECATED] Get audience demographics from Professional Dashboard.

        This tool no longer functions. The Professional Dashboard is not accessible
        through Instagram's private-web API.

        Args:
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with deprecation notice and suggested alternatives.
        """
        return {
            "deprecated": True,
            "message": _DEPRECATION_MSG,
            "alternatives": [
                "Use get_user_profile with sections='posts' to see content engagement",
                "Use get_user_posts to get like/comment counts per post",
            ],
        }

    @mcp.tool(
        timeout=30.0,
        title="Get Content Insights (Deprecated)",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "deprecated"},
    )
    async def get_content_insights(
        time_range: str = "30d",
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        [DEPRECATED] Get content performance insights from Professional Dashboard.

        This tool no longer functions. The Professional Dashboard is not accessible
        through Instagram's private-web API.

        Args:
            ctx: FastMCP context for progress reporting
            time_range: Ignored (tool is deprecated)

        Returns:
            Dict with deprecation notice and suggested alternatives.
        """
        return {
            "deprecated": True,
            "message": _DEPRECATION_MSG,
            "alternatives": [
                "Use get_user_posts to analyze individual post engagement",
                "Use get_user_profile to get an overview of a user's content",
            ],
        }

    @mcp.tool(
        timeout=30.0,
        title="Get Activity Insights (Deprecated)",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "deprecated"},
    )
    async def get_activity_insights(
        time_range: str = "7d",
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        [DEPRECATED] Get profile activity insights from Professional Dashboard.

        This tool no longer functions. The Professional Dashboard is not accessible
        through Instagram's private-web API.

        Args:
            ctx: FastMCP context for progress reporting
            time_range: Ignored (tool is deprecated)

        Returns:
            Dict with deprecation notice and suggested alternatives.
        """
        return {
            "deprecated": True,
            "message": _DEPRECATION_MSG,
            "alternatives": [
                "There is no direct API replacement for activity insights",
                "Use get_user_posts to get engagement data per post as a proxy",
            ],
        }
