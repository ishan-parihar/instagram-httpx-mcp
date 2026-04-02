# Instagram Reel Transcription

Download Instagram reels and generate SRT subtitle files using Whisper speech-to-text.

---

## Overview

The transcription tools download Instagram reels and convert spoken audio to text using the `caption` command (Whisper-based transcription).

**Use cases:**
- Accessibility (subtitles for hearing impaired)
- Content analysis (search transcripts, extract quotes)
- Translation workflows (translate SRT files)
- Content repurposing (convert reels to blog posts, scripts)

---

## Tools

### `transcribe_user_reels`

Download and transcribe multiple reels from a user's profile.

**Parameters:**
- `username` (required): Instagram username
- `max_reels` (optional): Maximum reels to transcribe (default: 10)
- `keep_videos` (optional): Keep downloaded video files (default: False)

**Example:**
```
Transcribe 5 reels from @natgeo with subtitles
```

**Response:**
```json
{
  "url": "https://www.instagram.com/natgeo/",
  "transcripts": [
    {
      "reel_id": "C0AbCdEfGhI",
      "video_url": "https://scontent.cdninstagram.com/...",
      "srt_path": "/home/user/.instagram-mcp/transcripts/output/C0AbCdEfGhI.srt",
      "transcript_preview": "This incredible footage shows...",
      "reel_url": "https://www.instagram.com/reel/C0AbCdEfGhI/"
    }
  ],
  "total_reels": 5,
  "temp_dir": "/home/user/.instagram-mcp/transcripts/tmp",
  "output_dir": "/home/user/.instagram-mcp/transcripts/output"
}
```

---

### `transcribe_reel`

Transcribe a single reel by URL.

**Parameters:**
- `reel_url` (required): Full Instagram reel URL
- `keep_video` (optional): Keep downloaded video (default: False)

**Example:**
```
Get subtitles for this reel: https://www.instagram.com/reel/C0AbCdEfGhI/
```

**Response:**
```json
{
  "reel_id": "C0AbCdEfGhI",
  "video_url": "https://scontent.cdninstagram.com/...",
  "srt_path": "/home/user/.instagram-mcp/transcripts/output/C0AbCdEfGhI.srt",
  "transcript_preview": "This incredible footage shows...",
  "reel_url": "https://www.instagram.com/reel/C0AbCdEfGhI/"
}
```

---

## Requirements

### System Dependencies

1. **`caption` command** - Whisper transcription wrapper
   - Location: `/home/ishanp/bin/caption`
   - Uses: `whisper_timestamped` with `Oriserve/Whisper-Hindi2Hinglish-Prime` model
   - Conda env: `whisper-hindi`

2. **`ffmpeg` + `ffprobe`** - Audio extraction from videos
   - Install: `sudo apt install ffmpeg` (Ubuntu) or `brew install ffmpeg` (macOS)

### Python Dependencies

- `httpx` - Video download (auto-installed)

---

## How It Works

```
1. Fetch reels from Instagram (get_user_reels)
   ↓
2. Download video files to ~/.instagram-mcp/transcripts/tmp/
   ↓
3. Run `caption` command on each video
   ↓
4. Generate SRT files in ~/.instagram-mcp/transcripts/output/
   ↓
5. Return SRT paths + transcript previews
```

---

## Performance

| Reel Duration | Processing Time |
|---------------|----------------|
| 15 seconds | ~20-30 seconds |
| 30 seconds | ~35-50 seconds |
| 60 seconds | ~60-90 seconds |
| 90 seconds | ~90-120 seconds |

**Bulk Processing:**
- 10 reels (avg 30s each): ~6-8 minutes
- Runs sequentially to avoid rate limiting

---

## Output Format

### SRT Files

Standard SRT subtitle format with timestamps:

```srt
1
00:00:00,000 --> 00:00:05,000
This is the first subtitle line.

2
00:00:05,500 --> 00:00:10,000
Second subtitle line here.
```

### File Locations

- **Temporary videos:** `~/.instagram-mcp/transcripts/tmp/{reel_id}.mp4`
- **SRT output:** `~/.instagram-mcp/transcripts/output/{reel_id}.srt`

By default, temporary videos are deleted after transcription. Use `keep_videos=True` to preserve them.

---

## Usage Examples

### Example 1: Transcribe Nature Reels

```
Transcribe 10 reels from @natgeo for accessibility analysis
```

**Use case:** Create subtitles for educational content

---

### Example 2: Extract Script from Tutorial

```
Get the transcript from https://www.instagram.com/reel/ABC123/
```

**Use case:** Convert tutorial reel to blog post

---

### Example 3: Bulk Content Analysis

```
Download and transcribe all reels from @tech_channel with max_reels=50
```

**Use case:** Analyze content themes across multiple videos

---

## Troubleshooting

### Error: "caption command not found"

**Solution:**
```bash
# Check if caption is in PATH
which caption

# If not found, add to PATH
export PATH="/home/ishanp/bin:$PATH"
```

---

### Error: "whisper-hindi environment not found"

**Solution:**
```bash
# Activate conda environment
conda activate whisper-hindi

# Or reinstall if missing
conda env create -f ~/Documents/GitHub/Whisper-Hindi2Hinglish/environment.yml
```

---

### Error: "Transcription failed"

**Possible causes:**
1. Video has no audio track
2. Video format not supported
3. Whisper model loading failed

**Solution:**
- Check if video plays normally
- Try `transcribe_reel` with a different reel
- Check logs: `~/.instagram-mcp/logs/`

---

### Slow Processing

**Optimization:**
- Reduce `max_reels` for faster results
- Use GPU if available (configured in `caption` command)
- Process during off-peak hours

---

## Advanced Usage

### Using SRT Files

**Convert to other formats:**
```bash
# SRT to TXT (extract just text)
grep -v "^[0-9]" file.srt | grep -v "^$" | grep -v "-->" > transcript.txt

# SRT to JSON (with timestamps)
# Use online converter or Python script
```

**Translation workflow:**
```bash
# 1. Generate SRT
transcribe_user_reels("username", max_reels=5)

# 2. Translate SRT (using translation API or DeepL)
# 3. Merge translated SRT back to video (using ffmpeg)
```

---

## Limitations

1. **Language:** Default model is optimized for Hindi/Hinglish. English-only reels may have lower accuracy.

2. **Audio Quality:** Poor audio quality, background music, or multiple speakers can reduce accuracy.

3. **Rate Limiting:** Instagram may temporarily block bulk downloads. Wait 5-10 minutes between large batches.

4. **Video Length:** Very long reels (>3 minutes) may timeout. Use `transcribe_reel` for individual long videos.

---

## Related Tools

- `get_user_reels` - Get reel metadata without transcription
- `get_post_details` - Get details for individual posts/reels
- `get_business_insights` - Analytics for Business/Creator accounts

---

## Technical Details

### Whisper Model

- **Model:** `Oriserve/Whisper-Hindi2Hinglish-Prime`
- **Framework:** `whisper_timestamped`
- **Device:** CPU (default) or GPU (if configured)
- **Languages:** Optimized for Hindi/Hinglish, supports 99+ languages

### Caption Command

Source: `~/Documents/GitHub/openscript/modules/transcription/`

```bash
caption video.mp4
# Output: video.srt (in current directory)
```

---

## Support

For issues with transcription:
1. Check `caption` command works: `caption --help`
2. Verify Instagram session is active
3. Check logs in `~/.instagram-mcp/logs/`
4. File an issue with error details
