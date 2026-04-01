"""
Instagram Business/Creator insights tools.

Uses innerText extraction for resilient insights data capture
from the Professional Dashboard.

Note: Professional Dashboard is only available for Business and Creator accounts.
"""

import logging
from typing import Any

from fastmcp import Context, FastMCP

from instagram_mcp_server.constants import TOOL_TIMEOUT_SECONDS
from instagram_mcp_server.core.exceptions import AuthenticationError
from instagram_mcp_server.dependencies import get_ready_extractor, handle_auth_error
from instagram_mcp_server.error_handler import raise_tool_error
from instagram_mcp_server.scraping.extractor import _RATE_LIMITED_MSG
from instagram_mcp_server.scraping.link_metadata import Reference

logger = logging.getLogger(__name__)

_DASHBOARD_URL = "https://www.instagram.com/professional_dashboard/"


def register_insights_tools(mcp: FastMCP) -> None:
    """Register all insights-related tools with the MCP server."""

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Business Insights",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "scraping"},
        exclude_args=["extractor"],
    )
    async def get_business_insights(
        ctx: Context,
        time_range: str = "7d",
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get Business/Creator account insights from Professional Dashboard.

        Note: Professional Dashboard is only available for Business and Creator accounts.

        Args:
            ctx: FastMCP context for progress reporting
            time_range: Time range for insights data (7d, 30d, 90d). Default: "7d"

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text in each section.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_business_insights"
            )
            logger.info("Scraping business insights (time_range=%s)", time_range)

            await ctx.report_progress(
                progress=0, total=100, message="Navigating to Professional Dashboard"
            )

            url = _DASHBOARD_URL
            extracted = await extractor.extract_page(url, section_name="overview")

            sections: dict[str, str] = {}
            references: dict[str, list[Reference]] = {}
            if extracted.text and extracted.text != _RATE_LIMITED_MSG:
                sections["overview"] = extracted.text
                if extracted.references:
                    references["overview"] = extracted.references

            await ctx.report_progress(progress=100, total=100, message="Complete")

            result: dict[str, Any] = {
                "url": url,
                "sections": sections,
            }
            if references:
                result["references"] = references
            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_business_insights")
        except Exception as e:
            raise_tool_error(e, "get_business_insights")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Audience Insights",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "scraping"},
        exclude_args=["extractor"],
    )
    async def get_audience_insights(
        ctx: Context,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get audience demographics from Professional Dashboard.

        Note: Professional Dashboard is only available for Business and Creator accounts.

        Args:
            ctx: FastMCP context for progress reporting

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text to extract audience demographics.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_audience_insights"
            )
            logger.info("Scraping audience insights")

            await ctx.report_progress(
                progress=0, total=100, message="Navigating to audience tab"
            )

            url = f"{_DASHBOARD_URL}?tab=audience"
            extracted = await extractor.extract_page(url, section_name="audience")

            sections: dict[str, str] = {}
            references: dict[str, list[Reference]] = {}
            if extracted.text and extracted.text != _RATE_LIMITED_MSG:
                sections["audience"] = extracted.text
                if extracted.references:
                    references["audience"] = extracted.references

            await ctx.report_progress(progress=100, total=100, message="Complete")

            result: dict[str, Any] = {
                "url": url,
                "sections": sections,
            }
            if references:
                result["references"] = references
            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_audience_insights")
        except Exception as e:
            raise_tool_error(e, "get_audience_insights")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Content Insights",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "scraping"},
        exclude_args=["extractor"],
    )
    async def get_content_insights(
        ctx: Context,
        time_range: str = "30d",
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get content performance insights from Professional Dashboard.

        Note: Professional Dashboard is only available for Business and Creator accounts.

        Args:
            ctx: FastMCP context for progress reporting
            time_range: Time range for insights data (7d, 30d, 90d). Default: "30d"

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text to extract content performance data.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_content_insights"
            )
            logger.info("Scraping content insights (time_range=%s)", time_range)

            await ctx.report_progress(
                progress=0, total=100, message="Navigating to content tab"
            )

            url = f"{_DASHBOARD_URL}?tab=content"
            extracted = await extractor.extract_page(url, section_name="content")

            sections: dict[str, str] = {}
            references: dict[str, list[Reference]] = {}
            if extracted.text and extracted.text != _RATE_LIMITED_MSG:
                sections["content"] = extracted.text
                if extracted.references:
                    references["content"] = extracted.references

            await ctx.report_progress(progress=100, total=100, message="Complete")

            result: dict[str, Any] = {
                "url": url,
                "sections": sections,
            }
            if references:
                result["references"] = references
            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_content_insights")
        except Exception as e:
            raise_tool_error(e, "get_content_insights")  # NoReturn

    @mcp.tool(
        timeout=TOOL_TIMEOUT_SECONDS,
        title="Get Activity Insights",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"insights", "scraping"},
        exclude_args=["extractor"],
    )
    async def get_activity_insights(
        ctx: Context,
        time_range: str = "7d",
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Get profile activity insights from Professional Dashboard.

        Note: Professional Dashboard is only available for Business and Creator accounts.

        Args:
            ctx: FastMCP context for progress reporting
            time_range: Time range for insights data (7d, 30d, 90d). Default: "7d"

        Returns:
            Dict with url, sections (name -> raw text), and optional references.
            The LLM should parse the raw text to extract profile activity data.
        """
        try:
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="get_activity_insights"
            )
            logger.info("Scraping activity insights (time_range=%s)", time_range)

            await ctx.report_progress(
                progress=0, total=100, message="Navigating to activity tab"
            )

            url = f"{_DASHBOARD_URL}?tab=activity"
            extracted = await extractor.extract_page(url, section_name="activity")

            sections: dict[str, str] = {}
            references: dict[str, list[Reference]] = {}
            if extracted.text and extracted.text != _RATE_LIMITED_MSG:
                sections["activity"] = extracted.text
                if extracted.references:
                    references["activity"] = extracted.references

            await ctx.report_progress(progress=100, total=100, message="Complete")

            result: dict[str, Any] = {
                "url": url,
                "sections": sections,
            }
            if references:
                result["references"] = references
            return result

        except AuthenticationError as e:
            try:
                await handle_auth_error(e, ctx)
            except Exception as relogin_exc:
                raise_tool_error(relogin_exc, "get_activity_insights")
        except Exception as e:
            raise_tool_error(e, "get_activity_insights")  # NoReturn
