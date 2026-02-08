#!/bin/sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(pwd)}"
VENV_PATH="${VENV_PATH:-$REPO_DIR/.venv}"

cd "$REPO_DIR"

if [ -f "$VENV_PATH/bin/activate" ]; then
  . "$VENV_PATH/bin/activate"
fi

python3 -m src.generate --scraper marinetraffic_kauai

if [ -f "data/cache/marinetraffic_kauai.json" ]; then
  git add "data/cache/marinetraffic_kauai.json"
fi

if git diff --cached --quiet; then
  echo "No MarineTraffic changes to commit."
  exit 0
fi

git commit -m "Update MarineTraffic cache"
git push origin master
