# Instagram Reel Analysis with Google Gemini 2.0 Flash

**Fast AI-powered analysis** - 3x faster than local transcription (~15-25s vs ~50s per reel)

---

## Overview

Gemini 2.0 Flash provides multimodal analysis of Instagram reels, understanding both audio and visual content. Returns structured JSON insights without requiring local transcription.

**Best for:**
- Quick content analysis
- Bulk processing
- Visual content understanding (memes, text overlays)
- Structured insights (topics, quotes, summaries)

---

## Tools

### `analyze_reel_with_gemini`

Analyze a single reel with AI.

**Parameters:**
- `reel_url` (required): Instagram reel URL
- `analysis_type` (optional): Type of analysis
  - `summary` - Quick overview (fastest)
  - `transcript` - Full transcription
  - `topics` - Extract topics and keywords
  - `quotes` - Notable quotes with timestamps
  - `full` - Comprehensive analysis (default)

**Example:**
```
Analyze this reel with AI: https://www.instagram.com/reel/ABC123/
```

**Response (full analysis):**
```json
{
  "reel_id": "ABC123",
  "reel_url": "https://www.instagram.com/reel/ABC123/",
  "analysis_type": "full",
  "model": "gemini-2.0-flash",
  "results": {
    "summary": "This reel demonstrates 5 Python libraries...",
    "transcript": "Hey everyone, today I'm showing you...",
    "topics": ["Python", "Programming", "Data Science"],
    "quotes": [
      {
        "text": "This library will save you hours",
        "timestamp": "0:15",
        "significance": "Key benefit statement"
      }
    ],
    "sentiment": "positive",
    "insights": ["Install pandas for data manipulation"],
    "category": "Educational/Technology"
  }
}
```

---

### `bulk_analyze_reels_with_gemini`

Analyze multiple reels from a user.

**Parameters:**
- `username` (required): Instagram username
- `max_reels` (optional): Maximum reels to analyze (default: 5)
- `analysis_type` (optional): Analysis type (default: summary for speed)

**Example:**
```
Analyze 10 reels from @natgeo with AI summary
```

**Response:**
```json
{
  "username": "natgeo",
  "total_reels": 10,
  "successful": 9,
  "failed": 1,
  "analysis_type": "summary",
  "analyses": [
    {
      "reel_id": "ABC123",
      "status": "success",
      "analysis": {
        "summary": "Wildlife footage showing...",
        "topic": "Nature/Wildlife",
        "audience": "Nature enthusiasts",
        "takeaway": "Conservation importance"
      }
    }
  ]
}
```

---

## Speed Comparison

| Method | Time per Reel | Best For |
|--------|---------------|----------|
| **Gemini (summary)** | ~15s | Quick overview |
| **Gemini (full)** | ~20-25s | Comprehensive analysis |
| **Local Whisper** | ~40-60s | Accurate timestamps |

**Gemini is 2-3x faster** because:
1. No local download (direct URL processing)
2. Cloud-based GPU acceleration
3. Combined analysis (no separate transcription step)

---

## Cost

**Gemini 2.0 Flash Pricing:**
- Input: $0.075 / 1M tokens
- Output: $0.30 / 1M tokens
- Video: ~500 tokens per minute

**Per Reel (30 seconds):**
- Processing: ~250 tokens = $0.000019
- Output: ~500 tokens = $0.00015
- **Total: ~$0.00017 per reel**

**Monthly Estimates:**
| Reels/Month | Cost |
|-------------|------|
| 100 | $0.017 |
| 1,000 | $0.17 |
| 10,000 | $1.70 |
| 100,000 | $17.00 |

**Verdict:** Extremely affordable for the speed gain.

---

## Analysis Types

### Summary (Fastest)
```json
{
  "summary": "One-sentence overview",
  "topic": "Main category",
  "audience": "Target viewers",
  "takeaway": "Key point"
}
```

**Use case:** Quick content scanning, feed curation

---

### Transcript
```json
{
  "transcript": "Full text...",
  "segments": [
    {"start": 0, "end": 10, "text": "Intro...", "speaker": "Speaker 1"},
    {"start": 10, "end": 20, "text": "Main content...", "speaker": "Speaker 1"}
  ]
}
```

**Use case:** Content repurposing, blog posts

---

### Topics
```json
{
  "main_topic": "Python Programming",
  "subtopics": ["Data Analysis", "Pandas", "Visualization"],
  "keywords": ["library", "data", "code", "analysis"],
  "hashtags": ["#python", "#coding", "#datascience"]
}
```

