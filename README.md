# Island Dashboard

Lightweight dashboard generator to provide situational awerness information about Kauai.

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
- `site/index.html`

## Offline mode

If the network is unavailable, you can render from cached data:
- `python3 -m src.generate --island kauai --offline`

## Secrets

Put keys in a **`.env`** file at the repo root (see `.env.example`). When you run `python3 -m src.generate ...`, that file is loaded automatically via `python-dotenv` (`USGS_API_KEY`, `HCDP_API_KEY`, `WINLINK_API_KEY`, etc.). Variables you already exported in the shell still override `.env`.

- GitHub Actions: add repository secrets (e.g. `USGS_API_KEY`, `HCDP_API_KEY`, `WINLINK_API_KEY`) and map them in `.github/workflows/generate.yml`.

**Cron / other scripts** that call `python3` directly should either `cd` to the repo root (so the same `.env` path applies if you add `load_dotenv` there) or `export`/`source` the keys before running. The generate entrypoint loads only when using `src.generate`.

## Notes

- Scrapers prioritize resilience. If a source fails, the last known cache is used when available. Stale sections are flagged on the dashboard with a **Stale** badge, show the cached data's last-retrieved time, and display any error note.
- Source URLs are centralized in `src/config.py`.
