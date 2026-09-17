"""Get a plain-text transcript for an episode, cheapest source first.

Returns (text, source) where source ∈ {"feed", "youtube", "whisper"} or (None, reason).
"""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import requests

UA = {"User-Agent": "whohasthetime/1.0 (+https://github.com/dcpadilla01/whohasthetime)"}

# Any OpenAI-compatible /audio/transcriptions endpoint. Default is Groq's hosted Whisper turbo,
# roughly 9x cheaper than OpenAI's whisper-1 (Groq's whisper-large-v3 is more accurate at ~3x cheaper).
# To use OpenAI instead:  TRANSCRIBE_BASE_URL=https://api.openai.com/v1  TRANSCRIBE_MODEL=whisper-1
TRANSCRIBE_BASE_URL = os.environ.get("TRANSCRIBE_BASE_URL", "https://api.groq.com/openai/v1")
TRANSCRIBE_MODEL = os.environ.get("TRANSCRIBE_MODEL", "whisper-large-v3-turbo")


# ---------- 1. Feed-native <podcast:transcript> ----------

def _strip_vtt_srt(text: str) -> str:
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s == "WEBVTT" or s.isdigit() or "-->" in s or s.startswith(("NOTE", "STYLE", "REGION")):
            continue
        s = re.sub(r"<[^>]+>", "", s)          # <v Speaker> tags, <c> styling
        s = re.sub(r"^\[?[A-Za-z .]+\]?:\s*", "", s) if s.count(":") == 1 and len(s.split(":")[0]) < 30 else s
        lines.append(s)
    # collapse repeated lines that VTT rolling captions produce
    out, prev = [], None
    for l in lines:
        if l != prev:
            out.append(l)
        prev = l
    return " ".join(out)


def _from_feed(ep) -> Optional[str]:
    # prefer plain text / html, then json, then subtitle formats
    order = ["text/plain", "text/html", "application/json", "application/x-subrip", "application/srt", "text/vtt"]
    for want in order:
        for url, mime in ep.transcript_urls:
            if mime and want not in mime:
                continue
            try:
                r = requests.get(url, headers=UA, timeout=30)
                r.raise_for_status()
            except Exception as ex:
                print(f"[transcripts] feed transcript fetch failed {url}: {ex}")
                continue
            body = r.text
            if "json" in (mime or "") or body.lstrip().startswith("{"):
                try:
                    data = json.loads(body)
                    segs = data.get("segments") or data.get("transcript") or []
                    return " ".join(s.get("body", "") for s in segs if isinstance(s, dict))
                except Exception:
                    pass
            if "html" in (mime or ""):
                return re.sub(r"<[^>]+>", " ", body)
            if "WEBVTT" in body[:20] or "-->" in body[:500]:
                return _strip_vtt_srt(body)
            return body
    return None


# ---------- 2. YouTube auto-captions ----------

def _title_tokens(t: str) -> set:
    return set(re.findall(r"[a-z0-9]{3,}", t.lower()))


def _from_youtube(ep) -> Optional[str]:
    if not ep.show.youtube_channel:
        return None
    try:
        import yt_dlp
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None

    opts = {"quiet": True, "extract_flat": True, "playlistend": 20, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(ep.show.youtube_channel.rstrip("/") + "/videos", download=False)
    except Exception as ex:
        print(f"[transcripts] youtube listing failed: {ex}")
        return None

    want = _title_tokens(ep.title)
    best, best_score = None, 0.0
    for v in info.get("entries") or []:
        have = _title_tokens(v.get("title", ""))
        if not want or not have:
            continue
        score = len(want & have) / len(want | have)  # Jaccard
        if score > best_score:
            best, best_score = v, score
    if not best or best_score < 0.5:
        return None

    try:
        segs = YouTubeTranscriptApi().fetch(best["id"], languages=["en", "es"])
        return " ".join(s.text for s in segs)
    except Exception as ex:
        print(f"[transcripts] youtube captions unavailable for {best.get('title')}: {ex}")
        return None


# ---------- 3. Whisper-style API on downloaded audio ----------

def _from_whisper(ep) -> Optional[str]:
    api_key = os.environ.get("TRANSCRIBE_API_KEY")
    if not ep.audio_url or not api_key:
        return None
    cap = ep.show.max_minutes
    if cap and ep.duration_min and ep.duration_min > cap:
        print(f"[transcripts] skipping transcription: {ep.duration_min:.0f} min > max_minutes={cap}")
        return None

    from openai import OpenAI
    client = OpenAI(base_url=TRANSCRIBE_BASE_URL, api_key=api_key)
    print(f"[transcripts] transcribing with {TRANSCRIBE_MODEL} via {TRANSCRIBE_BASE_URL}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "episode.mp3"
        with requests.get(ep.audio_url, headers=UA, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(src, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)

        # Re-encode to mono 32 kbps and cut into 20-min chunks so each stays well under the 25 MB API limit.
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", str(src), "-ac", "1", "-b:a", "32k",
             "-f", "segment", "-segment_time", "1200", str(tmp / "chunk_%03d.mp3")],
            check=True,
        )
        parts = []
        for chunk in sorted(tmp.glob("chunk_*.mp3")):
            with open(chunk, "rb") as f:
                resp = client.audio.transcriptions.create(model=TRANSCRIBE_MODEL, file=f, response_format="text")
            parts.append(resp if isinstance(resp, str) else getattr(resp, "text", str(resp)))
        return "\n".join(parts)


# ---------- public ----------

def get_transcript(ep):
    for name, fn in (("feed", _from_feed), ("youtube", _from_youtube), ("whisper", _from_whisper)):
        try:
            text = fn(ep)
        except Exception as ex:
            print(f"[transcripts] {name} failed for '{ep.title}': {ex}")
            text = None
        if text and len(text.split()) > 200:
            return text, name
    return None, "no transcript source succeeded"
