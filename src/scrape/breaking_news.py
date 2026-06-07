import re
from pathlib import Path

import markdown

from src.scrape.base import now_iso

_REPO_ROOT = Path(__file__).resolve().parents[2]
BREAKING_NEWS_PATH = _REPO_ROOT / "content" / "breaking_news.md"


def _strip_comments_and_whitespace(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return text.strip()


def scrape() -> dict:
    base = {
        "id": "breaking_news",
        "label": "Breaking News",
        "retrieved_at": now_iso(),
        "source_urls": [str(BREAKING_NEWS_PATH.relative_to(_REPO_ROOT))],
        "error": None,
        "stale": False,
    }

    if not BREAKING_NEWS_PATH.exists():
        return {**base, "skip": True, "html": ""}

    raw = BREAKING_NEWS_PATH.read_text(encoding="utf-8")
    content = _strip_comments_and_whitespace(raw)
    if not content:
        return {**base, "skip": True, "html": ""}

    body_html = markdown.markdown(
        content,
        extensions=["extra", "nl2br", "sane_lists"],
    )
    return {
        **base,
        "banner": True,
        "skip": False,
        "html": body_html,
    }
