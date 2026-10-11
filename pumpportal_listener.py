#!/usr/bin/env python3
"""PumpPortal Listener — пуш-вход RAB9: pump.fun миграции → ingress :8089/msf-signal.

Spec: openspec/specs/pumpportal-ingress.md (v0.3 FROZEN)
Design: openspec/changes/pumpportal-ingress/design.md
"""
import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid

import requests
import websockets

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("pumpportal_listener")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Config (.env + defaults) ──
def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)

PPP_WS_URL = _env("PPP_WS_URL", "wss://pumpportal.fun/api/data")
PPP_INGRESS_URL = _env("PPP_INGRESS_URL", "http://127.0.0.1:8089")
PPP_MAX_POST_ATTEMPTS = int(_env("PPP_MAX_POST_ATTEMPTS", "3"))
PPP_POST_BACKOFF_S = float(_env("PPP_POST_BACKOFF_S", "2"))
PPP_RECONNECT_BACKOFF_S = float(_env("PPP_RECONNECT_BACKOFF_S", "1"))
PPP_RECONNECT_CAP_S = float(_env("PPP_RECONNECT_CAP_S", "60"))
PPP_SUB_ACK_TIMEOUT_S = float(_env("PPP_SUB_ACK_TIMEOUT_S", "30"))
PPP_WS_PING_INTERVAL_S = float(_env("PPP_WS_PING_INTERVAL_S", "20"))
PPP_WS_PING_TIMEOUT_S = float(_env("PPP_WS_PING_TIMEOUT_S", "20"))
PPP_REPLAY_DELAY_S = float(_env("PPP_REPLAY_DELAY_S", "1"))
PPP_FAILED_FILE = os.path.join(
    BASE_DIR, _env("PPP_FAILED_FILE", "data/ingress_failed.jsonl")
)
PPP_HTTP_TIMEOUT_S = 10  # requests default = infinite — запрещён (design)

