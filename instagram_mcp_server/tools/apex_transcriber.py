"""
Apex Transcription Engine — Oriserve/Whisper-Hindi2Hinglish-Apex.

Native transcription using the Apex Whisper model via the whisper-hindi
conda environment. Replaces the fragile `caption` bash CLI wrapper.

APEX IS THE ONLY TRANSCRIPTION MODEL. NO FALLBACKS. NO ALTERNATIVES.
"""

import logging
import os
import shlex
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

APEX_MODEL = "Oriserve/Whisper-Hindi2Hinglish-Apex"


def _log(msg: str) -> None:
    """Log transcription progress at debug level."""
    logger.debug("[apex] %s", msg)


def _find_whisper_python() -> str:
    """Find the whisper-hindi conda env python.

    Search order:
    1. $WHISPER_HINDI_PYTHON env var
    2. ~/miniconda3/envs/whisper-hindi/bin/python3.11
    3. ~/miniconda3/envs/whisper-hindi/bin/python3
    4. ~/miniconda3/envs/whisper-hindi/bin/python
    5. ~/anaconda3/envs/whisper-hindi/bin/python3.11

    Returns:
        Path to conda python.

    Raises:
        RuntimeError: If no conda python found.
    """
    env_python = os.environ.get("WHISPER_HINDI_PYTHON")
    if env_python and Path(env_python).exists():
        return env_python

    home = Path.home()
    candidates = [
        home / "miniconda3" / "envs" / "whisper-hindi" / "bin" / "python3.11",
        home / "miniconda3" / "envs" / "whisper-hindi" / "bin" / "python3",
        home / "miniconda3" / "envs" / "whisper-hindi" / "bin" / "python",
        home / "anaconda3" / "envs" / "whisper-hindi" / "bin" / "python3.11",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    raise RuntimeError(
        "whisper-hindi conda environment Python not found. "
        "Set WHISPER_HINDI_PYTHON env var or ensure conda env 'whisper-hindi' exists."
    )


def _is_apex_healthy() -> bool:
    """Check if the Apex transcription environment is functional.

    Returns True if conda python is found and whisper_timestamped imports cleanly.
    """
    try:
        python = _find_whisper_python()
    except RuntimeError:
        return False

    try:
        result = subprocess.run(
            [python, "-c", "import whisper_timestamped"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def extract_audio(video_path: str, wav_path: str) -> bool:
    """Extract 16kHz mono WAV from video using ffmpeg.

    Args:
        video_path: Path to input video/audio file.
        wav_path: Path to output WAV file.

    Returns:
        True on success, False on failure.
    """
    cmd = (
        "ffmpeg -y -i "
        + shlex.quote(os.path.abspath(video_path))
        + " -vn -acodec pcm_s16le -ar 16000 -ac 1 "
        + shlex.quote(os.path.abspath(wav_path))
    )
    _log("Extracting audio...")
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        logger.error("Audio extraction failed: %s", result.stderr[:300])
        return False
    _log(f"Audio extracted: {wav_path}")
    return True


def _run_apex_transcription(
    whisper_python: str,
    wav_path: str,
    out_dir: str,
    stem: str,
) -> dict:
    """Run Apex transcription in a subprocess inside the whisper-hindi conda env.

    Runs on CPU to avoid VRAM conflicts.

    Returns:
        dict with text_preview, word_count, word_srt_path, phrase_srt_path, text_path.
        On error, dict with "error" key.
    """
    text_out = os.path.join(out_dir, stem + ".apex.txt")
    word_srt_out = os.path.join(out_dir, stem + ".apex.word.srt")
    phrase_srt_out = os.path.join(out_dir, stem + ".apex.phrase.srt")

    script = (
        """
import os
import sys
import time
import torch
import whisper_timestamped as whisper

audio_path = """
        + repr(wav_path)
        + """
text_out = """
        + repr(text_out)
        + """
word_srt_out = """
        + repr(word_srt_out)
        + """
phrase_srt_out = """
        + repr(phrase_srt_out)
        + """

_log = lambda m: print("[apex:worker] " + str(m), file=sys.stderr, flush=True)

def fmt_ts(s):
    ms = round((s % 1) * 1000) % 1000
    s_int = int(s)
    return "%02d:%02d:%02d,%03d" % (s_int // 3600, (s_int % 3600) // 60, s_int % 60, ms)

torch.set_num_threads(int(os.environ.get("TTS_THREADS", "8")))
_log("Loading Whisper-Hindi2Hinglish-Apex model (CPU)...")
model = whisper.load_model(\""""
        + APEX_MODEL
        + """\", device="cpu")
_log("Model loaded. Transcribing...")

audio = whisper.load_audio(audio_path)
duration = len(audio) / 16000.0
_log("Audio loaded: %.1fs" % duration)

start = time.time()
result = whisper.transcribe(
    model, audio,
    language="hi",
    condition_on_previous_text=False,
    remove_empty_words=True,
)
elapsed = time.time() - start
_log("Transcription done in %.0fs (%.1f min, %.1fx real-time)" % (elapsed, elapsed/60, elapsed/duration if duration > 0 else 0))

# Extract full text
text = " ".join(seg["text"].strip() for seg in result["segments"])
with open(text_out, "w", encoding="utf-8") as f:
    f.write(text + "\\n")

print(text[:200])
print(str(len(text.split())))

# Extract word-level timestamps
all_words = []
for seg in result["segments"]:
    if "words" in seg and seg["words"]:
        all_words.extend(seg["words"])

_log("Word-level timestamps: %d" % len(all_words))

with open(word_srt_out, "w", encoding="utf-8") as f:
    for i, w in enumerate(all_words, 1):
        f.write("%d\\n%s --> %s\\n%s\\n\\n" % (
            i, fmt_ts(w["start"]), fmt_ts(w["end"]), w["text"].strip()
        ))

# Generate phrase-level SRT (group words into ~3-5s phrases)
def group_words(words, max_words=12, max_chars=64, max_gap=0.6):
    groups = []
    cur_words = []
    cur_start = None
    cur_end = None
    for w in words:
        t = w["text"].strip()
        if not t:
            continue
        if cur_start is None:
            cur_start = w["start"]
            cur_end = w["end"]
            cur_words = [t]
            continue
        gap = w["start"] - (cur_end or w["start"])
        combined = " ".join(cur_words)
        next_len = len(combined) + 1 + len(t)
        if gap > max_gap or len(cur_words) >= max_words or next_len > max_chars:
            groups.append((" ".join(cur_words), cur_start, cur_end))
            cur_start = w["start"]
            cur_end = w["end"]
            cur_words = [t]
        else:
            cur_words.append(t)
            cur_end = w["end"]
    if cur_words:
        groups.append((" ".join(cur_words), cur_start, cur_end))
    return groups

groups = group_words(all_words)
with open(phrase_srt_out, "w", encoding="utf-8") as f:
    for i, (text, start, end) in enumerate(groups, 1):
        f.write("%d\\n%s --> %s\\n%s\\n\\n" % (i, fmt_ts(start), fmt_ts(end), text))

_log("Phrase SRT: %d phrases, avg %.1fs" % (
    len(groups),
    sum(e - s for _, s, e in groups) / max(1, len(groups))
))

del model
import gc; gc.collect()
_log("Done.")
"""
    )

    _log("Running Apex transcription (CPU)...")
    result = subprocess.run(
        [whisper_python, "-c", script],
        capture_output=True,
        text=True,
        timeout=1800,  # 30min timeout for long videos
    )

    if result.returncode != 0:
        stderr_tail = result.stderr[-2000:] if result.stderr else "No stderr output"
        logger.error("Apex transcription failed: %s", stderr_tail)
        return {"error": stderr_tail}

    lines = result.stdout.strip().split("\n")
    text_preview = lines[0] if lines else ""
    word_count = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else 0

    for out_file in [word_srt_out, phrase_srt_out, text_out]:
        if not Path(out_file).exists() or Path(out_file).stat().st_size == 0:
            return {
                "error": f"Output file missing or empty: {out_file}",
            }

    _log(f"Apex transcription complete: {word_count} words")
    return {
        "text_preview": text_preview,
        "word_count": word_count,
        "word_srt_path": word_srt_out,
        "phrase_srt_path": phrase_srt_out,
        "text_path": text_out,
    }


def transcribe_video(video_path: str, output_srt_path: str) -> str | None:
    """Transcribe a video file to SRT using the Apex Whisper model.

    Pipeline:
    1. Extract 16kHz mono WAV audio via ffmpeg
    2. Run Apex transcription in whisper-hindi conda env
    3. Copy phrase-level SRT to output_srt_path

    Args:
        video_path: Path to input video file.
        output_srt_path: Where to write the final SRT file.

    Returns:
        Path to output SRT file on success, None on failure.
    """
    try:
        whisper_python = _find_whisper_python()
    except RuntimeError as e:
        logger.error("Apex transcription unavailable: %s", e)
        return None

    out_dir = str(Path(output_srt_path).parent)
    stem = Path(video_path).stem
    wav_path = str(Path(out_dir) / (stem + ".apex.wav"))

    # Step 1: Extract audio
    if not extract_audio(video_path, wav_path):
        return None

    # Step 2: Transcribe with Apex
    result = _run_apex_transcription(whisper_python, wav_path, out_dir, stem)

    if "error" in result:
        logger.error("Apex transcription error: %s", result["error"])
        # Clean up WAV on failure
        Path(wav_path).unlink(missing_ok=True)
        return None

    # Step 3: Copy phrase-level SRT to expected output path
    phrase_srt = result.get("phrase_srt_path")
    if phrase_srt and Path(phrase_srt).exists():
        try:
            Path(output_srt_path).write_text(
                Path(phrase_srt).read_text(encoding="utf-8"), encoding="utf-8"
            )
            _log(f"SRT written to: {output_srt_path}")
            # Clean up WAV
            Path(wav_path).unlink(missing_ok=True)
            return output_srt_path
        except OSError as e:
            logger.error("Failed to write output SRT: %s", e)
            return None

    logger.error("Phrase SRT not found at expected path: %s", phrase_srt)
    return None
