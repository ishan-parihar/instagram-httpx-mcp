# Instagram Reel Transcription Tool - Implementation Plan

**Date:** 2026-04-02  
**Integration:** Uses existing `caption` command from ~/Documents/GitHub/openscript/modules/transcription  
**Status:** Ready for Implementation

---

## Existing Infrastructure (Already Available)

### `caption` Command
**Location:** `/home/ishanp/bin/caption`  
**Functionality:**
- Takes video/audio file as input
- Uses `whisper_timestamped` with `Oriserve/Whisper-Hindi2Hinglish-Prime` model
- Generates SRT subtitle file in current working directory
- Handles audio extraction from video automatically
- Runs in conda environment `whisper-hindi`

**Usage:**
```bash
caption video.mp4
# Output: video.srt (in current directory)
```

### Source Code
**Location:** `~/Documents/GitHub/openscript/modules/transcription/`
- `caption_generator.py` - Main transcription logic
- `media_handler.py` - Audio extraction, format conversion
- `utils.py` - Device/dtype helpers
- `logger.py` - Logging configuration

**Dependencies:**
- `torch`
- `whisper_timestamped`
- `ffmpeg` + `ffprobe`
- Conda env: `whisper-hindi`

---

## Implementation Plan

### New MCP Tool: `transcribe_user_reels`

**Goal:** Download Instagram reels → Generate SRT transcripts using existing `caption` command

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  1. get_user_reels()                                         │
│      - Get reel metadata + video_url                         │
│      - Returns: [{reel_id, video_url, caption, ...}]         │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  2. Download Videos                                          │
│      - Download from video_url using httpx                   │
│      - Save to: ~/.instagram-mcp/transcripts/tmp/            │
│      - Name: {reel_id}.mp4                                   │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  3. Run `caption` Command                                    │
│      - subprocess.run(["caption", "{reel_id}.mp4"])          │
│      - Generates: {reel_id}.srt                              │
│      - Wait for completion                                   │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│  4. Return Results                                           │
│      - Map reel_id → SRT path                                │
│      - Include transcript preview                            │
│      - Optionally cleanup temp files                         │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation Details

### File: `instagram_mcp_server/tools/transcription.py` (NEW)

```python
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
        # Run caption command
        result = subprocess.run(
            ["caption", str(media_path)],
            cwd=str(output_dir),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout per video
        )
        
        if result.returncode != 0:
            logger.error(f"caption failed: {result.stderr}")
            return None
        
        # SRT is created in same directory as input
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
    except Exception as e:
        logger.error(f"caption error: {e}")
        return None


def read_srt_preview(srt_path: Path, max_chars: int = 200) -> str:
    """Read first few lines of SRT as preview."""
    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            # Skip sequence number and timestamp, get first subtitle text
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
        timeout=600.0,  # 10 minutes for bulk processing
        title="Transcribe User Reels",
        annotations={"readOnlyHint": True},
        tags={"reels", "transcription", "accessibility"},
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
        
        Downloads reels, runs speech-to-text using Whisper, and generates
        SRT subtitle files. Uses existing caption command infrastructure.
        
        Args:
            username: Instagram username (e.g., "instagram", "natgeo")
            ctx: FastMCP context for progress reporting
            max_reels: Maximum reels to transcribe (default: 10)
            keep_videos: Keep downloaded video files (default: False)
        
        Returns:
            Dict with:
            - url: Instagram profile URL
            - transcripts: List of {reel_id, video_url, srt_path, transcript_preview, duration}
            - total_reels: Number processed
            - temp_dir: Temporary files location
        """
        try:
            ensure_directories()
            
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="transcribe_user_reels"
            )
            
            await ctx.report_progress(
                progress=0, total=100, message="Fetching reels..."
            )
            
            # Step 1: Get user reels
            logger.info(f"Fetching reels for @{username}")
            reels_result = await extractor.scrape_user_reels(
                username, max_reels=max_reels
            )
            
            # Extract video URLs from references
            reel_links = reels_result.get("references", {}).get("reels", [])
            
            if not reel_links:
                raise_tool_error(
                    Exception(f"No reels found for @{username}"),
                    "transcribe_user_reels"
                )
            
            transcripts = []
            total_reels = len(reel_links)
            
            for i, reel in enumerate(reel_links):
                reel_id = reel.get("text", "").replace("reel:", "")
                video_url = reel.get("url", "")
                
                if not reel_id or not video_url:
                    continue
                
                await ctx.report_progress(
                    progress=int((i / total_reels) * 100),
                    total=100,
                    message=f"Downloading reel {i+1}/{total_reels}..."
                )
                
                # Step 2: Download video
                video_path = TMP_DIR / f"{reel_id}.mp4"
                if not await download_video(video_url, video_path):
                    logger.warning(f"Skipping {reel_id}: download failed")
                    continue
                
                await ctx.report_progress(
                    progress=int(((i + 0.5) / total_reels) * 100),
                    total=100,
                    message=f"Transcribing reel {i+1}/{total_reels}..."
                )
                
                # Step 3: Run caption command
                srt_path = run_caption(video_path)
                
                if not srt_path or not srt_path.exists():
                    logger.warning(f"Skipping {reel_id}: transcription failed")
                    if not keep_videos:
                        video_path.unlink(missing_ok=True)
                    continue
                
                # Step 4: Move SRT to output directory
                output_srt = OUTPUT_DIR / f"{reel_id}.srt"
                srt_path.rename(output_srt)
                
                # Read preview
                preview = read_srt_preview(output_srt)
                
                transcripts.append({
                    "reel_id": reel_id,
                    "video_url": video_url,
                    "srt_path": str(output_srt),
                    "transcript_preview": preview,
                    "reel_url": f"https://www.instagram.com/reel/{reel_id}/"
                })
                
                # Cleanup video if not keeping
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
        annotations={"readOnlyHint": True},
        tags={"reels", "transcription"},
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
            
            # Extract reel ID from URL
            reel_id = reel_url.rstrip("/").split("/reel/")[-1].split("?")[0]
            
            await ctx.report_progress(
                progress=0, total=100, message="Getting reel details..."
            )
            
            extractor = extractor or await get_ready_extractor(
                ctx, tool_name="transcribe_reel"
            )
            
            # Get reel details to extract video URL
            reel_result = await extractor.extract_page(reel_url, section_name="main")
            
            # Extract video URL from references or page content
            video_url = None
            if reel_result.get("references"):
                for ref in reel_result["references"].get("main", []):
                    if "video" in ref.get("kind", "").lower() or "/reel/" in ref.get("url", ""):
                        video_url = ref.get("url")
                        break
            
            if not video_url:
                # Try to get from user reels
                # (fallback - would need username extraction)
                raise Exception("Could not extract video URL from reel")
            
            await ctx.report_progress(
                progress=25, total=100, message="Downloading video..."
            )
            
            # Download video
            video_path = TMP_DIR / f"{reel_id}.mp4"
            if not await download_video(video_url, video_path):
                raise Exception("Video download failed")
            
            await ctx.report_progress(
                progress=50, total=100, message="Transcribing audio..."
            )
            
            # Run caption
            srt_path = run_caption(video_path)
            
            if not srt_path:
                raise Exception("Transcription failed")
            
            # Move to output
            output_srt = OUTPUT_DIR / f"{reel_id}.srt"
            srt_path.rename(output_srt)
            
            preview = read_srt_preview(output_srt)
            
            # Cleanup
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
```

