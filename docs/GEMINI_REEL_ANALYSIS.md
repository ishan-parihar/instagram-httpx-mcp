# Instagram Reel Analysis with Gemini 2.0 Flash

**Investigation:** Use Google's Gemini 2.0 Flash (multimodal) for direct reel analysis instead of local Whisper transcription.

---

## Comparison: Local Whisper vs Gemini 2.0 Flash

### Current Approach (Local Whisper)

```
Download Video → Extract Audio → Whisper Transcription → SRT → Analysis
     5-10s           2-5s          30-60s         1s      (separate)
     
Total: ~40-80s per reel
```

**Pros:**
- ✅ Free (no API costs)
- ✅ Local processing (privacy)
- ✅ Accurate timestamps (word-level)
- ✅ Works offline

**Cons:**
- ❌ Slow (30-60s transcription alone)
- ❌ Requires ffmpeg + conda env
- ❌ Two-step process (transcribe then analyze)
- ❌ CPU intensive

---

### Proposed Approach (Gemini 2.0 Flash)

```
Send Video URL → Gemini 2.0 Flash → Structured Analysis
     1-2s            10-20s           1s

Total: ~15-25s per reel
```

**Pros:**
- ✅ **3-4x faster** (15-25s vs 40-80s)
- ✅ No local dependencies (no ffmpeg, no conda)
- ✅ Direct analysis (skip transcription step)
- ✅ Multimodal (understands visuals + audio)
- ✅ Structured output (JSON)
- ✅ Can analyze multiple reels in parallel

**Cons:**
- ⚠️ API costs (~$0.075 per 1M input tokens, ~$0.30 per 1M output tokens)
- ⚠️ Requires internet
- ⚠️ Rate limits (15 RPM free tier, 1000 RPM paid)
- ⚠️ No word-level timestamps

---

## Cost Estimation

**Gemini 2.0 Flash Pricing:**
- Input: $0.075 / 1M tokens
- Output: $0.30 / 1M tokens
- Video: ~500 tokens per minute of video

**Per Reel (30 seconds):**
- Video processing: ~250 tokens = $0.000019
- Analysis output: ~500 tokens = $0.00015
- **Total: ~$0.00017 per reel**

**100 reels/month:** ~$0.017  
**1000 reels/month:** ~$0.17  
**10,000 reels/month:** ~$1.70

**Verdict:** Extremely cheap for the speed gain.

---

## Implementation Design

### New Tool: `analyze_reel_with_gemini`

```python
@mcp.tool(timeout=120.0, title="Analyze Reel with Gemini")
async def analyze_reel_with_gemini(
    reel_url: str,
    ctx: Context,
    analysis_type: str = "summary",  # summary, transcript, topics, quotes
    language: str = "en",
) -> dict[str, Any]:
    """
    Analyze Instagram reel using Gemini 2.0 Flash.
    
    Sends video directly to Gemini for multimodal analysis.
    Returns structured insights without local transcription.
    """
```

### Gemini API Integration

```python
import google.generativeai as genai

genai.configure(api_key="REDACTED_GOOGLE_API_KEY_1")

model = genai.GenerativeModel("gemini-2.0-flash")

# Option 1: Direct video URL (Gemini fetches)
response = await model.generate_content_async([
    "Analyze this Instagram reel. Provide:",
    "1. Summary of content",
    "2. Key topics discussed",
    "3. Notable quotes",
    "4. Sentiment (positive/negative/neutral)",
    video_url
])

# Option 2: Download + upload (more reliable)
video_data = await download_video(video_url)
response = await model.generate_content_async([
    "Transcribe and analyze this video...",
    video_data  # bytes
])
```

---

## Analysis Types

### 1. Summary
```json
{
  "summary": "This reel explains 5 Python libraries for data analysis...",
  "duration_seconds": 45,
  "language": "en",
  "speaker_count": 1
}
```

### 2. Transcript
```json
{
  "transcript": "Hey everyone, today I'm going to show you...",
  "segments": [
    {"start": 0, "end": 5, "text": "Introduction"},
    {"start": 5, "end": 20, "text": "Library 1: Pandas"},
    ...
  ]
}
```

