# Instagram Reel Transcription Tool - Implementation Investigation

**Date:** 2026-04-02  
**Feature:** Bulk reel download + Whisper transcription → SRT subtitle files  
**Status:** Investigation & Design Phase

---

## Executive Summary

**Goal:** Implement a tool that downloads Instagram reels in bulk and generates SRT subtitle files using speech-to-text transcription, allowing users to know "which reel has which script."

**Feasibility:** ✅ **Technically feasible** with existing libraries  
**Complexity:** Medium-High (requires video processing + ML inference)  
**Estimated Development Time:** 2-3 days  
**Dependencies:** `faster-whisper`, `yt-dlp` or `httpx`, `ffmpeg`

---

## Technical Architecture

### Proposed Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Request                                  │
│  "Transcribe reels from @username"                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Get User Reels (Existing Tool)                         │
│  - Call get_user_reels()                                        │
│  - Extract video_url for each reel                              │
│  - Get metadata (caption, views, timestamp, reel_id)            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: Bulk Download Videos                                   │
│  - Download video files from video_url                          │
│  - Save to temp directory: ~/.instagram-mcp/transcripts/tmp/    │
│  - Name format: {reel_id}.mp4                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: Extract Audio (ffmpeg)                                 │
│  - Extract audio track from each video                          │
│  - Convert to WAV/MP3 for Whisper                               │
│  - Save as {reel_id}.wav                                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 4: Transcribe with Whisper                                │
│  - Run faster-whisper on each audio file                        │
│  - Generate SRT with timestamps                                 │
│  - Save as {reel_id}.srt                                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 5: Return Results                                         │
│  - Map reel_id → SRT file path                                  │
│  - Include transcript preview in response                       │
│  - Clean up temp files (optional)                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Options

### Option 1: Use `faster-whisper` Python Library (Recommended)

**Pros:**
- ✅ Fast inference (CTranslate2 backend)
- ✅ SRT output built-in
- ✅ 99+ languages supported
- ✅ Runs locally (no API costs)
- ✅ GPU acceleration optional
- ✅ Active maintenance

**Cons:**
- ⚠️ Requires `faster-whisper` dependency (~2GB models)
- ⚠️ First run downloads model (100MB-3GB depending on size)

**Installation:**
```bash
uv add faster-whisper
# Also need ffmpeg for audio extraction
# Ubuntu: sudo apt install ffmpeg
# macOS: brew install ffmpeg
```

**Usage Example:**
```python
from faster_whisper import WhisperModel

model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe("audio.wav", word_timestamps=True)

# Generate SRT
with open("output.srt", "w") as f:
    for i, segment in enumerate(segments, 1):
        f.write(f"{i}\n")
        f.write(f"{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}\n")
        f.write(f"{segment.text.strip()}\n\n")
```

**Model Sizes:**
| Model | Size | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| `tiny` | 75MB | Fastest | ~60% | Quick tests |
| `base` | 142MB | Fast | ~70% | Casual use |
| `small` | 466MB | Medium | ~80% | **Recommended** |
| `medium` | 1.5GB | Slow | ~90% | High accuracy |
| `large-v3` | 3GB | Slowest | ~95% | Production |

---

### Option 2: Use `whisper-cli` (OpenAI Official)

**Pros:**
- ✅ Official OpenAI implementation
- ✅ SRT output supported (`--output_format srt`)
- ✅ Simple CLI interface

**Cons:**
- ❌ Slower than faster-whisper (5-10x)
- ❌ No GPU optimization by default
- ❌ Larger memory footprint

**Usage:**
```bash
pip install openai-whisper
whisper audio.wav --model small --output_format srt --output_dir ./transcripts
```

---

### Option 3: Use AssemblyAI API (Cloud Service)

**Pros:**
- ✅ No local ML dependencies
- ✅ Very fast (cloud GPUs)
- ✅ High accuracy
- ✅ Speaker diarization available

**Cons:**
- ❌ Requires API key ($0.000125/second = ~$0.45/hour)
- ❌ Upload/download overhead
- ❌ Privacy concerns (audio sent to third party)

**Usage:**
```python
import assemblyai as aai

aai.settings.api_key = "YOUR_API_KEY"
transcriber = aai.Transcriber()
transcript = transcriber.transcribe("audio.wav")
transcript.export_subs("output.srt")
```

---

## Video Download Implementation

### Method 1: Direct HTTP Download (Recommended for CDP Mode)

Since we already have `video_url` from the CDP scraper, we can download directly:

```python
import httpx
from pathlib import Path

async def download_video(video_url: str, output_path: Path) -> bool:
    """Download video from Instagram URL."""
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", video_url) as response:
            if response.status_code != 200:
                return False
            
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
    return True
```

**Pros:**
- ✅ No additional dependencies (uses existing `httpx`)
- ✅ Fast (direct download)
- ✅ Works with CDP mode

**Cons:**
- ⚠️ Video URLs may expire (need to download quickly)
- ⚠️ Some reels may have DRM protection

---

