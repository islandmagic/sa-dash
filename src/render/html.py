import datetime as dt
import html as html_module
import re
from pathlib import Path

from bs4 import BeautifulSoup

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
        return ts


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


def _ensure_compact_tables(fragment: str) -> str:
    """Wrap every table in a horizontal-scroll container and mark compact styling."""
    if "<table" not in fragment.lower():
        return fragment
    soup = BeautifulSoup(f"<body>{fragment}</body>", "lxml")
    body = soup.body
    if not body:
        return fragment
    for table in list(body.find_all("table", recursive=True)):
        parent = table.parent
        if parent and parent.name == "div":
            pclass = parent.get("class") or []
            if isinstance(pclass, str):
                pclass = pclass.split()
            if "status-table-wrap" in pclass:
                tclass = table.get("class") or []
                if isinstance(tclass, str):
                    tclass = tclass.split()
                if "status-table-compact" not in tclass:
                    tclass.append("status-table-compact")
                    table["class"] = tclass
                continue
        tclass = table.get("class") or []
        if isinstance(tclass, str):
            tclass = tclass.split()
        if "status-table-compact" not in tclass:
            tclass.append("status-table-compact")
            table["class"] = tclass
        wrap = soup.new_tag("div", attrs={"class": "status-table-wrap"})
        table.wrap(wrap)
    return body.decode_contents()


def _provider_status_note(provider: dict) -> tuple[str, list[str]]:
    extra_classes: list[str] = []
    parts: list[str] = []

    if provider.get("stale"):
        extra_classes.append("module--stale")
        parts.append('<span class="status-badge status-badge--stale">Stale</span>')

    error = provider.get("error")
    if error:
        parts.append(
            f'<span class="status status--error">{html_module.escape(str(error))}</span>'
        )

    if not parts:
        return "", extra_classes

    return f'<p class="provider-status">{"".join(parts)}</p>', extra_classes


