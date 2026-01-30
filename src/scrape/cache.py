import json
from pathlib import Path


def cache_path(cache_dir: Path, provider_id: str) -> Path:
    return cache_dir / f"{provider_id}.json"


def load_cache(cache_dir: Path, provider_id: str):
    path = cache_path(cache_dir, provider_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_cache(cache_dir: Path, provider_id: str, payload: dict) -> None:
    path = cache_path(cache_dir, provider_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