### Method 2: Use `yt-dlp`

**Pros:**
- ✅ Handles URL expiration
- ✅ Retry logic built-in
- ✅ Supports many sites

**Cons:**
- ❌ Additional dependency
- ❌ Slower than direct download
- ❌ May break with Instagram changes

```python
import yt_dlp

def download_with_ytdlp(video_url: str, output_dir: str) -> str:
    ydl_opts = {
        'outtmpl': f'{output_dir}/%(id)s.%(ext)s',
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return ydl.prepare_filename(info)
```

---

## Audio Extraction

### Using `ffmpeg-python`

```python
import ffmpeg

def extract_audio(video_path: Path, audio_path: Path) -> bool:
    """Extract audio from video file."""
    try:
        (
            ffmpeg
            .input(str(video_path))
            .output(str(audio_path), acodec='pcm_s16le', ar='16000')
            .run(quiet=True, overwrite_output=True)
        )
        return True
    except ffmpeg.Error as e:
        logger.error(f"ffmpeg error: {e.stderr.decode()}")
        return False
```

**Requirements:**
- System-level `ffmpeg` installation
- `ffmpeg-python` Python package

**Alternative:** Use `pydub` (simpler but requires ffmpeg anyway)

---

## Proposed Tool Design

### New Tool: `transcribe_user_reels`

```python
@mcp.tool(
    timeout=300.0,  # 5 minutes for bulk transcription
    title="Transcribe User Reels",
    annotations={"readOnlyHint": True},
    tags={"reels", "transcription", "accessibility"},
)
async def transcribe_user_reels(
    username: str,
    ctx: Context,
    max_reels: int = 10,
    whisper_model: str = "small",  # tiny, base, small, medium, large-v3
    output_format: str = "srt",  # srt, vtt, txt, json
    keep_videos: bool = False,  # Delete temp files after transcription
    language: str = "en",  # Auto-detect if not specified
) -> dict[str, Any]:
    """
    Download and transcribe Instagram reels with SRT subtitles.
    
    Downloads reels, extracts audio, and generates subtitle files using Whisper AI.
    Returns mapping of reel URLs to transcript files and preview text.
    
    Args:
        username: Instagram username (e.g., "instagram", "natgeo")
        ctx: FastMCP context for progress reporting
        max_reels: Maximum reels to transcribe (default: 10)
        whisper_model: Whisper model size (tiny/base/small/medium/large-v3)
        output_format: Subtitle format (srt/vtt/txt/json)
        keep_videos: Keep downloaded video files (default: False)
        language: Language code for transcription (default: auto-detect)
    
    Returns:
        Dict with:
        - url: Instagram profile URL
        - transcripts: List of {reel_id, video_url, srt_path, transcript_preview, duration}
        - total_reels: Number of reels processed
        - total_duration: Total audio duration transcribed
    """
```

### Response Format

```json
{
  "url": "https://www.instagram.com/username/",
  "transcripts": [
    {
      "reel_id": "C0AbCdEfGhI",
      "video_url": "https://scontent.cdninstagram.com/...",
      "srt_path": "/home/user/.instagram-mcp/transcripts/C0AbCdEfGhI.srt",
      "transcript_preview": "Hey everyone, today I'm going to show you...",
      "duration_seconds": 45.2,
      "word_count": 120,
      "language_detected": "en"
    }
  ],
  "total_reels": 5,
  "total_duration_seconds": 226.0,
  "processing_time_seconds": 89.3
}
```

---

## Directory Structure

```
~/.instagram-mcp/
├── profile/                    # Existing browser profile
├── cookies.json                # Existing session cookies
├── source-state.json           # Existing auth state
└── transcripts/                # NEW: Transcription output
    ├── tmp/                    # Temporary video/audio files
    │   ├── C0AbCdEfGhI.mp4
    │   ├── C0AbCdEfGhI.wav
    │   └── ...
    └── output/                 # Final SRT files
        ├── C0AbCdEfGhI.srt
        ├── C0AbCdEfGhI.json    # Optional: JSON with metadata
        └── manifest.json       # Index of all transcripts
```

---

## Dependencies to Add

### `pyproject.toml`

```toml
[project.optional-dependencies]
transcription = [
    "faster-whisper>=1.0.0",    # Whisper transcription
    "ffmpeg-python>=0.2.0",     # Audio extraction
    "httpx>=0.27.0",            # Video download (already installed)
]

# Or add to main dependencies if always needed
[project.dependencies]
faster-whisper = ">=1.0.0"
ffmpeg-python = ">=0.2.0"
```

