#!/usr/bin/env python3
"""Standalone-анализатор RAB9 — ядро без Telegram (спека standalone-analyzer v1.2).

Машина состояний: NEW → T0_PENDING → [выжил] QUEUED → [rate cap] ANALYZED → SINK.
Дедуп-ключ — только на входе в ANALYZED (N1/N2 ре-чека abab7dc9).
"""
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from msf_http import _extract_baseline, send_msf_pairresolve, start_msf_http_server
from sink import Sink

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("rab9_analyzer")

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
T0_QUEUE = DATA / "t0_queue.jsonl"
ANALYSIS_QUEUE = DATA / "analysis_queue.jsonl"
OUTCOMES = DATA / "verdict_outcomes.jsonl"
RATE_LOG = DATA / "analysis_rate.jsonl"
DIGEST_CURSOR = BASE / "data" / "analyses_out" / "digest_cursor.json"


def _env(name, default):
    return os.environ.get(name, default)

T0_INTERVAL_MIN = int(_env("ANALYZER_T0_INTERVAL_MIN", "20"))
DIGEST_WINDOW_H = float(_env("ANALYZER_DIGEST_WINDOW_H", "4"))
DIGEST_THRESHOLD = int(_env("ANALYZER_DIGEST_THRESHOLD", "3"))
RATE_CAP_H = int(_env("ANALYZER_RATE_CAP_H", "15"))
KABAL_CAP_H = int(_env("ANALYZER_KABAL_CAP_H", "5"))
QUEUE_MAX = int(_env("ANALYZER_QUEUE_MAX", "500"))
OUTCOME_DEAD_LIQ = float(_env("ANALYZER_OUTCOME_DEAD_LIQ_USD", "5000"))
OUTCOME_AFTER_H = float(_env("ANALYZER_OUTCOME_AFTER_H", "24"))


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _load(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [l.strip() for l in path.read_text().splitlines() if l.strip()]


def _rewrite(path: Path, lines: list[str]) -> None:
    tmp = str(path) + ".tmp"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        for l in lines:
            f.write(l + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ── T0_PENDING: мягкий чек, БЕЗ записи дедуп-ключа (v1.2 N1) ──
async def t0_enroll(address: str):
    log.info("T0_PENDING enroll: %s (мягкий чек, без LLM)", address[:12])
    try:
        baseline = await asyncio.to_thread(_extract_baseline, address)
    except Exception:
        baseline = {}
    for raw in _load(T0_QUEUE):
        if address in raw:
            return  # уже в очереди — дубль POST, каскад не дублируем
    _append(T0_QUEUE, {"address": address, "ts": time.time(), "baseline": baseline})


# ── T0_PENDING → QUEUED (L1-пороги) ──
async def t0_tick(sink: Sink):
    now = time.time()
    for raw in _load(T0_QUEUE):
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if now - rec.get("ts", now) < T0_INTERVAL_MIN * 60:
            continue
        address = rec.get("address", "")
        try:
            fresh = await asyncio.to_thread(_extract_baseline, address)
        except Exception:
            fresh = {}
        liq = float(fresh.get("liquidity_usd") or 0)
        if liq < 3000:  # умер: пул пуст/ниже критического
            log.info("T0: token %s не пережил каскад (liq=$%.0f) — дайджест-строка", address[:12], liq)
            await sink.write("reject", address, "?", f"Токен не пережил t0-каскад (ликвидность ${liq:.0f}).")
            _rewrite(T0_QUEUE, [l for l in _load(T0_QUEUE) if l != raw])
            continue
        # выжил → QUEUED (L1-пороги применены мягко, T0 старта не режет)
        if len(_load(ANALYSIS_QUEUE)) >= QUEUE_MAX:
            await sink.write("reject", address, "?", f"Очередь анализа полна ({QUEUE_MAX}) — кандидат в дайджест.")
            _rewrite(T0_QUEUE, [l for l in _load(T0_QUEUE) if l != raw])
            continue
        kabal_bonus = 10.0 if await _is_kabal(address) else 0.0
        _append(ANALYSIS_QUEUE, {"address": address, "ts": now, "priority": liq + kabal_bonus})
        _rewrite(T0_QUEUE, [l for l in _load(T0_QUEUE) if l != raw])
        log.info("T0 pass: %s → QUEUED (liq=$%.0f, kabal=%s)", address[:12], liq, bool(kabal_bonus))


async def _is_kabal(address: str) -> bool:
    """KABAL-эскалация из sink-alerts за 24ч (бакет сигналов, не X)."""
    try:
        cutoff = time.time() - 86400
        sink = Sink()
        for rec in sink.read_new():
            if rec.get("type") == "alert" and rec.get("address") == address and rec.get("ts", 0) >= cutoff:
                return True
    except Exception:
        pass
    return False


# ── QUEUED → ANALYZED: rate cap + KABAL-бакет на ПЕРЕХОДЕ (N2) ──
def _ts_of(raw: str) -> float:
    try:
        return float(json.loads(raw).get("ts") or 0)
    except (ValueError, AttributeError):
        return 0.0


async def rate_gate(sink: Sink):
    entries = _load(ANALYSIS_QUEUE)
    if not entries:
        return
    hour_ago = time.time() - 3600
    # N1-minor hardening: счётчик из rate-журнала ANALYZED (устойчив к ротации sink)
    done_this_hour = sum(
        1 for raw in _load(RATE_LOG)
        if _ts_of(raw) >= hour_ago
    )
    best, best_i, best_p = None, -1, -1.0
    for i, raw in enumerate(entries):
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        p = float(rec.get("priority") or 0)
        if p > best_p:
            best, best_i, best_p = rec, i, p
    if best is None:
        return
    address = best.get("address", "")
    if done_this_hour >= RATE_CAP_H + KABAL_CAP_H:
        log.info("RATE CAP: %d/%d+KABAL — %s остаётся в очереди", done_this_hour, RATE_CAP_H, address[:12])
        return
    # ANALYZED: дедуп-ключ пишется ВНУТРИ полного прогона (record_analysis)
    _rewrite(ANALYSIS_QUEUE, [l for i, l in enumerate(entries) if i != best_i])
    _append(RATE_LOG, {"ts": time.time(), "address": address})
    log.info("ANALYZED start: %s (priority=%.0f, done=%d/%d)", address[:12], best_p, done_this_hour, RATE_CAP_H)
    await send_msf_pairresolve(sink, address)


# ── digest_timer (накопительный, окно/порог конфиг) ──
async def digest_timer(sink: Sink):
    while True:
        await asyncio.sleep(DIGEST_WINDOW_H * 3600)
        try:
            cursor = {}
            if DIGEST_CURSOR.exists():
                cursor = json.loads(DIGEST_CURSOR.read_text())
            last_id = cursor.get("last_digest_id")
            records = [r for r in sink.read_new(last_id) if r.get("type") != "digest"]
            # отсчёт только после последнего digest
            if last_id and records and records[0].get("id") == last_id:
                records = records[1:]
            if len(records) < DIGEST_THRESHOLD:
                log.info("digest: %d записей < порога %d — тишина", len(records), DIGEST_THRESHOLD)
                continue
            counts = {"verdict": 0, "reject": 0, "alert": 0}
            entries = []
            for r in records:
                t = r.get("type", "?")
                counts[t] = counts.get(t, 0) + 1
                entries.append({"id": r.get("id"), "type": t, "address": r.get("address"), "token": r.get("token"), "title": (r.get("text") or "")[:80]})
            text = f"Дайджест окна {DIGEST_WINDOW_H}ч: {len(records)} записей (verdict={counts.get('verdict',0)}, reject={counts.get('reject',0)}, alert={counts.get('alert',0)})."
            did = await sink.write(
                "digest", "", "", text,
                digest_meta={
                    "window_start": (records[0].get("ts") if records else 0),
                    "window_end": time.time(),
                    "threshold": DIGEST_THRESHOLD,
                    "counts": counts,
                    "entries": entries,
                },
            )
            DIGEST_CURSOR.parent.mkdir(parents=True, exist_ok=True)
            DIGEST_CURSOR.write_text(json.dumps({"last_digest_id": did}))
            log.info("digest написан: %d записей, id=%s", len(records), did[:8])
        except Exception as exc:
            log.warning("digest_timer error: %s", type(exc).__name__)


# ── outcome-loop (раз в час, бейзлайн из sink-записи v1.2) ──
async def outcome_loop(sink: Sink):
    while True:
        await asyncio.sleep(3600)
        try:
            measured = set()
            if OUTCOMES.exists():
                for l in _load(OUTCOMES):
                    try:
                        measured.add(json.loads(l).get("id"))
                    except ValueError:
                        pass
            cutoff = time.time() - OUTCOME_AFTER_H * 3600
            for rec in sink.read_new():
                if rec.get("type") != "verdict" or rec.get("ts", 0) > cutoff or rec.get("id") in measured:
                    continue
                base = rec.get("baseline") or {}
                base_price = float(base.get("price_usd") or 0)
                base_liq = float(base.get("liquidity_usd") or 0)
                address = rec.get("address", "")
                fresh = await asyncio.to_thread(_extract_baseline, address)
                price = float(fresh.get("price_usd") or 0)
                liq = float(fresh.get("liquidity_usd") or 0)
                if not price and not liq:
                    outcome, conf = "умер", "low"
                elif base_price and price >= 2 * base_price:
                    outcome, conf = "2x", "high"
                elif (liq < OUTCOME_DEAD_LIQ) or (base_price and price < 0.25 * base_price):
                    outcome, conf = "умер", "high"
                else:
                    outcome, conf = "флэт", "high"
                _append(OUTCOMES, {"id": rec.get("id"), "token": rec.get("token"), "address": address, "ts": rec.get("ts"), "verdict": (rec.get("text") or "")[:60], "outcome": outcome, "confidence": conf})
                log.info("outcome: %s → %s (conf=%s)", address[:12], outcome, conf)
        except Exception as exc:
            log.warning("outcome_loop error: %s", type(exc).__name__)


async def main():
    sink = Sink()
    loop = asyncio.get_running_loop()
    start_msf_http_server(sink, loop, signal_coro=t0_enroll)
    log.info("RAB9 standalone analyzer started (ingress :8089, t0=%dмин, digest=%.0fч/≥%d, cap=%d)", T0_INTERVAL_MIN, DIGEST_WINDOW_H, DIGEST_THRESHOLD, RATE_CAP_H)
    tasks = [
        asyncio.create_task(_periodic(t0_tick, sink, 60)),
        asyncio.create_task(_periodic(rate_gate, sink, 30)),
        asyncio.create_task(digest_timer(sink)),
        asyncio.create_task(outcome_loop(sink)),
    ]
    await asyncio.gather(*tasks)


async def _periodic(fn, sink, interval):
    while True:
        try:
            await fn(sink)
        except Exception as exc:
            log.warning("%s error: %s", fn.__name__, type(exc).__name__)
        await asyncio.sleep(interval)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("stopped by signal")
