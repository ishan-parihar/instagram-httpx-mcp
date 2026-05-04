"""Media processing utilities for frame extraction using ffmpeg."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    fps: float = 1.0,
    *,
    max_frames: int = 0,
    prefix: str = "frame",
) -> list[Path]:
    """
    Extract frames from a video at the given FPS.

    Uses ffmpeg subprocess (ffmpeg-python dependency for tracking only,
    actual work via subprocess for reliability).

    Args:
        video_path: Path to video file
        output_dir: Directory to write frames to
        fps: Frames per second to extract (default 1.0)
        max_frames: Maximum number of frames (0 = unlimited)
        prefix: Filename prefix for extracted frames

    Returns:
        List of paths to extracted frame images
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        logger.error("Video not found: %s", video_path)
        return []

    output_pattern = str(output_dir / f"{prefix}_%04d.jpg")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"fps={fps}",
        "-q:v", "2",
    ]
    if max_frames > 0:
        cmd.extend(["-vframes", str(max_frames)])
    cmd.append(output_pattern)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.error("ffmpeg error: %s", result.stderr[:500])
            return []

        # Collect generated frames
        frames = sorted(output_dir.glob(f"{prefix}_*.jpg"))
        logger.info("Extracted %d frames at %s FPS from %s", len(frames), fps, video_path.name)
        return frames
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timed out processing %s", video_path)
        return []
    except Exception as e:
        logger.error("Frame extraction error: %s", e)
        return []


def get_video_duration(video_path: str | Path) -> float:
    """Get video duration in seconds using ffprobe."""
    video_path = Path(video_path)
    if not video_path.exists():
        return 0.0

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception as e:
        logger.warning("Could not get video duration: %s", e)

    return 0.0