### System Requirements

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Arch
sudo pacman -S ffmpeg
```

---

## Performance Estimates

### Processing Time (per 60-second reel)

| Step | CPU (i7) | GPU (RTX 3060) |
|------|----------|----------------|
| Download video | 2-5s | 2-5s |
| Extract audio | 1-2s | 1-2s |
| Transcribe (small) | 15-20s | 3-5s |
| **Total per reel** | **18-27s** | **6-12s** |

### Batch Processing (10 reels, avg 60s each)

| Model | CPU Time | GPU Time |
|-------|----------|----------|
| `tiny` | ~2 min | ~30s |
| `base` | ~3 min | ~45s |
| `small` | ~4 min | ~1 min |
| `medium` | ~8 min | ~2 min |

---

## Error Handling

### Common Failure Modes

1. **Video Download Fails**
   - URL expired → Re-fetch from Instagram
   - DRM protected → Skip with warning
   - Network error → Retry 3x with backoff

2. **Audio Extraction Fails**
   - Corrupt video → Skip reel
   - ffmpeg not installed → Helpful error message

3. **Transcription Fails**
   - No audio in reel → Return empty transcript
   - Unsupported language → Auto-detect fallback
   - OOM (out of memory) → Use smaller model

### Graceful Degradation

```python
try:
    # Try GPU first
    model = WhisperModel("small", device="cuda")
except Exception:
    try:
        # Fallback to CPU with smaller model
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        logger.warning("GPU not available, using CPU with tiny model")
    except Exception as e:
        raise ToolError(f"Whisper initialization failed: {e}")
```

---

## Security & Privacy Considerations

### Data Storage
- ✅ All processing local (no cloud uploads)
- ✅ Videos deleted after transcription (default)
- ✅ SRT files stored in user-controlled directory

### Rate Limiting
- ⚠️ Bulk downloads may trigger Instagram rate limits
- ✅ Implement delay between downloads (1-2s)
- ✅ Respect Instagram's ToS

### Model Licensing
- ✅ Whisper: MIT License (OpenAI)
- ✅ faster-whisper: MIT License
- ✅ Commercial use allowed

---

## Testing Strategy

### Unit Tests
```python
def test_download_video():
    """Test video download from known URL."""
    pass

def test_extract_audio():
    """Test audio extraction from test video."""
    pass

def test_transcribe_audio():
    """Test Whisper transcription on sample audio."""
    pass

def test_generate_srt():
    """Test SRT file format generation."""
    pass
```

### Integration Tests
```python
async def test_transcribe_user_reels():
    """End-to-end test with real Instagram reel."""
    result = await transcribe_user_reels("instagram", max_reels=2)
    assert len(result["transcripts"]) == 2
    assert all("srt_path" in t for t in result["transcripts"])
```

---

## Implementation Phases

### Phase 1: Core Functionality (Day 1)
- [ ] Add `faster-whisper` and `ffmpeg-python` dependencies
- [ ] Implement video download function
- [ ] Implement audio extraction function
- [ ] Implement Whisper transcription function
- [ ] Create SRT generation utility

### Phase 2: Tool Integration (Day 2)
- [ ] Create `transcribe_user_reels` MCP tool
- [ ] Add progress callbacks for long operations
- [ ] Implement error handling and retries
- [ ] Add cleanup for temp files
- [ ] Write unit tests

### Phase 3: Polish & Documentation (Day 3)
- [ ] Add configuration options (model size, language, format)
- [ ] Write tool documentation
- [ ] Add examples to README
- [ ] Performance optimization (batching, parallel processing)
- [ ] Integration tests

---

## Alternative: Simpler Approach

If full implementation is too complex, start with a **caption-only tool** that:

1. Uses existing `caption` field from reel metadata
2. Downloads video only (no transcription)
3. Returns video + caption mapping

```python
@mcp.tool(...)
async def download_reels_with_captions(
    username: str,
    max_reels: int = 50,
    output_dir: str = "~/.instagram-mcp/reels/",
) -> dict[str, Any]:
    """
    Download reels with their existing captions.
    
    Simpler alternative to full transcription.
    Returns video files + caption text (if creator added captions).
    """
```

**Pros:**
- ✅ Much simpler (no ML, no ffmpeg)
- ✅ Faster (download only)
- ✅ No additional dependencies

**Cons:**
- ❌ Only works if creator added captions
- ❌ No speech-to-text for spoken content
- ❌ Less useful for accessibility

---

## Recommendation

**Proceed with full implementation** using:
1. `faster-whisper` for transcription (best speed/accuracy tradeoff)
2. Direct HTTP download (leverages existing CDP session)
3. `ffmpeg` for audio extraction (industry standard)
4. Start with `small` model (good balance of speed/accuracy)

**Justification:**
- High user value (accessibility, content analysis, SEO)
- Technically feasible with mature libraries
- Local processing (privacy, no API costs)
- Can start simple and add features incrementally

---

## Next Steps

1. **Get user confirmation** on feature scope
2. **Add dependencies** to `pyproject.toml`
3. **Implement Phase 1** (core functions)
4. **Test with sample reels**
5. **Iterate based on feedback**

---

**Questions for User:**
1. Do you want GPU acceleration support? (adds complexity but 3-5x faster)
2. Should transcripts be saved permanently or temp-only?
3. Preferred default model size? (recommend `small`)
4. Need multi-language support beyond English?
5. Should we also transcribe regular video posts or just reels?
