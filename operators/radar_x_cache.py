"""Bounded TTL cache for per-token radar_x payloads (one X call per analysis path)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "radar_x_per_token.json"


def _path() -> Path:
    custom = os.environ.get("RADAR_X_CACHE_PATH")
    return Path(custom) if custom else _DEFAULT_PATH


def _load_doc(path: Path) -> dict:
    if not path.exists():
        return {"entries": {}}
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return {"entries": {}}
    if not isinstance(doc.get("entries"), dict):
        doc["entries"] = {}
    return doc


def _save_doc(path: Path, doc: dict, *, max_entries: int) -> None:
    entries = doc.get("entries") or {}
    if len(entries) > max_entries:
        ordered = sorted(
            entries.items(),
            key=lambda kv: float((kv[1] or {}).get("ts") or 0),
        )
        for key, _ in ordered[: len(entries) - max_entries]:
            entries.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"entries": entries}, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def put_cached(
    address: str,
    query: str,
    radar: dict,
    *,
    social: dict | None = None,
    ttl_seconds: float | None = None,
    max_entries: int | None = None,
) -> None:
    path = _path()
    doc = _load_doc(path)
    doc["entries"][address] = {
        "ts": time.time(),
        "query": query,
        "radar": radar,
        "social": social or {},
        "ttl_seconds": ttl_seconds,
    }
    cap = max_entries if max_entries is not None else int(os.environ.get("RADAR_X_CACHE_MAX", "200"))
    _save_doc(path, doc, max_entries=cap)


def get_cached(address: str, *, ttl_seconds: float | None = None) -> dict | None:
    path = _path()
    doc = _load_doc(path)
    entry = (doc.get("entries") or {}).get(address)
    if not entry:
        return None
    ttl = ttl_seconds
    if ttl is None:
        ttl = entry.get("ttl_seconds")
    if ttl is None:
        ttl = float(os.environ.get("RADAR_X_CACHE_TTL_H", "6")) * 3600
    if time.time() - float(entry.get("ts") or 0) > ttl:
        return None
    return entry


__all__ = ["get_cached", "put_cached"]