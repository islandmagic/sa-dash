#!/bin/sh
set -euo pipefail

cd "$(pwd)"

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
