"""
Instagram Reel Analysis using Google Gemini 2.0 Flash.

Fast multimodal analysis of Instagram reels without local transcription.
Uses the Instagram API client for video URL extraction and cookie auth.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Literal

import httpx
from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext
from google import genai
from google.genai import types

from instagram_mcp_server.dependencies import get_ready_extractor
from instagram_mcp_server.error_handler import raise_tool_error

logger = logging.getLogger(__name__)

ANALYSIS_DIR = Path.home() / ".instagram-mcp" / "gemini_analysis"


async def download_video_bytes(video_url: str, cookies: dict[str, str] | None = None) -> bytes | None:
    """Download video as bytes for Gemini upload.

    When a cookies dict is provided, attaches Instagram session cookies to
    the download request so it is authenticated.  Without cookies
    Instagram CDN returns 403 Forbidden.
    """
    try:
        headers: dict[str, str] = {
            "Referer": "https://www.instagram.com/",
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Pixel 8) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Mobile Safari/537.36"
            ),
        }

        # Attach Instagram session cookies if available
        if cookies:
            cookie_header = "; ".join(
                f"{k}={v}" for k, v in cookies.items() if v
            )
            if cookie_header:
                headers["Cookie"] = cookie_header

        async with httpx.AsyncClient(headers=headers) as client:
            response = await client.get(video_url, timeout=30.0)
            if response.status_code == 200:
                return response.content
            logger.warning(
                "Video download returned HTTP %d for %s",
                response.status_code,
                video_url[:80],
            )
        return None
    except Exception as e:
        logger.error("Download error: %s", e)
        return None


def get_gemini_api_key() -> str:
    """Get Gemini API key from environment variable only."""
    env_key = os.environ.get("GEMINI_API_KEY")
    if env_key:
        return env_key
    raise ValueError(
        "Gemini API key not configured. "
        "Set GEMINI_API_KEY environment variable. "
        "Get key from: https://aistudio.google.com/app/apikey"
    )


async def analyze_with_gemini(
    video_data: bytes | str,
    analysis_type: Literal[
        "summary", "transcript", "topics", "quotes", "full"
    ] = "full",
    is_url: bool = False,
) -> dict[str, Any]:
    """
    Analyze video using Gemini 2.0 Flash via google-genai.

    Args:
        video_data: Video bytes or URL string
        analysis_type: Type of analysis to perform
        is_url: If True, video_data is a URL; if False, it's bytes

    Returns:
        Structured analysis results
    """
    try:
        api_key = get_gemini_api_key()
        client = genai.Client(api_key=api_key)

        # Build prompt based on analysis type
        prompts = {
            "summary": """Analyze this Instagram reel and provide:
1. One-sentence summary
2. Main topic/category
3. Target audience
4. Key takeaway

Respond in JSON format with keys: summary, topic, audience, takeaway""",
            "transcript": """Transcribe this video. Provide:
1. Full transcript text
2. Segment breakdown with timestamps (every 10-15 seconds)
3. Speaker identification if multiple speakers

Respond in JSON format with keys: transcript, segments (array with start, end, text, speaker)""",
            "topics": """Extract topics from this Instagram reel:
1. Main topic (broad category)
2. Subtopics (3-5 specific subjects)
3. Keywords (5-10 terms)
4. Suggested hashtags for Instagram

Respond in JSON format with keys: main_topic, subtopics (array), keywords (array), hashtags (array)""",
            "quotes": """Extract 3-5 notable quotes from this video:
For each quote provide:
- Exact wording
- Approximate timestamp (e.g., "0:15")
- Why it's significant

Respond in JSON format with keys: quotes (array with text, timestamp, significance)""",
            "full": """Comprehensive analysis of this Instagram reel. Provide:
1. Summary (2-3 sentences)
2. Full transcript
3. Key topics (3-5)
4. Notable quotes (2-3)
5. Sentiment (positive/negative/neutral/mixed)
6. Actionable insights or key takeaways
7. Content category (educational/entertainment/promotional/etc)

