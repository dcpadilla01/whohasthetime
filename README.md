# whohasthetime

Daily email digest of new episodes from the podcasts you follow. Runs on GitHub Actions; no server. MIT licensed.

## How it works
1. `feeds.py` polls every feed in `podcasts.yaml` and diffs against `state/seen.sqlite`.
2. `transcripts.py` gets a transcript, cheapest source first:
   feed-native `<podcast:transcript>` → YouTube captions (if `youtube_channel` set) → Whisper on the downloaded audio (Groq by default, any OpenAI-compatible endpoint).
3. `summarize.py` asks an LLM (any model on OpenRouter) for a fixed-structure summary, scored against your `interests`.
4. `digest.py` renders one HTML email and sends it via Gmail SMTP. Nothing new → no email.
5. The workflow commits `state/seen.sqlite` back so episodes are never processed twice.

## Setup
1. Click "Use this template" (or create the repo), edit `podcasts.yaml`.
2. In Google Account → Security → 2-Step Verification → App passwords, create one for "Mail".
3. Add repository secrets (Settings → Secrets and variables → Actions):
   - `OPENROUTER_API_KEY` — for summarization (https://openrouter.ai/keys)
   - `TRANSCRIBE_API_KEY` — for audio transcription when a feed has no transcript. Groq by default (https://console.groq.com/keys, ~$0.04/hour of audio with `whisper-large-v3-turbo`). Enable billing on Groq or the free-tier rate limits will bite on long episodes.
   - `GMAIL_USER` — the sending Gmail address
   - `GMAIL_APP_PASSWORD` — the 16-char app password
   - `DIGEST_TO` — where to send (can equal GMAIL_USER)
4. Actions → "Podcast digest" → Run workflow once to seed the state.
   The first run marks all existing episodes as seen without summarizing them (`--seed`),
   so you only get episodes published from now on.

## Local run
```
pip install -r requirements.txt   # plus ffmpeg on PATH (brew install ffmpeg) for the audio fallback
export OPENROUTER_API_KEY=... TRANSCRIBE_API_KEY=... GMAIL_USER=... GMAIL_APP_PASSWORD=... DIGEST_TO=...
python main.py --dry-run     # prints the digest instead of emailing
```

## Knobs
- `SUMMARY_MODEL` env var: any OpenRouter model id (default `anthropic/claude-sonnet-5`).
  In Actions, set it as a repository *variable*, not a secret.
- `OPENROUTER_BASE_URL` to point at a different OpenAI-compatible server (OpenAI, Ollama, …)
- `SUMMARY_MAX_CHARS` to truncate transcripts for small-context models (default 600000 ≈ 150k tokens)
- `TRANSCRIBE_BASE_URL` + `TRANSCRIBE_MODEL` to change the transcription provider. Defaults are Groq
  (`https://api.groq.com/openai/v1`, `whisper-large-v3-turbo`). Groq's `whisper-large-v3` is more accurate
  at ~3x the price. For OpenAI use `https://api.openai.com/v1` and `whisper-1` or
  `gpt-4o-mini-transcribe`. Set as repository variables in Actions.
- `--since-hours N` to look back further than the default 48h on a manual run
- `max_minutes` per show to cap transcription spend
