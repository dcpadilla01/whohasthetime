"""Summarize one transcript with Claude into a fixed JSON structure."""
import json
import os
import re

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
MAX_CHARS = 600_000  # ~150k tokens; a 3-hour episode is well under this

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


def summarize(ep, transcript: str) -> dict:
    client = anthropic.Anthropic()
    user = f"""Podcast: {ep.podcast}
Episode: {ep.title}
Published: {ep.published.date() if ep.published else "unknown"}
Show notes: {re.sub(r"<[^>]+>", " ", ep.description)[:1500]}

Reader's interests for this show: {ep.show.interests or "not specified — score on general intellectual value"}

TRANSCRIPT:
{transcript[:MAX_CHARS]}"""

    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text")
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"tldr": raw[:800], "key_ideas": [], "guests": "", "notable_lines": [],
                "worth_listening": 3, "why_score": "summary returned in free text", "skip_to": ""}