Respond in JSON format with keys: summary, transcript, topics (array), quotes (array with text+timestamp), sentiment, insights (array), category""",
        }

        prompt = prompts.get(analysis_type, prompts["full"])

        # Prepare content for Gemini
        if is_url:
            # Gemini can fetch from URL directly
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_uri(
                            file_uri=video_data,
                            mime_type="video/mp4",
                        ),
                    ],
                )
            ]
        else:
            # Upload video bytes via inline data
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(
                            data=video_data,
                            mime_type="video/mp4",
                        ),
                    ],
                )
            ]

        # Generate content
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.0-flash",
                contents=contents,
            ),
        )

        # Parse response
        import json

        response_text = response.text.strip()

        # Try to extract JSON from response
        try:
            # Look for JSON block
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text

            result = json.loads(json_str)
            result["raw_response"] = response_text
            result["model"] = "gemini-2.0-flash"
            result["analysis_type"] = analysis_type

            return result

        except json.JSONDecodeError as e:
            logger.warning("JSON parse error: %s, returning raw text", e)
            return {
                "raw_response": response_text,
                "model": "gemini-2.0-flash",
                "analysis_type": analysis_type,
                "parse_error": str(e),
            }

    except Exception as e:
        logger.error("Gemini analysis error: %s", e)
        raise


def register_gemini_tools(mcp: FastMCP) -> None:
    """Register Gemini analysis tools with MCP server."""

    @mcp.tool(
        timeout=120.0,
        title="Analyze Reel with Gemini",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"reels", "analysis", "ai", "gemini"},
    )
    async def analyze_reel_with_gemini(
        reel_url: str,
        analysis_type: Literal[
            "summary", "transcript", "topics", "quotes", "full"
        ] = "full",
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        Analyze Instagram reel using Google Gemini 2.0 Flash.

        Fast multimodal analysis that understands both audio and visuals.
        Returns structured insights without local transcription.

        **Speed:** ~15-25 seconds per reel (3x faster than local Whisper)

        **Cost:** ~$0.00017 per reel (extremely cheap)

        Args:
            reel_url: Full Instagram reel URL (e.g., https://www.instagram.com/reel/ABC123/)
            ctx: FastMCP context for progress reporting
            analysis_type: Type of analysis:
                - summary: Quick overview (fastest)
                - transcript: Full transcription
                - topics: Extract topics and keywords
                - quotes: Notable quotes with timestamps
                - full: Comprehensive analysis (default)

        Returns:
            Dict with analysis results in JSON format.
            Structure depends on analysis_type.
        """
        try:
            await ctx.report_progress(
                progress=0, total=100, message="Getting reel details..."
            )

            extractor = await get_ready_extractor(
                ctx, tool_name="analyze_reel_with_gemini"
            )

            # Extract reel ID and video URL
            reel_id = reel_url.rstrip("/").split("/reel/")[-1].split("?")[0]

            logger.info("Analyzing reel %s with Gemini (%s)", reel_id, analysis_type)

            await ctx.report_progress(
                progress=10, total=100, message="Fetching reel metadata..."
            )

            # Fetch reel video URL via the API client
            details = await extractor.get_post_details(reel_url)
            post_details = details.get("post_details", {})
            video_url = post_details.get("video_url", "") or post_details.get("media_url", "")
            if not video_url:
                raise Exception(
                    "Could not extract video URL from reel. "
                    "The reel may be private, deleted, or Instagram's structure changed."
                )

            await ctx.report_progress(
                progress=25, total=100, message="Downloading video..."
            )

            # Download video bytes (with authenticated cookies)
            video_bytes = await download_video_bytes(video_url, extractor._cookies)

            if not video_bytes:
                raise Exception("Video download failed")

            await ctx.report_progress(
                progress=50,
                total=100,
                message=f"Analyzing with Gemini ({analysis_type})...",
            )

            # Analyze with Gemini
            result = await analyze_with_gemini(
                video_bytes, analysis_type=analysis_type, is_url=False
            )

            await ctx.report_progress(progress=100, total=100, message="Complete")

            # Save analysis to file
            ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
            analysis_file = ANALYSIS_DIR / f"{reel_id}_{analysis_type}.json"
            import json

            with open(analysis_file, "w") as f:
                json.dump(result, f, indent=2)

            return {
                "reel_id": reel_id,
                "reel_url": reel_url,
                "video_url": video_url,
                "analysis_type": analysis_type,
                "analysis_file": str(analysis_file),
                "model": "gemini-2.0-flash",
                "results": result,
            }

        except Exception as e:
            raise_tool_error(e, "analyze_reel_with_gemini")

    @mcp.tool(
        timeout=300.0,
        title="Bulk Analyze User Reels with Gemini",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"reels", "analysis", "ai", "gemini", "bulk"},
    )
    async def bulk_analyze_reels_with_gemini(
        username: str,
        max_reels: int = 5,
        analysis_type: Literal[
            "summary", "transcript", "topics", "quotes", "full"
        ] = "summary",
        ctx: Context = CurrentContext(),
    ) -> dict[str, Any]:
        """
        Analyze multiple reels from a user with Gemini.

        Faster than local transcription for bulk analysis.
        Processes reels sequentially to avoid rate limits.

        Args:
            username: Instagram username (e.g., "instagram", "natgeo")
            ctx: FastMCP context for progress reporting
            max_reels: Maximum reels to analyze (default: 5)
            analysis_type: Analysis type (default: summary for speed)

        Returns:
            Dict with analyses for each reel.
        """
        try:
            await ctx.report_progress(
                progress=0, total=100, message="Fetching reels..."
            )

            extractor = await get_ready_extractor(
                ctx, tool_name="bulk_analyze_reels_with_gemini"
            )

            logger.info(
                "Bulk analyzing @%s reels (max=%d, type=%s)",
                username,
                max_reels,
                analysis_type,
            )

            # Get user reels
            reels_result = await extractor.scrape_user_reels(
                username, max_reels=max_reels
            )

            reel_links = reels_result.get("references", {}).get("reels", [])

            if not reel_links:
                raise_tool_error(
                    Exception("No reels found for @%s" % username),
                    "bulk_analyze_reels_with_gemini",
                )

            analyses = []
            total_reels = len(reel_links)

            for i, reel in enumerate(reel_links):
                reel_id = reel.get("text", "").replace("reel:", "")
                reel_url = f"https://www.instagram.com/reel/{reel_id}/"

                await ctx.report_progress(
                    progress=int((i / total_reels) * 100),
                    total=100,
                    message=f"Analyzing reel {i + 1}/{total_reels}...",
                )

                try:
                    # Fetch reel video URL via the API client
                    details = await extractor.get_post_details(reel_url)
                    post_details = details.get("post_details", {})
                    video_url = post_details.get("video_url", "") or post_details.get("media_url", "")
                    if not video_url:
                        raise Exception("Could not extract video URL from reel")

                    # Download video bytes (with authenticated cookies)
                    video_bytes = await download_video_bytes(video_url, extractor._cookies)
                    if not video_bytes:
                        raise Exception("Video download failed")

                    result = await analyze_with_gemini(
                        video_bytes, analysis_type=analysis_type, is_url=False
                    )

                    analyses.append(
                        {
                            "reel_id": reel_id,
                            "status": "success",
                            "analysis": result,
                        }
                    )

                except Exception as e:
                    logger.warning("Failed to analyze %s: %s", reel_id, e)
                    analyses.append(
                        {"reel_id": reel_id, "status": "failed", "error": str(e)}
                    )

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return {
                "username": username,
                "total_reels": len(analyses),
                "successful": sum(1 for a in analyses if a["status"] == "success"),
                "failed": sum(1 for a in analyses if a["status"] == "failed"),
                "analysis_type": analysis_type,
                "analyses": analyses,
            }

        except Exception as e:
            raise_tool_error(e, "bulk_analyze_reels_with_gemini")
