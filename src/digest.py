"""Build one HTML email from the day's summaries and send it through Gmail SMTP."""
import html
import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

STARS = {5: "★★★★★", 4: "★★★★☆", 3: "★★★☆☆", 2: "★★☆☆☆", 1: "★☆☆☆☆"}


def _esc(s):
    return html.escape(str(s or ""))


def render(items: list[dict], failures: list[dict]) -> str:
    """items: [{"ep": Episode, "summary": dict, "source": str}] sorted by score desc."""
    today = date.today().strftime("%A, %B %-d")
    toc = "".join(
        f'<li><a href="#e{i}" style="color:#1a4d8f;text-decoration:none">'
        f'{STARS.get(int(it["summary"].get("worth_listening", 3)), "")} '
        f'{_esc(it["ep"].podcast)} — {_esc(it["ep"].title)}</a></li>'
        for i, it in enumerate(items)
    )

    cards = []
    for i, it in enumerate(items):
        ep, s = it["ep"], it["summary"]
        mins = f" · {ep.duration_min:.0f} min" if ep.duration_min else ""
        ideas = "".join(f"<li>{_esc(k)}</li>" for k in s.get("key_ideas", []))
        lines = "".join(f"<li><em>{_esc(q)}</em></li>" for q in s.get("notable_lines", []))
        skip = f'<p style="margin:6px 0"><b>Skip to:</b> {_esc(s["skip_to"])}</p>' if s.get("skip_to") else ""
        cards.append(f"""
<div id="e{i}" style="border:1px solid #e3e3e3;border-radius:8px;padding:16px;margin:18px 0">
  <div style="color:#666;font-size:12px;text-transform:uppercase;letter-spacing:.5px">{_esc(ep.podcast)}{mins} · transcript via {_esc(it["source"])}</div>
  <h2 style="margin:4px 0 8px;font-size:18px"><a href="{_esc(ep.link)}" style="color:#111;text-decoration:none">{_esc(ep.title)}</a></h2>
  <div style="font-size:15px;color:#b8860b">{STARS.get(int(s.get("worth_listening", 3)), "")}
     <span style="color:#555;font-size:13px">— {_esc(s.get("why_score"))}</span></div>
  <p style="margin:10px 0"><b>TL;DR</b> {_esc(s.get("tldr"))}</p>
  <ul style="margin:6px 0 6px 18px;padding:0">{ideas}</ul>
  <p style="margin:6px 0"><b>Guests:</b> {_esc(s.get("guests"))}</p>
  {'<p style="margin:6px 0"><b>Notable lines</b></p><ul style="margin:0 0 6px 18px">' + lines + '</ul>' if lines else ''}
  {skip}
  {'<p style="margin:6px 0;font-size:13px"><a href="' + _esc(ep.audio_url) + '">▶ audio</a></p>' if ep.audio_url else ''}
</div>""")

    fails = ""
    if failures:
        rows = "".join(f"<li>{_esc(f['ep'].podcast)} — {_esc(f['ep'].title)} <span style='color:#888'>({_esc(f['reason'])})</span></li>"
                       for f in failures)
        fails = f'<h3 style="color:#888;font-size:14px">New but couldn\'t summarize</h3><ul style="color:#888;font-size:13px">{rows}</ul>'

    return f"""<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:680px;margin:0 auto;padding:20px;color:#222;line-height:1.45">
<h1 style="font-size:22px;margin:0 0 4px">Podcast digest · {today}</h1>
<p style="color:#666;margin:0 0 14px">{len(items)} new episode{'s' if len(items) != 1 else ''}, sorted by how much they're worth your time.</p>
<ol style="padding-left:20px;margin:0 0 10px">{toc}</ol>
{''.join(cards)}
{fails}
</body></html>"""


def send(html_body: str, subject: str):
    user, pw, to = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"], os.environ["DIGEST_TO"]
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText("Your mail client doesn't render HTML; open in Gmail.", "plain"))
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())
