# Island Dashboard

Lightweight dashboard generator to provide situational awareness information about Kauai.

## Quick start

1. Create a virtualenv and install dependencies:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`

2. Generate Kauai pages:
   - `python3 -m src.generate --island kauai`

3. Run a single scraper (for testing):
   - `python3 -m src.generate --scraper kiuc`

Outputs are written to `site/`:
- `site/index.html` — full dashboard
- `site/digest.txt` — plain-text low-bandwidth digest (saildocs / Winlink)

## Offline mode

If the network is unavailable, you can render from cached data:
- `python3 -m src.generate --island kauai --offline`

## Secrets

Put keys in a **`.env`** file at the repo root (see `.env.example`). When you run `python3 -m src.generate ...`, that file is loaded automatically via `python-dotenv`. Variables you already exported in the shell still override `.env`.

- GitHub Actions: add repository secrets and map them in `.github/workflows/generate.yml`.

**Cron / other scripts** that call `python3` directly should either `cd` to the repo root or `export`/`source` the keys before running.

Low-bandwidth pull without Winlink push:

```
send http://kauai.islandmagic.co/digest.txt
```

to `query@saildocs.com`.

While event mode is active, Winlink digests are pushed on the first generate at or after each configured HST hour (default **06:00** and **18:00**), so a delayed hourly run still delivers the morning/afternoon slot.

## Notes

- Scrapers prioritize resilience. If a source fails, the last known cache is used when available. Stale sections are flagged on the dashboard with a **Stale** badge, show the cached data's last-retrieved time, and display any error note.
- Island scraper order is in `src/config.py`.
- `helpmefind.app` supply reports are crowd-sourced and unverified — always confirm before driving.
- County alert synthesis is rules-only (no LLM), designed from Hurricane Lowell alert templates.
