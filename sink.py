"""Sink — единственный выход результатов анализатора (спека standalone-analyzer v1.2).

Схема записи (D-A1): {id, ts, type, address, token, text, manual?, baseline?, digest_meta?}
type: verdict | reject | alert | digest. Все fsync/tmp+rename — через to_thread (D-A2).
Ротация analyses.jsonl: >5MB или >20К строк (D-A3).
"""
import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

RAB9_DIR = Path(__file__).resolve().parent
OUT_DIR = RAB9_DIR / "data" / "analyses_out"
JSONL = OUT_DIR / "analyses.jsonl"

ROTATE_BYTES = 5 * 1024 * 1024
ROTATE_LINES = 20000
MD_MAX_FILES = 500


def _write_sync(path: Path, data: str, append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if append:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    else:
        tmp = str(path) + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)


def _rotate_check_sync() -> None:
    if not JSONL.exists():
        return
    size = JSONL.stat().st_size
    with open(JSONL) as f:
        lines = sum(1 for _ in f)
    if size > ROTATE_BYTES or lines > ROTATE_LINES:
        rotated = JSONL.with_name(f"analyses.{time.strftime('%Y%m%dT%H%M%S')}.jsonl")
        os.replace(JSONL, rotated)
        asyncio.get_event_loop().call_soon(
            lambda: logging.getLogger("sink").warning(
                "analyses.jsonl rotated (%d bytes, %d lines)", size, lines
            )
        )


def _md_rotate_check_sync() -> None:
    mds = sorted(OUT_DIR.glob("*.md"))
    if len(mds) > MD_MAX_FILES:
        for old in mds[: len(mds) - MD_MAX_FILES]:
            old.unlink(missing_ok=True)


class Sink:
    def __init__(self, out_dir: Path = OUT_DIR):
        self.out_dir = Path(out_dir)
        self.jsonl = self.out_dir / "analyses.jsonl"

    async def write(
        self,
        type: str,
        address: str,
        token: str,
        text: str,
        manual: bool = False,
        baseline: dict | None = None,
        digest_meta: dict | None = None,
    ) -> str:
        """Запись результата. Возвращает id записи."""
        record = {
            "id": str(uuid.uuid4()),
            "ts": time.time(),
            "type": type,
            "address": address,
            "token": token,
            "text": text,
        }
        if manual:
            record["manual"] = True
        if baseline:
            record["baseline"] = baseline  # {price_usd, liquidity_usd}
        if digest_meta:
            record["digest_meta"] = digest_meta
        line = json.dumps(record, ensure_ascii=False)
        await asyncio.to_thread(_write_sync, self.jsonl, line + "\n", True)
        if type == "verdict":
            fname = f"{time.strftime('%Y%m%dT%H%M%S')}_{type}_{address[:8]}.md"
            await asyncio.to_thread(
                _write_sync, self.out_dir / fname, text + "\n", False
            )
            await asyncio.to_thread(_md_rotate_check_sync)
        await asyncio.to_thread(_rotate_check_sync)
        return record["id"]

    def read_new(self, last_id: str | None = None) -> list[dict]:
        """Записи после last_id (для delivery-reader). None → все."""
        if not self.jsonl.exists():
            return []
        out, seen = [], False
        with open(self.jsonl) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if last_id is None:
                    out.append(rec)
                elif seen or rec.get("id") == last_id:
                    if rec.get("id") == last_id:
                        seen = True
                    else:
                        out.append(rec)
        return out

