import datetime as dt
import re
from pathlib import Path

HST = dt.timezone(dt.timedelta(hours=-10))


def _format_ts(ts: str | None) -> str:
    if not ts:
        return "unknown"
    try:
        parsed = dt.datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=HST)
        return parsed.astimezone(HST).strftime("%Y-%m-%d %H:%M HST")
    except ValueError:
        return ts.replace("T", " ")


def _load_cron_schedule() -> tuple[int, tuple[int, ...]] | None:
    workflow_path = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "generate.yml"
    )
    try:
        contents = workflow_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^\s*-\s*cron:\s*"([^"]+)"', contents, flags=re.MULTILINE)
    if not match:
        return None
    cron = match.group(1).strip()
    parts = cron.split()
    if len(parts) < 2:
        return None
    minute_str, hour_str = parts[0], parts[1]
    if not minute_str.isdigit():
        return None
    minute = int(minute_str)
    hours: list[int] = []
    for token in hour_str.split(","):
        token = token.strip()
        if not token:
            continue
        if token == "*":
            hours.extend(range(24))
            continue
        if "-" in token:
            start_str, end_str = token.split("-", 1)
            if not (start_str.isdigit() and end_str.isdigit()):
                return None
            start = int(start_str)
            end = int(end_str)
            if start > end:
                return None
            hours.extend(range(start, end + 1))
            continue
        if not token.isdigit():
            return None
        hours.append(int(token))
    if not hours:
        return None
    return minute, tuple(sorted(set(hours)))


def _next_update_ts(
    generated_at: str | None, schedule: tuple[int, tuple[int, ...]] | None
) -> str:
    if not generated_at:
        return "unknown"
    if not schedule:
        return "unknown"
    try:
        parsed = dt.datetime.fromisoformat(generated_at)
    except ValueError:
        return "unknown"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HST)
    now_utc = parsed.astimezone(dt.timezone.utc)
    minute, hours = schedule
    base_date = now_utc.date()
    for day_offset in (0, 1):
        day = base_date + dt.timedelta(days=day_offset)
        for hour in hours:
            candidate = dt.datetime(
                day.year,
                day.month,
                day.day,
                hour,
                minute,
                tzinfo=dt.timezone.utc,
            )
            if candidate > now_utc:
                return candidate.astimezone(HST).strftime("%H:%M HST")
    next_day = base_date + dt.timedelta(days=1)
    fallback = dt.datetime(
        next_day.year,
        next_day.month,
        next_day.day,
        hours[0],
        minute,
        tzinfo=dt.timezone.utc,
    )
    return fallback.astimezone(HST).strftime("%H:%M HST")


def _label_to_id(label: str) -> str:
    text = re.sub(r"<[^>]+>", "", label)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "section"


def render_html(island_name: str, providers: list[dict], generated_at: str) -> str:
    sections = []
    toc_items = []
    for provider in providers:
        error_note = ""
        if provider.get("error"):
            error_note = f"<p><strong>Note:</strong> {provider['error']}</p>"
        last_retrieved = _format_ts(provider.get("retrieved_at"))

        body = provider.get("html") or "<p>No updates available.</p>"
        section_id = _label_to_id(str(provider.get("label", "")))
        toc_items.append(
            f"<li><a href=\"#{section_id}\">{provider['label']}</a></li>"
        )

        sections.append(
            f"<section class=\"module\" id=\"{section_id}\">"
            f"<h2>{provider['label']}</h2>"
            f"<p class=\"meta\">{last_retrieved}</p>"
            f"{error_note}{body}"
            f"</section>"
        )

    generated = _format_ts(generated_at)
    schedule = _load_cron_schedule()
    next_update = _next_update_ts(generated_at, schedule)
    toc_html = "<nav class=\"toc\"><ul>" + "".join(toc_items) + "</ul></nav>"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{island_name} Dashboard</title>
  <style>
    :root {{
      color-scheme: light only;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 1rem;
      line-height: 1.4;
      color: #111;
      background: #fff;
    }}
    header {{
      border-bottom: 1px solid #ddd;
      margin-bottom: 1rem;
    }}
    h1 {{
      margin: 0;
      font-size: 1.5rem;
    }}
    h2 {{
      margin: 0;
      font-size: 1.1rem;
    }}
    h3 {{
      margin: 0;
      font-size: 1rem;
    }}
    .toc {{
      border: 1px solid #e2e2e2;
      padding: 0.75rem;
      margin: 0 0 1rem 0;
      border-radius: 6px;
      background: #fafafa;
    }}
    .toc h2 {{
      margin-top: 0;
    }}
    .toc ul {{
      margin: 0.5rem 0 0 0;
      padding-left: 1.1rem;
    }}
    .module {{
      border: 1px solid #e2e2e2;
      padding: 0.75rem;
      margin: 0 0 1rem 0;
      border-radius: 6px;
      background: #fff;
    }}
    .module hr {{
      border: 0;
      border-top: 1px solid #eee;
      margin: 0.75rem 0 0 0;
    }}
    .meta {{
      color: #555;
      font-size: 0.9rem;
      margin-top: 0;
    }}
    ul {{
      padding-left: 1.1rem;
      margin-top: 0.5rem;
    }}
    a {{
      color: #0b4d9b;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
    }}
    th,
    td {{
      padding: 0.4rem 0.5rem;
      vertical-align: top;
    }}
    th {{
      text-align: left;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{island_name} Dashboard</h1>
    <p class="meta">{generated} (Next update: {next_update})</p>
  </header>
  {toc_html}
  {"".join(sections)}
</body>
</html>
"""
    return html
