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

## Local propagation cron

If PSKReporter is blocked in CI, you can generate `data/propagation.json` locally
on a machine with access and push it to the repo.

1. Make the script executable:
   - `chmod +x scripts/propagation_cron.sh`
2. Add a cron entry (runs at minute 25 each hour):
   - `25 * * * * cd /Users/xxx/sa-dash && REPO_DIR=/Users/xxx/sa-dash VENV_PATH=/Users/xxx/sa-dash/.venv ./scripts/propagation_cron.sh >> /Users/xxx/sa-dash/propagation_cron.log 2>&1`

This requires git credentials configured on that machine so `git push` succeeds.

## Secrets

Put keys in a **`.env`** file at the repo root (see `.env.example`). When you run `python3 -m src.generate ...`, that file is loaded automatically via `python-dotenv` (`USGS_API_KEY`, `HCDP_API_KEY`, etc.). Variables you already exported in the shell still override `.env`.

- GitHub Actions: add repository secrets (e.g. `USGS_API_KEY`, `HCDP_API_KEY`) and map them in `.github/workflows/generate.yml`.

**Cron / other scripts** that call `python3` directly should either `cd` to the repo root (so the same `.env` path applies if you add `load_dotenv` there) or `export`/`source` the keys before running. The generate entrypoint loads only when using `src.generate`.

## Notes

- Scrapers prioritize resilience. If a source fails, the last known cache is used and the output will show when it was last retrieved.
- Source URLs are centralized in `src/config.py`.
