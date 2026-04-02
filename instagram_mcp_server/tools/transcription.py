"""
Instagram Reel Transcription Tools.

Downloads reels and generates SRT subtitles using existing caption command.
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from fastmcp import Context, FastMCP

from instagram_mcp_server.constants import TOOL_TIMEOUT_SECONDS
from instagram_mcp_server.dependencies import get_ready_extractor, handle_auth_error
from instagram_mcp_server.error_handler import raise_tool_error

import httpx
import logging

logger = logging.getLogger(__name__)

TRANSCRIPTS_DIR = Path.home() / ".instagram-mcp" / "transcripts"
TMP_DIR = TRANSCRIPTS_DIR / "tmp"
OUTPUT_DIR = TRANSCRIPTS_DIR / "output"


def ensure_directories():
    """Create transcript directories if they don't exist."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def download_video(video_url: str, output_path: Path) -> bool:
    """Download video from Instagram URL."""
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", video_url, timeout=30.0) as response:
                if response.status_code != 200:
                    logger.error(f"Download failed: {response.status_code}")
                    return False

                with open(output_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)

        logger.info(f"Downloaded: {output_path.name}")
        return True
    except Exception as e:
        logger.error(f"Download error: {e}")
        return False


def run_caption(media_path: Path, output_dir: Path = None) -> Path | None:
    """
    Run caption command on media file.

    Args:
        media_path: Path to video/audio file
        output_dir: Where to save SRT (default: same directory as media)

    Returns:
        Path to generated SRT file, or None if failed
    """
    if output_dir is None:
        output_dir = media_path.parent

    try:
        logger.info(f"Running caption on {media_path.name}...")

        result = subprocess.run(
            ["caption", str(media_path)],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            logger.error(f"caption failed: {result.stderr}")
            return None

        srt_path = output_dir / f"{media_path.stem}.srt"

        if srt_path.exists():
            logger.info(f"Generated: {srt_path.name}")
            return srt_path
        else:
            logger.error(f"SRT not found: {srt_path}")
            return None

    except subprocess.TimeoutExpired:
        logger.error(f"caption timeout for {media_path.name}")
        return None
    except FileNotFoundError:
        logger.error("caption command not found. Make sure it's in PATH.")
        return None
    except Exception as e:
        logger.error(f"caption error: {e}")
        return None


def read_srt_preview(srt_path: Path, max_chars: int = 200) -> str:
    """Read first subtitle from SRT as preview."""
    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if len(lines) >= 3:
                preview = lines[2].strip()
                return preview[:max_chars] + ("..." if len(preview) > max_chars else "")
        return ""
    except Exception:
        return ""


def register_transcription_tools(mcp: FastMCP) -> None:
    """Register transcription tools with MCP server."""

    @mcp.tool(
        timeout=600.0,
        title="Transcribe User Reels",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"reels", "transcription", "accessibility"},
        exclude_args=["extractor"],
    )
    async def transcribe_user_reels(
        username: str,
        ctx: Context,
        max_reels: int = 10,
        keep_videos: bool = False,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Download and transcribe Instagram reels to SRT subtitles.

        Downloads reels, runs speech-to-text using Whisper via the caption command,
        and generates SRT subtitle files.

        Args:
            username: Instagram username (e.g., "instagram", "natgeo")
            ctx: FastMCP context for progress reporting
            max_reels: Maximum reels to transcribe (default: 10)
            keep_videos: Keep downloaded video files (default: False)

        Returns:
            Dict with:
            - url: Instagram profile URL
            - transcripts: List of {reel_id, video_url, srt_path, transcript_preview, reel_url}
            - total_reels: Number processed
            - temp_dir: Temporary files location
            - output_dir: SRT output directory
        """
        try:
            ensure_directories()

            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="transcribe_user_reels"
            )

            await ctx.report_progress(
                progress=0, total=100, message="Fetching reels..."
            )

            logger.info(f"Fetching reels for @{username} (max={max_reels})")

            reels_result = await extractor.scrape_user_reels(
                username, max_reels=max_reels
            )

            reel_links = reels_result.get("references", {}).get("reels", [])

            if not reel_links:
                raise_tool_error(
                    Exception(f"No reels found for @{username}"),
                    "transcribe_user_reels",
                )

            transcripts = []
            total_reels = len(reel_links)

            for i, reel in enumerate(reel_links):
                reel_id = reel.get("text", "").replace("reel:", "")
                video_url = reel.get("url", "")

                if not reel_id or not video_url:
                    logger.warning(f"Skipping reel {i + 1}: missing URL or ID")
                    continue

                await ctx.report_progress(
                    progress=int((i / total_reels) * 100),
                    total=100,
                    message=f"Downloading reel {i + 1}/{total_reels}...",
                )

                video_path = TMP_DIR / f"{reel_id}.mp4"

                if not await download_video(video_url, video_path):
                    logger.warning(f"Skipping {reel_id}: download failed")
                    continue

                await ctx.report_progress(
                    progress=int(((i + 0.5) / total_reels) * 100),
                    total=100,
                    message=f"Transcribing reel {i + 1}/{total_reels}...",
                )

                srt_path = run_caption(video_path)

                if not srt_path or not srt_path.exists():
                    logger.warning(f"Skipping {reel_id}: transcription failed")
                    if not keep_videos:
                        video_path.unlink(missing_ok=True)
                    continue

                output_srt = OUTPUT_DIR / f"{reel_id}.srt"
                srt_path.rename(output_srt)

                preview = read_srt_preview(output_srt)

                transcripts.append(
                    {
                        "reel_id": reel_id,
                        "video_url": video_url,
                        "srt_path": str(output_srt),
                        "transcript_preview": preview,
                        "reel_url": f"https://www.instagram.com/reel/{reel_id}/",
                    }
                )

                if not keep_videos:
                    video_path.unlink(missing_ok=True)

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return {
                "url": f"https://www.instagram.com/{username}/",
                "transcripts": transcripts,
                "total_reels": len(transcripts),
                "temp_dir": str(TMP_DIR),
                "output_dir": str(OUTPUT_DIR),
            }

        except Exception as e:
            raise_tool_error(e, "transcribe_user_reels")

    @mcp.tool(
        timeout=300.0,
        title="Transcribe Single Reel",
        annotations={"readOnlyHint": True, "openWorldHint": True},
        tags={"reels", "transcription"},
        exclude_args=["extractor"],
    )
    async def transcribe_reel(
        reel_url: str,
        ctx: Context,
        keep_video: bool = False,
        extractor: Any | None = None,
    ) -> dict[str, Any]:
        """
        Transcribe a single Instagram reel to SRT.

        Args:
            reel_url: Full Instagram reel URL (e.g., https://www.instagram.com/reel/ABC123/)
            ctx: FastMCP context for progress reporting
            keep_video: Keep downloaded video file (default: False)

        Returns:
            Dict with reel_id, srt_path, transcript_preview, etc.
        """
        try:
            ensure_directories()

            reel_id = reel_url.rstrip("/").split("/reel/")[-1].split("?")[0]

            await ctx.report_progress(
                progress=0, total=100, message="Getting reel details..."
            )

            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="transcribe_reel"
            )

            logger.info(f"Transcribing reel: {reel_id}")

            reel_result = await extractor.extract_page(reel_url, section_name="main")

            video_url = None
            if reel_result.get("references"):
                for ref in reel_result["references"].get("main", []):
                    if "video" in ref.get("kind", "").lower() or "/reel/" in ref.get(
                        "url", ""
                    ):
                        video_url = ref.get("url")
                        break

            if not video_url:
                raise Exception("Could not extract video URL from reel")

            await ctx.report_progress(
                progress=25, total=100, message="Downloading video..."
            )

            video_path = TMP_DIR / f"{reel_id}.mp4"
            if not await download_video(video_url, video_path):
                raise Exception("Video download failed")

            await ctx.report_progress(
                progress=50, total=100, message="Transcribing audio..."
            )

            srt_path = run_caption(video_path)

            if not srt_path:
                raise Exception("Transcription failed")

            output_srt = OUTPUT_DIR / f"{reel_id}.srt"
            srt_path.rename(output_srt)

            preview = read_srt_preview(output_srt)

            if not keep_video:
                video_path.unlink(missing_ok=True)

            await ctx.report_progress(progress=100, total=100, message="Complete")

            return {
                "reel_id": reel_id,
                "video_url": video_url,
                "srt_path": str(output_srt),
                "transcript_preview": preview,
                "reel_url": reel_url,
            }

        except Exception as e:
            raise_tool_error(e, "transcribe_reel")
