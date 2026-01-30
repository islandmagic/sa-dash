import argparse
from pathlib import Path

from src.config import ISLANDS
from src.render.html import render_html
from src.render.text import html_to_text
from src.scrape.base import now_iso
from src.scrape.cache import load_cache, save_cache
from src.scrape.registry import get_scraper


def scrape_with_cache(scraper_name: str, cache_dir: Path, offline: bool) -> dict:
    cached = load_cache(cache_dir, scraper_name)
    if offline:
        if cached:
            cached["error"] = cached.get("error") or "Offline mode: using cached data."
            cached["stale"] = True
            return cached
        return {
            "id": scraper_name,
            "label": scraper_name,
            "retrieved_at": None,
            "source_urls": [],
            "html": "<p>Offline mode: no cached data available.</p>",
            "text": "- Offline mode: no cached data available.",
            "error": "Offline mode: no cached data available.",
            "stale": True,
        }

    try:
        scraper = get_scraper(scraper_name)
        data = scraper()
        save_cache(cache_dir, scraper_name, data)
        return data
    except Exception as exc:  # noqa: BLE001 - keep generator resilient
        if cached:
            cached["error"] = f"Fetch failed: {exc}. Using cached data."
            cached["stale"] = True
            return cached
        return {
            "id": scraper_name,
            "label": scraper_name,
            "retrieved_at": None,
            "source_urls": [],
            "html": f"<p>Fetch failed: {exc}.</p>",
            "text": f"- Fetch failed: {exc}.",
            "error": f"Fetch failed: {exc}.",
            "stale": True,
        }


def generate_island(
    island_key: str,
    output_dir: Path,
    cache_dir: Path,
    offline: bool,
) -> None:
    if island_key not in ISLANDS:
        raise SystemExit(f"Unknown island: {island_key}")
    island = ISLANDS[island_key]
    scrapers = island.get("scrapers", [])
    results = [scrape_with_cache(name, cache_dir, offline) for name in scrapers]
    generated_at = now_iso()

    output_dir.mkdir(parents=True, exist_ok=True)
    html = render_html(island["name"], results, generated_at)
    text = html_to_text(html)
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    (output_dir / "index.txt").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate emergency dashboard pages.")
    parser.add_argument("--island", default="kauai", help="Island key to generate")
    parser.add_argument(
        "--scraper",
        help="Run a single scraper by name (overrides island config)",
    )
    parser.add_argument("--offline", action="store_true", help="Render from cache only")
    parser.add_argument(
        "--output-dir", default="site", help="Output directory for generated pages"
    )
    parser.add_argument(
        "--cache-dir", default="data/cache", help="Cache directory for provider data"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    cache_dir = Path(args.cache_dir)
    if args.scraper:
        result = scrape_with_cache(args.scraper, cache_dir, args.offline)
        generated_at = now_iso()
        html = render_html(args.scraper.upper(), [result], generated_at)
        text = html_to_text(html)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{args.scraper}.html").write_text(html, encoding="utf-8")
        (output_dir / f"{args.scraper}.txt").write_text(text, encoding="utf-8")
    else:
        generate_island(args.island, output_dir, cache_dir, args.offline)


if __name__ == "__main__":
    main()
