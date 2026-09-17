# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A daily podcast digest: poll RSS feeds, fetch a transcript for each new episode, summarize it with an LLM via OpenRouter, email one HTML digest via Gmail SMTP. Runs on GitHub Actions (`.github/workflows/digest.yml`, cron 13:00 UTC); no server. Python 3.12, no tests, no linter.

## Commands

```
pip install -r requirements.txt
python main.py --dry-run                 # print digest HTML to stdout, mark nothing as seen
python main.py --dry-run --since-hours 168
python main.py --seed                    # mark entire current back-catalogue as seen, send nothing
python main.py                           # real run: summarize, email, mark seen
```

Required env: `OPENROUTER_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `DIGEST_TO`. Optional: `TRANSCRIBE_API_KEY` (audio transcription fallback; without it that step is silently skipped), `SUMMARY_MODEL` (any OpenRouter id, default `anthropic/claude-sonnet-5`), `OPENROUTER_BASE_URL` (any OpenAI-compatible server), `SUMMARY_MAX_CHARS` (transcript truncation, default 600000), `TRANSCRIBE_BASE_URL` / `TRANSCRIBE_MODEL` (default Groq `whisper-large-v3-turbo`; any OpenAI-compatible `/audio/transcriptions` endpoint). The transcription fallback also needs `ffmpeg` on PATH.

Two providers are involved on purpose: OpenRouter for text (it has no transcription endpoint) and a Whisper-style endpoint for audio. Both use the `openai` SDK with different `base_url`s.

`--dry-run` still hits the LLM API (and transcription if it falls through to it); it only skips email and state writes.

## Architecture

`main.py` is the only orchestrator. It does `sys.path.insert(0, "src")`, so modules in `src/` import each other as top-level names (`import state`, `from feeds import ...`), not `from src...`. Keep that convention.

Pipeline, one function per stage:

1. `feeds.load_shows()` reads `podcasts.yaml` into `Show` dataclasses. `feeds.fetch_new()` downloads each feed with `requests` and browser-like headers (Substack behind Cloudflare has served challenge pages to bot user agents from GitHub's IPs) and hands the bytes to feedparser; on a parse failure it logs HTTP status, content type, and the first bytes of the body. It returns `Episode`s that are not in the state DB **and** were published within `--since-hours`. Unseen episodes older than the window are silently skipped; that is what `--seed` is for when adding a new show.
2. `transcripts.get_transcript(ep)` tries sources cheapest-first: feed-native `<podcast:transcript>` → YouTube captions (only if the show has `youtube_channel`; matched to the episode by Jaccard similarity on title tokens, threshold 0.5) → Whisper-style transcription of the RSS `<enclosure>` audio (only if `TRANSCRIBE_API_KEY` is set and the episode is under the show's `max_minutes`; audio is re-encoded to mono 32 kbps and cut into 20-minute chunks by ffmpeg so each upload stays a few MB). A source "succeeds" only if it yields >200 words; otherwise the next one is tried. Returns `(text, source_name)` or `(None, reason)`.
3. `summarize.summarize(ep, text)` sends one Chat Completions call through the `openai` SDK pointed at OpenRouter, with a fixed JSON schema in the system prompt, and returns the parsed dict. It deliberately does not use `response_format` JSON mode because not every OpenRouter model supports it; JSON is enforced by prompt plus fence stripping. On a parse failure it returns a fallback dict with the raw text in `tldr` and score 3, so downstream never sees an exception from bad model output.
4. `digest.render(items, failures)` builds inline-styled HTML; `digest.send()` ships it over `smtplib.SMTP_SSL`. No email is sent when there is nothing new.

### Coupling to know about

- **`Episode.show` back-reference.** Each `Episode` carries its `Show`, and downstream stages read per-show config through it (`ep.show.interests` in summarize, `ep.show.youtube_channel` / `ep.show.max_minutes` in transcripts). New per-show knobs go in `podcasts.yaml` → `Show` dataclass → read via `ep.show`.
- **Summary schema lives in three places.** The system prompt in `summarize.py`, the parse-failure fallback dict in the same file, and the `s.get(...)` reads in `digest.render`. Change all three together. `worth_listening` (1–5) is also used by `main.py` for sort order and by `digest.STARS` for display.
- **GUID derivation decides what counts as "seen".** `feeds._entry_to_episode` uses the feed entry's `id`, falling back to `link`, then `"{show name}:{title}"`. Changing this formula, or renaming a show in `podcasts.yaml`, changes GUIDs and will make already-processed episodes look new again (subject to the since-hours window).
- **State is the dedupe mechanism.** `state/seen.sqlite` is keyed by episode GUID and is not in the repo until the first Action run commits it; `state.connect()` creates the directory and table on demand, so a local run works from a fresh clone. Failures are also marked (`status = "failed: ..."`), so a failed episode is never retried automatically; delete its row to retry. The workflow's last step commits the sqlite file back to the repo, so the DB is effectively version-controlled and the GitHub Action needs `contents: write`.
- **Transcript source is persisted.** The name of the source that succeeded (`feed` / `youtube` / `whisper`) is stored in the DB and shown in the email card. Adding a source means adding a `(name, fn)` pair to the tuple in `get_transcript`.

## Workflow dispatch

Manual runs of the "Podcast digest" action take `mode` (`run` | `seed` | `dry-run`) and `since_hours`; the shell `case` in `digest.yml` maps them to the CLI flags above. `SUMMARY_MODEL` can be overridden with a repository variable, not a secret.
