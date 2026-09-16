"""Poll feeds → get transcripts → summarize → email one digest.

  python main.py                 normal daily run
  python main.py --dry-run       print HTML to stdout, mark nothing as seen
  python main.py --seed          mark the whole current back-catalogue as seen, send nothing
  python main.py --since-hours 168
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import state  # noqa: E402
from digest import render, send  # noqa: E402
from feeds import all_episodes, fetch_new, load_shows  # noqa: E402
from summarize import summarize  # noqa: E402
from transcripts import get_transcript  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--since-hours", type=int, default=48)
    args = ap.parse_args()

    shows = load_shows()

    if args.seed:
        with state.connect() as con:
            n = 0
            for ep in all_episodes(shows):
                if not state.is_seen(con, ep.guid):
                    state.mark(con, ep, "seed", "skipped")
                    n += 1
        print(f"Seeded {n} episodes as seen.")
        return

    with state.connect() as con:
        new = fetch_new(shows, con, state.is_seen, since_hours=args.since_hours)
        print(f"{len(new)} new episode(s).")
        if not new:
            return

        items, failures = [], []
        for ep in new:
            print(f"→ {ep.podcast}: {ep.title}")
            text, source = get_transcript(ep)
            if not text:
                failures.append({"ep": ep, "reason": source})
                if not args.dry_run:
                    state.mark(con, ep, "none", f"failed: {source}")
                continue
            try:
                summary = summarize(ep, text)
                items.append({"ep": ep, "summary": summary, "source": source})
                if not args.dry_run:
                    state.mark(con, ep, source, "summarized")
            except Exception as ex:
                failures.append({"ep": ep, "reason": f"summarize error: {ex}"})
                if not args.dry_run:
                    state.mark(con, ep, source, f"failed: {ex}")

        items.sort(key=lambda it: -int(it["summary"].get("worth_listening", 3)))
        html_body = render(items, failures)

    if args.dry_run:
        print(html_body)
        return
    if items or failures:
        top = items[0]["ep"].title if items else "nothing summarized"
        send(html_body, f"Podcasts {date.today():%b %-d}: {len(items)} new · top: {top[:60]}")
        print("Digest sent.")


if __name__ == "__main__":
    main()
