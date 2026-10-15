import argparse
import datetime as dt
import os
from pathlib import Path

from dotenv import load_dotenv

from src.config import ISLANDS
from src.event import evaluate, load_state, save_state, should_send_digest
from src.notify.winlink import send_digest
from src.render.html import render_html
from src.render.text import render_digest
from src.scrape.base import now_iso
from src.scrape.cache import load_cache, save_cache
from src.scrape.registry import get_scraper

_REPO_ROOT = Path(__file__).resolve().parents[1]
HST = dt.timezone(dt.timedelta(hours=-10))

# Scrapers backed by a committed cache file; live fetch often fails in CI.
COMMITTED_CACHE_SCRAPERS = frozenset({"marinetraffic_kauai", "county_alerts"})


def _uses_committed_cache(scraper_name: str) -> bool:
    return scraper_name in COMMITTED_CACHE_SCRAPERS


def scrape_with_cache(scraper_name: str, cache_dir: Path, offline: bool) -> dict:
    cached = load_cache(cache_dir, scraper_name)
    if offline:
        if cached:
            if not _uses_committed_cache(scraper_name):
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
        # county_alerts persists its own committed cache inside scrape()
        if scraper_name != "county_alerts":
            save_cache(cache_dir, scraper_name, data)
        return data
    except Exception as exc:  # noqa: BLE001 - keep generator resilient
        if cached:
            if _uses_committed_cache(scraper_name):
                cached["stale"] = False
                cached["error"] = None
            else:
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
    send_digest_now: bool = False,
) -> None:
    if island_key not in ISLANDS:
        raise SystemExit(f"Unknown island: {island_key}")
    island = ISLANDS[island_key]
    scrapers = island.get("scrapers", [])
    results = [scrape_with_cache(name, cache_dir, offline) for name in scrapers]
    generated_at = now_iso()

    state_path = _REPO_ROOT / "data" / "state" / "event.json"
    prev_state = load_state(state_path)
    event_state = evaluate(results, prev_state)
    # Preserve last_sent_at from prev unless we send below
    event_state["last_sent_at"] = prev_state.get("last_sent_at")

    output_dir.mkdir(parents=True, exist_ok=True)
    html = render_html(island["name"], results, generated_at, event=event_state)
    (output_dir / "index.html").write_text(html, encoding="utf-8")

    digest = render_digest(island["name"], results, generated_at, event=event_state)
    (output_dir / "digest.txt").write_text(digest, encoding="utf-8")

    save_state(state_path, event_state)

    winlink_to = (os.environ.get("WINLINK_TO") or "").strip()
    do_send = send_digest_now or should_send_digest(event_state)
    if do_send and winlink_to:
        now_hst = dt.datetime.now(tz=HST).replace(microsecond=0)
        subject = f"Kauai digest {now_hst.strftime('%Y-%m-%d %H:%M HST')}"
        try:
            send_digest(digest, winlink_to, subject=subject)
            event_state["last_sent_at"] = now_hst.isoformat()
            save_state(state_path, event_state)
        except Exception as exc:  # noqa: BLE001
            print(f"Winlink digest send failed: {exc}")
    elif send_digest_now and not winlink_to:
        print("WINLINK_TO not set; digest not sent.")


def main() -> None:
    load_dotenv(_REPO_ROOT / ".env")
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
    parser.add_argument(
        "--send-digest-now",
        action="store_true",
        help="Force-send the Winlink digest after generation",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    cache_dir = Path(args.cache_dir)
    if args.scraper:
        result = scrape_with_cache(args.scraper, cache_dir, args.offline)
        generated_at = now_iso()
        html = render_html(args.scraper.upper(), [result], generated_at)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{args.scraper}.html").write_text(html, encoding="utf-8")
        digest = render_digest(args.scraper.upper(), [result], generated_at)
        (output_dir / f"{args.scraper}.digest.txt").write_text(digest, encoding="utf-8")
    else:
        generate_island(
            args.island,
            output_dir,
            cache_dir,
            args.offline,
            send_digest_now=args.send_digest_now,
        )


if __name__ == "__main__":
    main()