### 3. Topics
```json
{
  "topics": ["Python", "Data Analysis", "Pandas", "Visualization"],
  "keywords": ["library", "data", "analysis", "code"],
  "category": "Education/Technology"
}
```

### 4. Quotes
```json
{
  "quotes": [
    {
      "text": "This library will save you hours of work",
      "timestamp": "0:15",
      "context": "Discussing Pandas merge function"
    }
  ]
}
```

### 5. Full Analysis
```json
{
  "summary": "...",
  "transcript": "...",
  "topics": [...],
  "quotes": [...],
  "sentiment": "positive",
  "actionable_insights": ["Install pandas", "Try merge function"]
}
```

---

## Speed Comparison

| Operation | Local Whisper | Gemini 2.0 Flash | Speedup |
|-----------|---------------|------------------|---------|
| Download | 5s | 2s (direct URL) | 2.5x |
| Process | 40s | 15s | 2.7x |
| Analysis | 5s (separate) | Included | ∞ |
| **Total** | **50s** | **17s** | **~3x** |

---

## Hybrid Approach (Best of Both)

```python
async def analyze_reel(
    reel_url: str,
    use_gemini: bool = True,  # Toggle between approaches
    analysis_type: str = "full"
):
    if use_gemini:
        # Fast cloud analysis
        return await gemini_analyze(reel_url, analysis_type)
    else:
        # Local transcription (free, private)
        srt_path = await local_transcribe(reel_url)
        return await analyze_srt(srt_path, analysis_type)
```

**Use Gemini when:**
- Speed is priority
- Need visual analysis (not just audio)
- Want structured insights

**Use Local when:**
- Privacy required
- Offline processing
- Need word-level timestamps
- Budget constraints (though Gemini is very cheap)

---

## Implementation Plan

### Phase 1: Basic Integration (30 min)
- [ ] Add `google-generativeai` dependency
- [ ] Create `gemini_analyze_reel()` function
- [ ] Test with sample reel URLs

### Phase 2: Analysis Types (1 hour)
- [ ] Implement summary mode
- [ ] Implement transcript mode
- [ ] Implement topics/quotes extraction
- [ ] Add full analysis mode

### Phase 3: Hybrid Tool (30 min)
- [ ] Create unified `analyze_reel()` tool
- [ ] Add `use_gemini` toggle
- [ ] Document tradeoffs
- [ ] Update README

---

## Sample Prompts

### Summary Prompt
```
You are analyzing an Instagram reel. Provide:
1. One-sentence summary
2. Main topic/category
3. Target audience
4. Key takeaway

Format as JSON.
```

### Transcript Prompt
```
Transcribe this video verbatim. Include:
- Speaker identification (if multiple)
- Timestamp every 10 seconds
- Note background music/sound effects

Format as JSON with segments array.
```

### Topics Prompt
```
Extract topics from this reel:
1. Main topic (broad category)
2. Subtopics (specific subjects)
3. Keywords (5-10 terms)
4. Related hashtags for Instagram

Format as JSON.
```

### Quotes Prompt
```
Extract 3-5 notable quotes:
- Exact wording
- Approximate timestamp
- Why it's significant

Format as JSON array.
```

---

## Recommendation

**Use Gemini 2.0 Flash for:**
1. **Quick analysis** - 3x faster, good enough accuracy
2. **Bulk processing** - Parallel requests, no local bottlenecks
3. **Visual content** - Understands memes, text overlays, visuals
4. **Structured output** - Direct JSON, no parsing needed

**Keep Local Whisper for:**
1. **Accuracy-critical** - Word-level timestamps
2. **Privacy-sensitive** - No data leaves machine
3. **Offline use** - No internet required
4. **Budget** - Free (though Gemini is ~$0.00017/reel)

**Best approach:** Implement both, let user choose based on needs.

---

## Next Steps

1. **Test Gemini API** with sample reel
2. **Compare accuracy** vs local Whisper
3. **Implement hybrid tool** with toggle
4. **Document cost/speed tradeoffs**

Should I proceed with implementation?
