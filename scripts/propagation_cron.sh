#!/bin/sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(pwd)}"
VENV_PATH="${VENV_PATH:-$REPO_DIR/.venv}"

cd "$REPO_DIR"

if [ -f "$VENV_PATH/bin/activate" ]; then
  . "$VENV_PATH/bin/activate"
fi

python3 -m src.propagation.generate

if [ -f "data/propagation.json" ]; then
  git add "data/propagation.json"
fi
if [ -f "data/propagation_state.json" ]; then
  git add "data/propagation_state.json"
fi

if git diff --cached --quiet; then
  echo "No propagation changes to commit."
  exit 0
fi

git commit -m "Update propagation data"
git push origin master
