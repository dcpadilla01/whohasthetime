"""Summarize one transcript into a fixed JSON structure.

Talks to OpenRouter (or any OpenAI-compatible endpoint) so the model is a config choice,
not a code choice. Set SUMMARY_MODEL to any OpenRouter id, e.g.
  anthropic/claude-sonnet-5, openai/gpt-5.4-mini, google/gemini-3.5-flash
"""
import json
import os
import re

from openai import OpenAI

MODEL = os.environ.get("SUMMARY_MODEL", "anthropic/claude-sonnet-5")
BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
# ~150k tokens by default; a 3-hour episode is well under this. Lower it for small-context models.
MAX_CHARS = int(os.environ.get("SUMMARY_MAX_CHARS", 600_000))

SYSTEM = """You write concise summaries of podcast episodes for one busy reader.
Summaries must be in your own words. Never reproduce passages from the transcript;
"notable lines" are at most a short phrase each (under 12 words), and at most two of them.
Respond with JSON only, no markdown fences, matching exactly:
{
  "tldr": "2-3 sentences",
  "key_ideas": ["4-6 bullets, each one specific claim or takeaway"],
  "guests": "who appears and why they matter, or 'host only'",
  "notable_lines": ["0-2 short phrases"],
  "worth_listening": 1-5,
  "why_score": "one sentence tying the score to the reader's stated interests",
  "skip_to": "optional: rough part of the episode that matters most for this reader, if it can be inferred"
}
Scoring: 5 = drop everything and listen, 3 = summary is enough, 1 = irrelevant to this reader."""


def _client() -> OpenAI:
    return OpenAI(
        base_url=BASE_URL,
        api_key=os.environ["OPENROUTER_API_KEY"],
        # Optional OpenRouter attribution headers; harmless on other OpenAI-compatible servers.
        default_headers={"HTTP-Referer": "https://github.com/dcpadilla01/whohasthetime", "X-Title": "whohasthetime"},
    )


def summarize(ep, transcript: str) -> dict:
    user = f"""Podcast: {ep.podcast}
Episode: {ep.title}
Published: {ep.published.date() if ep.published else "unknown"}
Show notes: {re.sub(r"<[^>]+>", " ", ep.description)[:1500]}

Reader's interests for this show: {ep.show.interests or "not specified — score on general intellectual value"}

TRANSCRIPT:
{transcript[:MAX_CHARS]}"""

    resp = _client().chat.completions.create(
        model=MODEL,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    raw = resp.choices[0].message.content or ""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"tldr": raw[:800], "key_ideas": [], "guests": "", "notable_lines": [],
                "worth_listening": 3, "why_score": "summary returned in free text", "skip_to": ""}
