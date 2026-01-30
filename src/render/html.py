import re


def _format_ts(ts: str | None) -> str:
    if not ts:
        return "unknown"
    try:
        dt = __import__("datetime").datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M HST")
    except ValueError:
        return ts.replace("T", " ")


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
    <p class="meta">{generated}</p>
  </header>
  {toc_html}
  {"".join(sections)}
</body>
</html>
"""
    return html