---

### File: `instagram_mcp_server/server.py` (MODIFY)

Add transcription tools registration:

```python
from .tools.transcription import register_transcription_tools

# ... in setup_mcp_server()
register_transcription_tools(mcp)
```

---

## Usage Examples

### Bulk Transcription
```
Transcribe all reels from @natgeo with subtitles
```

**Result:**
```json
{
  "transcripts": [
    {
      "reel_id": "C0AbCdEfGhI",
      "srt_path": "/home/user/.instagram-mcp/transcripts/output/C0AbCdEfGhI.srt",
      "transcript_preview": "This incredible footage shows...",
      "reel_url": "https://www.instagram.com/reel/C0AbCdEfGhI/"
    }
  ],
  "total_reels": 5
}
```

### Single Reel
```
Get subtitles for this reel: https://www.instagram.com/reel/C0AbCdEfGhI/
```

---

## Performance Estimates

Based on existing `caption` command performance:

| Reel Duration | Processing Time (CPU) | Processing Time (GPU) |
|---------------|----------------------|----------------------|
| 15 seconds | ~20-30s | ~5-10s |
| 30 seconds | ~35-50s | ~10-15s |
| 60 seconds | ~60-90s | ~15-25s |
| 90 seconds | ~90-120s | ~25-40s |

**Bulk Processing (10 reels, avg 30s each):**
- CPU: ~6-8 minutes
- GPU: ~2-3 minutes

---

## Error Handling

### Failure Modes & Recovery

1. **Video Download Fails**
   - URL expired → Skip with warning
   - Network error → Retry 2x
   - DRM protected → Skip (log warning)

2. **`caption` Command Fails**
   - Not in PATH → Error: "caption command not found"
   - Conda env issue → Error: "whisper-hindi environment not found"
   - Timeout → Skip reel, continue with next

3. **No Audio in Reel**
   - SRT will be empty or minimal
   - Return with warning in response

---

## Testing

### Unit Tests
```python
def test_download_video():
    """Test video download from known URL."""
    pass

def test_run_caption():
    """Test caption command execution."""
    pass

def test_read_srt_preview():
    """Test SRT preview extraction."""
    pass
```

### Integration Test
```python
async def test_transcribe_user_reels():
    """End-to-end test with real Instagram reel."""
    result = await transcribe_user_reels("instagram", max_reels=2)
    assert len(result["transcripts"]) > 0
    assert all("srt_path" in t for t in result["transcripts"])
    assert all(Path(t["srt_path"]).exists() for t in result["transcripts"])
```

---

## Dependencies

### Python (add to pyproject.toml)
```toml
[project.dependencies]
httpx = ">=0.27.0"  # For video download
```

### System
- `caption` command in PATH (already at `/home/ishanp/bin/caption`)
- Conda env `whisper-hindi` (already exists)
- `ffmpeg` + `ffprobe` (already installed for caption)

---

## Implementation Phases

### Phase 1: Core Tool (Today - 2 hours)
- [ ] Create `instagram_mcp_server/tools/transcription.py`
- [ ] Implement `download_video()` function
- [ ] Implement `run_caption()` wrapper
- [ ] Create `transcribe_user_reels()` tool
- [ ] Register in server.py

### Phase 2: Polish (Today - 1 hour)
- [ ] Add `transcribe_reel()` for single reel
- [ ] Add progress callbacks
- [ ] Add error handling
- [ ] Write tests

### Phase 3: Documentation (Tomorrow)
- [ ] Update README with new tools
- [ ] Add usage examples
- [ ] Document requirements

---

## Next Steps

1. **Confirm:** Does this plan look correct?
2. **Proceed:** Should I implement Phase 1 now?
