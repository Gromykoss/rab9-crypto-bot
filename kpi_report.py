#!/usr/bin/env python3
"""
rab9 KPI/E2E-отчёт — рабочий скрипт (реализация черновика .kpi-proposal/kpi_report.py).

Схема реальной БД (data/rab9_trades.db, проверено 15.08.2026):
  - pairs(22)           pair_address, token_symbol, quote_symbol, dex, liquidity_usd,
                        volume24h_usd, market_cap_usd, fdv_usd, first_seen_at, last_seen_at,
                        trade_count, oldest_trade_unix, last_trade_unix
  - pair_trades(190226) id, pair_address, dedupe_key, tx_hash, maker, side, trade_time,
                        trade_unix, token_in, token_out, amount, usd_value, page, created_at
  - pair_scan_runs(37)  id, pair_address, trigger('msf'), mode, pages_fetched, trades_fetched,
                        trades_inserted, trades_skipped, status('200'|'request_error'),
                        started_at, finished_at   (последний скан: 2026-06-14)

Факты внедрения:
  - Все timestamps ISO 'YYYY-MM-DDTHH:MM:SSZ' — сравнение лексическое.
  - usd_value в pair_trades = NULL везде (объём в USD не записывался).
  - Позиций/PnL в схеме НЕТ — «0 закрытых сделок» это структурный факт, не баг.
  - msf_offset.txt у listener лежит в ~/.hermes/secrets/rab9/, пишется ТОЛЬКО при
    получении апдейтов (в затишье файл стареет — это НЕ признак смерти listener).
    Корневой rab9/msf_offset.txt пишет msf_poller.py (второй поллер, зона Hermes).

Режимы:
  --debug              печатать полный JSON всегда (для self-test).
  без флагов (cron)    печатать ТОЛЬКО при аномалии; silent-on-success.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

RAB9_DIR = Path("/home/hermes-workspace/rab9")
DB_PATH = RAB9_DIR / "data" / "rab9_trades.db"
LOOP_STATE_PATH = RAB9_DIR / "loop_state.json"
# Реальный offset-файл listener'а (пишется только при апдейтах — в затишье стареет)
OFFSET_LISTENER = Path("/home/hermes-workspace/.hermes/secrets/rab9/msf_offset.txt")
HEALTH_URL = "http://localhost:8089/health"
SERVICES = ["rab9-crypto-hermes", "msf-listener"]

# ── Пороги аномалий (правка — осознанно, с комментарием) ─────────────────────
STALE_OFFSET_SEC = 6 * 3600      # WARN: listener-файл старше 6ч. НЕ триггер аларма сам по себе:
                                 # в затишье (мемы молчат) listener не пишет offset — это норма.
ALARM_SERVICE_DOWN = True        # любой systemd-сервис не active → печатать
ALARM_HEALTH_BAD = True          # :8089/health != 200 → печатать
ALARM_CONVERSION_STUCK = True    # вход жив (сигналы за 24ч > 0), а закрытых позиций 0 → печатать
ALARM_SCAN_ERRORS = True         # скан-раны со статусом != '200' за 24ч > 0 → печатать


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_iso() -> str:
    return _iso(datetime.now(timezone.utc))


def _day_ago_iso() -> str:
    return _iso(datetime.now(timezone.utc) - timedelta(days=1))


def kpi_input(db: sqlite3.Connection) -> dict:
    """Вход: сигналы (scan runs), уникальные токены, захваченные трейды."""
    day_ago = _day_ago_iso()
    scans_total = db.execute("SELECT COUNT(*) FROM pair_scan_runs").fetchone()[0]
    scans_24h = db.execute(
        "SELECT COUNT(*) FROM pair_scan_runs WHERE started_at >= ?", (day_ago,)
    ).fetchone()[0]
    scans_error_24h = db.execute(
        "SELECT COUNT(*) FROM pair_scan_runs WHERE started_at >= ? AND status != '200'",
        (day_ago,),
    ).fetchone()[0]
    tokens_24h = db.execute(
        "SELECT COUNT(DISTINCT pair_address) FROM pair_scan_runs WHERE started_at >= ?",
        (day_ago,),
    ).fetchone()[0]
    trades_24h = db.execute(
        "SELECT COUNT(*) FROM pair_trades WHERE created_at >= ?", (day_ago,)
    ).fetchone()[0]
    pairs_total = db.execute("SELECT COUNT(*) FROM pairs").fetchone()[0]
    last_scan = db.execute("SELECT MAX(started_at) FROM pair_scan_runs").fetchone()[0]
    return {
        "signals_24h": scans_24h,
        "signals_total": scans_total,
        "scan_errors_24h": scans_error_24h,
        "unique_tokens_24h": tokens_24h,
        "trades_captured_24h": trades_24h,
        "pairs_total": pairs_total,
        "last_scan_at": last_scan,
    }


def kpi_conversion(db: sqlite3.Connection) -> dict:
    """Конверсия: сигнал → скан с данными → захваченные трейды → закрытая позиция."""
    day_ago = _day_ago_iso()
    row = db.execute(
        "SELECT COALESCE(SUM(trades_fetched),0), COALESCE(SUM(trades_inserted),0), "
        "COALESCE(SUM(trades_skipped),0) FROM pair_scan_runs WHERE started_at >= ?",
        (day_ago,),
    ).fetchone()
    row_all = db.execute(
        "SELECT COALESCE(SUM(trades_fetched),0), COALESCE(SUM(trades_inserted),0), "
        "COALESCE(SUM(trades_skipped),0) FROM pair_scan_runs"
    ).fetchone()
    return {
        "scans_with_data_24h": int(row[0] > 0),
        "trades_fetched_24h": row[0],
        "trades_inserted_24h": row[1],
        "trades_skipped_24h": row[2],
        "trades_fetched_total": row_all[0],
        "trades_inserted_total": row_all[1],
        # В схеме НЕТ таблицы позиций/PnL — «закрытые позиции» структурно 0.
        # Это не баг, а отсутствие трекинга результата (открыто для будущего слоя).
        "closed_positions": 0,
        "position_tracking": "not_implemented",
    }


def kpi_result(db: sqlite3.Connection) -> dict:
    """Результат: реализованный PnL, win-rate, hold. Схема БД их не хранит."""
    usd_total = db.execute("SELECT SUM(usd_value) FROM pair_trades").fetchone()[0]
    trades_total = db.execute("SELECT COUNT(*) FROM pair_trades").fetchone()[0]
    return {
        "realized_pnl_usd": None,       # не трекается
        "win_rate": None,               # нет закрытых позиций
        "avg_hold_hours": None,         # нет трекинга входа/выхода
        "trades_captured_total": trades_total,
        "trades_usd_value_total": usd_total if usd_total is not None else 0.0,
        "pnl_tracking": "not_implemented",
    }


def kpi_quality() -> dict:
    """Качество: loop_verifier (PASS/FLAG/FAIL) из loop_state.json."""
    try:
        data = json.loads(LOOP_STATE_PATH.read_text())
    except Exception as e:
        return {"error": str(e)}
    analyses = data.get("analyses", [])
    verdict_breakdown: dict[str, int] = {}
    for a in analyses:
        if isinstance(a, dict):
            v = str(a.get("verdict", "?") or "?")
            verdict_breakdown[v] = verdict_breakdown.get(v, 0) + 1
    return {
        "total_analyses": data.get("total", 0),
        "duplicates": data.get("duplicates", 0),
        "last_cleanup": data.get("last_cleanup"),
        # ВАЖНО: analyses-список ужат cleanup'ом — breakdown только по текущим записям
        "analyses_stored": len(analyses),
        "verdict_breakdown_stored": verdict_breakdown,
    }


def _is_active(service: str) -> str:
    try:
        out = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
        return out or "unknown"
    except Exception as e:
        return f"error:{e}"


def _health_code() -> int | None:
    try:
        req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "Mozilla/5.0 RAB9-kpi"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except Exception:
        return None


def kpi_e2e_health() -> dict:
    """E2E: сервисы active, health 200, offset listener-файла (WARN-only)."""
    offset_age = None
    offset_value = None
    if OFFSET_LISTENER.exists():
        try:
            offset_value = OFFSET_LISTENER.read_text().strip()
            offset_age = int(time.time() - OFFSET_LISTENER.stat().st_mtime)
        except Exception:
            pass
    services = {s: _is_active(s) for s in SERVICES}
    return {
        "services": services,
        "core_active": services.get("rab9-crypto-hermes") == "active",
        "listener_active": services.get("msf-listener") == "active",
        "health_http": _health_code(),
        # WARN-only: возраст listener-файла. В затишье растёт — не аларм.
        "offset_value": offset_value,
        "offset_file_age_sec": offset_age,
        "offset_stale_warn": offset_age is not None and offset_age > STALE_OFFSET_SEC,
    }


def build_report() -> dict:
    report = {
        "generated_at": _now_iso(),
        "input": {},
        "conversion": {},
        "result": {},
        "quality": kpi_quality(),
        "e2e_health": kpi_e2e_health(),
    }
    try:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            report["input"] = kpi_input(conn)
            report["conversion"] = kpi_conversion(conn)
            report["result"] = kpi_result(conn)
        finally:
            conn.close()
    except Exception as e:
        report["input"] = {"db_error": str(e)}
    return report


def anomalies(report: dict) -> list[str]:
    """Порог аномалий — ЧТО печатать в stdout (крон доставит, иначе silent)."""
    out: list[str] = []
    e2e = report.get("e2e_health", {})
    inp = report.get("input", {})
    conv = report.get("conversion", {})

    if "db_error" in inp:
        out.append(f"DB_ERROR: {inp['db_error']}")
    if ALARM_SERVICE_DOWN:
        if not e2e.get("core_active"):
            out.append(f"CORE_DOWN: rab9-crypto-hermes = {e2e.get('services', {}).get('rab9-crypto-hermes')}")
        if not e2e.get("listener_active"):
            out.append(f"LISTENER_DOWN: msf-listener = {e2e.get('services', {}).get('msf-listener')}")
    if ALARM_HEALTH_BAD and e2e.get("health_http") != 200:
        out.append(f"HEALTH_BAD: :8089/health = {e2e.get('health_http')}")
    if ALARM_SCAN_ERRORS and inp.get("scan_errors_24h", 0) > 0:
        out.append(f"SCAN_ERRORS_24H: {inp.get('scan_errors_24h')} (status != 200)")
    if ALARM_CONVERSION_STUCK and inp.get("signals_24h", 0) > 0 and conv.get("closed_positions", 0) == 0:
        out.append(
            f"CONVERSION_STUCK: {inp.get('signals_24h')} сигналов за 24ч, "
            f"закрытых позиций 0 (трекинг PnL не реализован)"
        )
    # offset_stale_warn сам по себе НЕ аларм (затишье = норма), но попадает в вывод
    # аномалии как контекст, если что-то другое сработало.
    return out


if __name__ == "__main__":
    report = build_report()
    debug = "--debug" in sys.argv
    if debug:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        sys.exit(0)
    alerts = anomalies(report)
    if alerts:
        # Небольшой контекст + список аномалий — сырой отчёт не дублируем целиком
        print("RAB9 KPI аномалии:", "; ".join(alerts))
        print(json.dumps(report, ensure_ascii=False, default=str))
    # иначе: пустой stdout → крон молчит (silent-by-default)