RAB9_HTTP_SECRET = ""
_env_file = os.path.join(BASE_DIR, ".env")
if os.path.exists(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            if _line.startswith("RAB9_HTTP_SECRET="):
                RAB9_HTTP_SECRET = _line.split("=", 1)[1].strip().strip("\"'")
                break

if not RAB9_HTTP_SECRET:
    log.error("RAB9_HTTP_SECRET not found in %s", _env_file)
    sys.exit(1)

SOLANA_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")


def is_msf_solana_address(address: str) -> bool:
    """Копия логики msf_listener (base58, 32-44) — контракт ingress в msf_http."""
    return bool(address) and bool(SOLANA_RE.fullmatch(address))


# ── Journal failed (ingress-failure-handling) ──
def _atomic_write(lines: list) -> None:
    tmp = PPP_FAILED_FILE + ".tmp"
    os.makedirs(os.path.dirname(PPP_FAILED_FILE), exist_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        for line in lines:
            f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, PPP_FAILED_FILE)


def _journal_append(record: dict) -> None:
    record["id"] = str(uuid.uuid4())
    record["ts"] = time.time()
    os.makedirs(os.path.dirname(PPP_FAILED_FILE), exist_ok=True)
    with open(PPP_FAILED_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _journal_load() -> list:
    if not os.path.exists(PPP_FAILED_FILE):
        return []
    with open(PPP_FAILED_FILE) as f:
        return [line.strip() for line in f if line.strip()]


def _journal_rotate_if_big() -> None:
    if not os.path.exists(PPP_FAILED_FILE):
        return
    with open(PPP_FAILED_FILE) as f:
        n = sum(1 for _ in f)
    if n > 10000:
        rotated = PPP_FAILED_FILE + "." + time.strftime("%Y%m%dT%H%M%S") + ".jsonl"
        os.replace(PPP_FAILED_FILE, rotated)
        log.warning("ingress_failed.jsonl rotated (%d lines) -> %s", n, rotated)


# ── Ingress HTTP (всё через to_thread, timeout явный) ──
def _post_signal_sync(address: str) -> requests.Response:
    return requests.post(
        PPP_INGRESS_URL + "/msf-signal",
        json={"chain": "solana", "address": address},
        headers={"X-RAB9-SECRET": RAB9_HTTP_SECRET},
        timeout=PPP_HTTP_TIMEOUT_S,
    )


def _health_sync() -> bool:
    try:
        r = requests.get(PPP_INGRESS_URL + "/health", timeout=PPP_HTTP_TIMEOUT_S)
        return r.status_code == 200
    except requests.RequestException:
        return False


async def _post_signal(address: str) -> bool:
    """POST с retry; исчерпание попыток → журнал неудач. True = доставлен."""
    for attempt in range(1, PPP_MAX_POST_ATTEMPTS + 1):
        try:
            resp = await asyncio.to_thread(_post_signal_sync, address)
            if resp.status_code == 200:
                return True
            log.warning("POST /msf-signal %s -> HTTP %d (attempt %d)", address, resp.status_code, attempt)
        except requests.RequestException as exc:
            log.warning("POST /msf-signal %s failed (attempt %d): %s", address, attempt, type(exc).__name__)
        if attempt < PPP_MAX_POST_ATTEMPTS:
            await asyncio.sleep(PPP_POST_BACKOFF_S * (2 ** (attempt - 1)))
    _journal_append({"address": address, "error": "ingress_unreachable"})
    return False


async def _replay_failed() -> None:
    """Per-line ack: успешные строки удаляются индивидуально; fsync; replay-backoff."""
    _journal_rotate_if_big()
    while True:
        lines = _journal_load()
        if not lines:
            return
        replayed_any = False
        for raw in lines:
            try:
                record = json.loads(raw)
                address = record.get("address", "")
            except (ValueError, AttributeError):
                log.warning("journal: dropping malformed line id=%s", raw[:40])
                _journal_remove(raw)
                continue
            if not is_msf_solana_address(address):
                _journal_remove(raw)
                continue
            try:
                resp = await asyncio.to_thread(_post_signal_sync, address)
            except requests.RequestException:
                log.warning("replay: ingress down, stop replay (id=%s)", record.get("id", "?")[:8])
                return
            if resp.status_code == 200:
                _journal_remove(raw)
                replayed_any = True
                log.info("replay: delivered id=%s", record.get("id", "?")[:8])
                await asyncio.sleep(PPP_REPLAY_DELAY_S)
            else:
                log.warning("replay: HTTP %d, stop (id=%s)", resp.status_code, record.get("id", "?")[:8])
                return
        if not replayed_any:
            return


def _journal_remove(raw_line: str) -> None:
    lines = _journal_load()
    lines = [l for l in lines if l != raw_line]
    _atomic_write(lines)


# ── WS main loop (resilient-connection + subscription-liveness + ws-keepalive) ──
async def _session() -> None:
    async with websockets.connect(
        PPP_WS_URL,
        ping_interval=PPP_WS_PING_INTERVAL_S,
        ping_timeout=PPP_WS_PING_TIMEOUT_S,
        open_timeout=PPP_HTTP_TIMEOUT_S,
    ) as ws:
        await ws.send(json.dumps({"method": "subscribeMigration"}))
        # subscription-liveness: ждём ack, иначе считаем подписку несостоявшейся
        ack_deadline = asyncio.get_event_loop().time() + PPP_SUB_ACK_TIMEOUT_S
        acked = False
        while not acked:
            raw = await asyncio.wait_for(
                ws.recv(), timeout=max(1.0, ack_deadline - asyncio.get_event_loop().time())
            )
            msg = json.loads(raw)
            if "Subscribed" in str(msg.get("message", "")):
                acked = True
                log.info("subscription active")  # наблюдаемый критерий живой подписки
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            address = str(msg.get("mint") or "")
            if not is_msf_solana_address(address):
                continue
            ok = await _post_signal(address)
            if ok:
                log.info("ingest: %s accepted", address)
            await _replay_failed()


async def main() -> None:
    backoff = PPP_RECONNECT_BACKOFF_S
    while True:
        try:
            log.info("connecting %s (backoff %.0fs)", PPP_WS_URL, backoff)
            await _session()
            backoff = PPP_RECONNECT_BACKOFF_S  # чистое закрытие — сброс backoff
        except asyncio.TimeoutError:
            log.warning("session timeout (no sub ack / recv timeout)")
        except (websockets.ConnectionClosed, OSError) as exc:
            log.warning("WS down: %s", type(exc).__name__)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, PPP_RECONNECT_CAP_S)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("stopped by signal")