def render_html(island_name: str, providers: list[dict], generated_at: str) -> str:
    sections = []
    toc_items = []
    banner_html = ""
    for provider in providers:
        if provider.get("skip"):
            continue
        if provider.get("banner") or provider.get("id") == "breaking_news":
            body = provider.get("html") or ""
            banner_html = (
                '<div class="breaking-news-banner" role="alert">'
                '<div class="breaking-news-label">Breaking News</div>'
                f'<div class="breaking-news-body">{body}</div>'
                "</div>"
            )
            continue

        status_note, status_classes = _provider_status_note(provider)
        last_retrieved = _format_ts(provider.get("retrieved_at"))

        body = provider.get("html") or "<p>No updates available.</p>"
        body = _ensure_compact_tables(body)
        section_id = _label_to_id(str(provider.get("label", "")))
        toc_items.append(
            f"<li><a href=\"#{section_id}\">{provider['label']}</a></li>"
        )

        module_classes = ["module", *status_classes]
        if provider.get("layout") == "full" or provider.get("full_width"):
            module_classes.append("module--full")
        class_attr = " ".join(module_classes)
        sections.append(
            f"<section class=\"{class_attr}\" id=\"{section_id}\">"
            f"<h2>{provider['label']}</h2>"
            f"<p class=\"meta\">{last_retrieved}</p>"
            f"{status_note}{body}"
            f"</section>"
        )

    generated = _format_ts(generated_at)
    schedule = _load_cron_schedule()
    next_update = _next_update_ts(generated_at, schedule)
    toc_nav = "<nav class=\"toc\"><ul>" + "".join(toc_items) + "</ul></nav>"
    toc_section = (
        "<section class=\"module module--narrow\" id=\"toc\">"
        f"{toc_nav}"
        "</section>"
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{island_name} Dashboard</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #fff;
      --text: #111;
      --text-muted: #555;
      --border: #e2e2e2;
      --header-border: #ddd;
      --module-bg: #fff;
      --link: #0b4d9b;
      --code-bg: #f5f5f5;
      --footer-border: #eee;
      --status-text: #111;
      --stale-bg: #fffbe6;
      --stale-border: #e6b800;
      --stale-badge-bg: #fff4cc;
      --stale-badge-text: #7a5d00;
      --error-text: #8a1c1c;
      --breaking-bg: #fde2e2;
      --breaking-border: #c62828;
      --breaking-label: #b71c1c;
      --status-green: #e7f6ea;
      --status-yellow: #fff4cc;
      --status-red: #fde2e2;
      --table-row-border: rgba(0, 0, 0, 0.08);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #121212;
        --text: #e8e8e8;
        --text-muted: #aaa;
        --border: #333;
        --header-border: #333;
        --module-bg: #1a1a1a;
        --link: #6eb3ff;
        --code-bg: #2a2a2a;
        --footer-border: #333;
        --status-text: #e8e8e8;
        --stale-bg: #2a2610;
        --stale-border: #b89400;
        --stale-badge-bg: #3d3510;
        --stale-badge-text: #e6c84a;
        --error-text: #f4a4a4;
        --breaking-bg: #3d1a1a;
        --breaking-border: #c62828;
        --breaking-label: #ff8a80;
        --status-green: #1a3d24;
        --status-yellow: #3d3510;
        --status-red: #3d1a1a;
        --table-row-border: rgba(255, 255, 255, 0.08);
      }}
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 1rem;
      line-height: 1.4;
      color: var(--text);
      background: var(--bg);
    }}
    .breaking-news-banner {{
      background: var(--breaking-bg);
      border: 2px solid var(--breaking-border);
      border-radius: 6px;
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
    }}
    .breaking-news-label {{
      font-weight: 700;
      font-size: 1rem;
      color: var(--breaking-label);
      margin-bottom: 0.35rem;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .breaking-news-body {{
      font-size: 0.95rem;
    }}
    .breaking-news-body p {{
      margin: 0.35rem 0 0;
    }}
    .breaking-news-body p:first-child {{
      margin-top: 0;
    }}
    header {{
      border-bottom: 1px solid var(--header-border);
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
    .toc ul {{
      margin: 0;
      padding-left: 1.1rem;
    }}
    .modules {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 1rem;
      align-items: stretch;
    }}
    .module {{
      border: 1px solid var(--border);
      padding: 0.75rem;
      margin: 0;
      border-radius: 6px;
      background: var(--module-bg);
      display: flex;
      flex-direction: column;
      min-width: 0;
    }}
    .module--narrow {{
      grid-column: span 1;
    }}
    .module--full {{
      grid-column: 1 / -1;
    }}
    .module--stale {{
      border-color: var(--stale-border);
      background: var(--stale-bg);
    }}
    .provider-status {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.35rem 0.5rem;
      margin: 0.15rem 0 0.5rem;
    }}
    .status-badge {{
      display: inline-block;
      font-size: 0.65rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.1rem 0.35rem;
      border-radius: 3px;
      line-height: 1.3;
    }}
    .status-badge--stale {{
      background: var(--stale-badge-bg);
      color: var(--stale-badge-text);
      border: 1px solid var(--stale-border);
    }}
    .status--error {{
      color: var(--error-text);
      font-size: 0.75rem;
      margin: 0;
    }}
    .meta {{
      color: var(--text-muted);
      font-size: 0.7rem;
      margin-top: 0;
    }}
    .status {{
      color: var(--status-text);
      font-size: 0.8rem;
      margin-top: 0;
    }}

    .info {{
      color: var(--text-muted);
      font-size: 0.8rem;
      margin-top: 0;
    }}
    .info::before {{
      content: "ⓘ ";
    }}
    .info code {{
      background: var(--code-bg);
      padding: 0.2rem 0.4rem;
      border-radius: 4px;
    }}
    ul {{
      padding-left: 1.1rem;
      margin-top: 0.5rem;
    }}
    a {{
      color: var(--link);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    th,
    td {{
      padding: 0.1rem 0.5rem;
      vertical-align: top;
    }}
    th {{
      text-align: left;
    }}
    .status-green {{
      background: var(--status-green);
    }}
    .status-yellow {{
      background: var(--status-yellow);
    }}
    .status-red {{
      background: var(--status-red);
    }}
    .status-cell {{
      text-align: center;
    }}
    .module .status-table-wrap {{
      display: block;
      width: 100%;
      max-width: 100%;
      min-width: 0;
    }}
    .module table.status-table-compact {{
      width: 100%;
      max-width: 100%;
      font-size: 0.88rem;
      border-collapse: collapse;
      table-layout: auto;
    }}
    .module table.status-table-compact th,
    .module table.status-table-compact td {{
      white-space: normal;
      overflow-wrap: break-word;
      word-break: break-word;
      padding: 0.06rem 0.35rem;
      vertical-align: top;
    }}
    .module .info-module td.info-td-phone {{
      white-space: nowrap;
    }}
    .footer {{
      border-top: 1px solid var(--footer-border);
      color: var(--text-muted);
      font-size: 0.9rem;
      margin-top: 1rem;
    }}
    details {{
      margin: 0.5rem 0 0 0.5rem;
    }}
    .info-module .info-td-notes,
    .info-module .info-kicker {{
      color: var(--text-muted);
    }}
    .solid-waste-table tbody tr + tr td {{
      border-top-color: var(--table-row-border);
    }}
    @media (prefers-color-scheme: dark) {{
      .time-wheel .tw-hole {{
        fill: var(--bg);
      }}
      .time-wheel .tw-seg--day {{
        fill: #1a2a3a;
      }}
      .time-wheel .tw-label--inner,
      .time-wheel .tw-label--outer {{
        fill: var(--text);
      }}
      .time-wheel .tw-outer-label {{
        fill: var(--text-muted);
      }}
    }}
    @media (max-width: 720px) {{
      .modules {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{island_name} Dashboard</h1>
    <p class="meta">{generated} | <a href="https://github.com/islandmagic/sa-dash/issues">Report issue</a></p>
    <p class="info">
      Get this page via email by sending a message to <code>query@saildocs.com</code> with <code>send http://kauai.islandmagic.co</code> in the body.
    </p>
  </header>
  {banner_html}
  <div class="modules">{toc_section}{"".join(sections)}</div>
  <footer class="footer">
    <p>This page aggregates publicly available data from multiple sources. Information may be delayed, incomplete, or contain errors. Always refer to official sources for confirmation.</p>
  </footer>
</body>
</html>
"""
    return html
