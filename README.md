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

USGS uses an API key. Set it as an environment variable locally or in GitHub Actions:
- Local: create `.env` (see `.env.example`) with `USGS_API_KEY=...`
- GitHub Actions: add a repository secret named `USGS_API_KEY`

## Notes

- Scrapers prioritize resilience. If a source fails, the last known cache is used and the output will show when it was last retrieved.
- Source URLs are centralized in `src/config.py`.
