"""Poll RSS feeds and return episodes not yet in the state DB."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import mktime
from typing import Optional

import feedparser
import requests
import yaml

# We fetch feeds ourselves instead of letting feedparser do it: some hosts (Substack behind Cloudflare)
# hand a challenge page to obvious bot user agents coming from datacenter IPs such as GitHub Actions,
# and feedparser then reports a confusing XML error with no HTTP context.
FEED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/128.0 Safari/537.36 whohasthetime/1.0 (+https://github.com/dcpadilla01/whohasthetime)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
}


@dataclass
class Show:
    name: str
    feed: str
    interests: str = ""
    youtube_channel: Optional[str] = None
    max_minutes: Optional[int] = None


@dataclass
class Episode:
    podcast: str
    guid: str
    title: str
    link: str
    published: Optional[datetime]
    audio_url: Optional[str]
    duration_min: Optional[float]
    description: str
    transcript_urls: list = field(default_factory=list)  # [(url, mime_type)]
    chapters_url: Optional[str] = None
    show: Show = None


def load_shows(path="podcasts.yaml") -> list[Show]:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return [Show(**p) for p in cfg["podcasts"]]


def _parse_duration(raw) -> Optional[float]:
    if not raw:
        return None
    raw = str(raw).strip()
    if raw.isdigit():
        return int(raw) / 60
    parts = [int(p) for p in raw.split(":") if p.isdigit()]
    if len(parts) == 3:
        return parts[0] * 60 + parts[1] + parts[2] / 60
    if len(parts) == 2:
        return parts[0] + parts[1] / 60
    return None


def _entry_to_episode(show: Show, e) -> Episode:
    published = None
    if getattr(e, "published_parsed", None):
        published = datetime.fromtimestamp(mktime(e.published_parsed), tz=timezone.utc)

    audio = next((l.get("href") for l in e.get("enclosures", []) if "audio" in l.get("type", "")), None)
    if not audio and e.get("enclosures"):
        audio = e.enclosures[0].get("href")

    # Podcasting 2.0 <podcast:transcript url="" type=""/> — feedparser exposes it as podcast_transcript
    transcripts = []
    raw_t = e.get("podcast_transcript")
    if raw_t:
        for t in raw_t if isinstance(raw_t, list) else [raw_t]:
            url = t.get("url") if isinstance(t, dict) else None
            if url:
                transcripts.append((url, (t.get("type") or "").lower()))

    chapters = e.get("podcast_chapters", {}) or {}

    return Episode(
        podcast=show.name,
        guid=e.get("id") or e.get("link") or f"{show.name}:{e.get('title')}",
        title=e.get("title", "(untitled)"),
        link=e.get("link", ""),
        published=published,
        audio_url=audio,
        duration_min=_parse_duration(e.get("itunes_duration")),
        description=e.get("summary", "") or "",
        transcript_urls=transcripts,
        chapters_url=chapters.get("url") if isinstance(chapters, dict) else None,
        show=show,
    )


def _parse_feed(show: Show):
    """Download the feed and hand the bytes to feedparser. Returns None (after logging enough
    to debug from the Actions log alone) when the response isn't a usable feed."""
    try:
        r = requests.get(show.feed, headers=FEED_HEADERS, timeout=60)
        r.raise_for_status()
    except Exception as ex:
        print(f"[feeds] WARN fetch failed for {show.name}: {ex}")
        return None
    parsed = feedparser.parse(r.content)
    if parsed.bozo and not parsed.entries:
        snippet = r.content[:200].decode("utf-8", "replace").replace("\n", " ")
        print(f"[feeds] WARN could not parse {show.name}: {parsed.bozo_exception} "
              f"(HTTP {r.status_code}, {r.headers.get('content-type', '?')}, {len(r.content)} bytes) "
              f"body starts: {snippet!r}")
        return None
    return parsed


def fetch_new(shows: list[Show], con, is_seen, since_hours: int = 48) -> list[Episode]:
    """Episodes published within `since_hours` that aren't marked seen."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    new = []
    for show in shows:
        parsed = _parse_feed(show)
        if parsed is None:
            continue
        for e in parsed.entries:
            ep = _entry_to_episode(show, e)
            if is_seen(con, ep.guid):
                continue
            if ep.published and ep.published < cutoff:
                continue  # old and never seen (e.g. newly added show) — seeding handles these
            new.append(ep)
    return new


def all_episodes(shows: list[Show]) -> list[Episode]:
    """Used by --seed to mark the current back-catalogue as seen."""
    out = []
    for show in shows:
        parsed = _parse_feed(show)
        if parsed is None:
            continue
        for e in parsed.entries:
            out.append(_entry_to_episode(show, e))
    return out
