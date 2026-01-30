from bs4 import BeautifulSoup

from src.scrape.base import clean_text


def _append_list(lines: list[str], ul) -> None:
    for li in ul.find_all("li", recursive=False):
        text = clean_text(li.get_text())
        if text:
            lines.append(f"- {text}")


def _append_table(lines: list[str], table) -> None:
    header = []
    thead = table.find("thead")
    if thead:
        header = [clean_text(th.get_text()) for th in thead.find_all("th")]
    if header:
        lines.append(" | ".join(header))

    tbody = table.find("tbody")
    rows = tbody.find_all("tr") if tbody else table.find_all("tr")
    for row in rows:
        cells = [clean_text(td.get_text()) for td in row.find_all(["td", "th"])]
        if cells:
            lines.append(" | ".join(cells))


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup

    lines: list[str] = []

    header = body.find("header")
    if header:
        title = header.find(["h1", "h2"])
        if title:
            lines.append(clean_text(title.get_text()))
        meta = header.find("p", class_="meta")
        if meta:
            lines.append(clean_text(meta.get_text()))
        lines.append("")

    for section in body.find_all("section"):
        for child in section.find_all(recursive=False):
            if child.name in {"h2", "h3"}:
                text = clean_text(child.get_text())
                if text:
                    lines.append(text)
            elif child.name == "p":
                text = clean_text(child.get_text())
                if text:
                    lines.append(text)
            elif child.name == "ul":
                _append_list(lines, child)
            elif child.name == "table":
                _append_table(lines, child)
        lines.append("")

    return "\n".join(lines).strip() + "\n"
