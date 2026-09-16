# podcast-digest

Daily email digest of new episodes from the podcasts you follow. Runs on GitHub Actions; no server.

## How it works
1. `feeds.py` polls every feed in `podcasts.yaml` and diffs against `state/seen.sqlite`.
2. `transcripts.py` gets a transcript, cheapest source first:
   feed-native `<podcast:transcript>` → YouTube captions (if `youtube_channel` set) → Whisper API on the downloaded audio.
3. `summarize.py` asks Claude for a fixed-structure summary, scored against your `interests`.
4. `digest.py` renders one HTML email and sends it via Gmail SMTP. Nothing new → no email.
5. The workflow commits `state/seen.sqlite` back so episodes are never processed twice.

## Setup
1. Fork/create the repo, edit `podcasts.yaml`.
2. In Google Account → Security → 2-Step Verification → App passwords, create one for "Mail".
3. Add repository secrets (Settings → Secrets and variables → Actions):
   - `ANTHROPIC_API_KEY`
   - `OPENAI_API_KEY` (only needed for Whisper fallback)
   - `GMAIL_USER` — the sending Gmail address
   - `GMAIL_APP_PASSWORD` — the 16-char app password
   - `DIGEST_TO` — where to send (can equal GMAIL_USER)
4. Actions → "Podcast digest" → Run workflow once to seed the state.
   The first run marks all existing episodes as seen without summarizing them (`--seed`),
   so you only get episodes published from now on.

## Local run
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=... GMAIL_USER=... GMAIL_APP_PASSWORD=... DIGEST_TO=...
python main.py --dry-run     # prints the digest instead of emailing
```

## Knobs
- `CLAUDE_MODEL` env var (default `claude-sonnet-5`)
- `--since-hours N` to look back further than the default 48h on a manual run
- `max_minutes` per show to cap Whisper spend
# whohasthetime