**Use case:** SEO, hashtag research, content categorization

---

### Quotes
```json
{
  "quotes": [
    {
      "text": "Exact quote text",
      "timestamp": "0:15",
      "significance": "Why it matters"
    }
  ]
}
```

**Use case:** Social media posts, marketing materials

---

### Full (Comprehensive)
```json
{
  "summary": "...",
  "transcript": "...",
  "topics": [...],
  "quotes": [...],
  "sentiment": "positive",
  "insights": ["Actionable takeaway 1", "..."],
  "category": "Educational"
}
```

**Use case:** Complete content analysis, research

---

## API Key Configuration

The Gemini API key is pre-configured in the code:
```python
GEMINI_API_KEY = "REDACTED_GOOGLE_API_KEY_1"
```

**To use your own key:**
1. Get API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Edit `instagram_mcp_server/tools/gemini_analysis.py`
3. Replace `GEMINI_API_KEY` value

---

## Use Cases

### 1. Content Research
```
Analyze 20 reels from @competitor with topics analysis
```
**Result:** Understand competitor content strategy

---

### 2. Trend Analysis
```
Bulk analyze reels from @tech_influencers with summary
```
**Result:** Identify trending topics in your niche

---

### 3. Content Repurposing
```
Get transcript from https://www.instagram.com/reel/ABC123/
```
**Result:** Convert reel to blog post or article

---

### 4. Quote Extraction
```
Extract quotes from this motivational reel
```
**Result:** Shareable quotes for social media

---

### 5. Sentiment Analysis
```
Analyze brand mentions with full analysis
```
**Result:** Understand public sentiment about your brand

---

## Comparison: Gemini vs Local Transcription

| Feature | Gemini 2.0 Flash | Local Whisper |
|---------|------------------|---------------|
| **Speed** | 15-25s | 40-60s |
| **Accuracy** | ~90% | ~95% |
| **Timestamps** | Segment-level | Word-level |
| **Visual Analysis** | ✅ Yes | ❌ No |
| **Structured Output** | ✅ JSON | ❌ Manual parsing |
| **Cost** | ~$0.00017/reel | Free |
| **Privacy** | Cloud processing | Local only |
| **Dependencies** | None | ffmpeg, conda |

**Use Gemini when:**
- Speed is priority
- Need visual context (memes, text overlays)
- Want structured JSON output
- Processing in bulk

**Use Local Whisper when:**
- Need word-level timestamps
- Privacy required
- Offline processing
- Maximum accuracy

---

## Troubleshooting

### Error: "API key not valid"

**Solution:**
```python
# Check API key in gemini_analysis.py
# Get new key from https://makersuite.google.com/app/apikey
```

---

### Error: "Rate limit exceeded"

**Solution:**
- Free tier: 15 requests per minute
- Wait 5 seconds between requests
- Or upgrade to paid tier (1000 RPM)

---

### Error: "Video too long"

**Solution:**
- Gemini has 10 minute video limit
- Use local transcription for longer videos
- Or split into segments

---

### Poor Analysis Quality

**Solutions:**
1. Try `analysis_type="full"` for more context
2. Check video has clear audio
3. Ensure video is not heavily edited/fast-paced
4. Use local Whisper for critical accuracy

---

## Advanced Usage

### Custom Prompts

Modify `prompts` dict in `analyze_with_gemini()`:

```python
prompts["custom"] = """Your custom prompt here.
Ask for specific format.
Respond in JSON."""
```

---

### Parallel Processing

For bulk analysis (advanced):
```python
import asyncio

# Process 5 reels in parallel
tasks = [analyze_reel(url) for url in reel_urls[:5]]
results = await asyncio.gather(*tasks)
```

**Warning:** May hit rate limits. Use sequential for large batches.

---

### Save Results

Analysis results are automatically saved to:
```
~/.instagram-mcp/gemini_analysis/{reel_id}_{type}.json
```

---

## Related Tools

- `transcribe_user_reels` - Local Whisper transcription (free, accurate)
- `get_user_reels` - Get reel metadata only
- `get_post_details` - Individual post analysis

---

## Support

For issues:
1. Check API key is valid
2. Verify reel URL is public
3. Check rate limits (15 RPM free tier)
4. Review logs: `~/.instagram-mcp/logs/`
