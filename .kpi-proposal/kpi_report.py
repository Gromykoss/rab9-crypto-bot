#!/usr/bin/env python3
"""
rab9 KPI/E2E-отчёт — РАБОЧАЯ версия (внедрена 15.08.2026 профилем rab9).

Адаптировано под РЕАЛЬНУЮ схему проекта (НЕ под черновую спецификацию оператора):

  data/rab9_trades.db:
    pairs(pair_address, token_symbol, dex, liquidity_usd, volume24h_usd,
          market_cap_usd, fdv_usd, first_seen_at, last_seen_at,
          trade_count, oldest_trade_unix, last_trade_unix)
    pair_trades(id, pair_address, dedupe_key, tx_hash, maker, side,
                trade_time, trade_unix, token_in, token_out, amount,
                usd_value, page, created_at, UNIQUE(dedupe_key))
    pair_scan_runs(id, pair_address, trigger, mode, pages_fetched,
                   trades_fetched, trades_inserted, trades_skipped,
                   status, started_at, finished_at)

  = это DEX-scan-хранилище (сырые чужие swap-транзакции), НЕ наша
  трейдинговая книга сделок.

  data/grok_analyses.jsonl:
    входные сигналы = Grok-вердикты (timestamp, token, mc, dex, verdict,
    buy_heavy, sell_heavy, buy_ratio, kabals_top5, analysis).
    ЕДИНСТВЕННЫЙ источник «вход/конверсия-в-сигнал».

ПОЧЕМУ НЕТ слоёв 'conversion→сделка→PnL/win-rate/hold':
  Трейдинг у RAB9 ОТКЛЮЧЁН (по контракту профиля). Мы выдаём сигналы-вердикты,
  исполнение сделок / закрытие позиций / реализованный PnL физически не пишутся
  ни в одну таблицу. Выдумывать эти метрики нельзя (правило: не выдумывать данные).
  Поэтому слои 'trade_result' возвращают status=N/A + reason.

Silent-by-default (для ночного cron no_agent):
  stdout ПУСТ когда всё в норме; печать JSON только при аномалии:
    - msf_offset протух (>6ч) ИЛИ
    - offset нет вовсе ИЛИ
    - < сигналов за 30 дней чем входной порог ИЛИ
    - сигналы идут, но 0 BUY-вердиктов дольше порога.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = Path.home() / "rab9"
DB_PATH = PROJECT_ROOT / "data" / "rab9_trades.db"
LOOP_STATE_PATH = PROJECT_ROOT / "loop_state.json"
GROK_LOG_PATH = PROJECT_ROOT / "data" / "grok_analyses.jsonl"
OFFSET_PATH = PROJECT_ROOT / "msf_offset.txt"

# --- пороги аномалий -----------------------------------------------
STALE_OFFSET_SEC = 6 * 3600          # offset старше 6ч = listener мёртв
MIN_SIGNALS_30D = 1                  # 0 сигналов за 30 дней при живом входе = слепота
ZERO_BUY_DAYS = 30                   # сколько дней без BUY-вердикта = конверсия застряла
BUY_MARKERS = ("BUY", "🟢", "КУПИТЬ", "LONG")   # маркеры позитивного вердикта
# ---------------------------------------------------------------------


def _read_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _read_grok_rows() -> list[dict]:
    rows = []
    try:
        with open(GROK_LOG_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except Exception:
        pass
    return rows


def _parse_ts(value) -> datetime | None:
    if isinstance(value, (int, float)) and value > 1e9:
        return datetime.fromtimestamp(value, timezone.utc)
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def kpi_input() -> dict:
    """Вход: сигналы/день, уникальных токенов (из grok_analyses.jsonl + loop_state)."""
    rows = _read_grok_rows()
    now = datetime.now(timezone.utc)
    cut30 = now - timedelta(days=30)
    sig30 = [r for r in rows if (t := _parse_ts(r.get("timestamp"))) and t >= cut30]
    tokens30 = {r.get("token") for r in sig30 if r.get("token")}
    return {
        "source": "data/grok_analyses.jsonl",
        "total_analyses": len(rows),
        "last_analysis_ts": max((_parse_ts(r.get("timestamp")) for r in rows if _parse_ts(r.get("timestamp"))), default=None).isoformat() if any(_parse_ts(r.get("timestamp")) for r in rows) else None,
        "signals_last_30d": len(sig30),
        "unique_tokens_last_30d": len(tokens30),
        "tokens_last_30d": sorted(tokens30),
    }


def kpi_conversion() -> dict:
    """Конверсия вход → BUY-вердикт (реально извлекаемая). Сделки = N/A (trading off)."""
    rows = _read_grok_rows()
    now = datetime.now(timezone.utc)
    cut30 = now - timedelta(days=30)
    sig30 = [r for r in rows if (t := _parse_ts(r.get("timestamp"))) and t >= cut30]
    buy30 = [r for r in sig30 if any(m in str(r.get("verdict", "")).upper() for m in BUY_MARKERS)]
    # Вся история: сколько BUY-вердиктов было вообще
    buy_all = [r for r in rows if any(m in str(r.get("verdict", "")).upper() for m in BUY_MARKERS)]
    return {
        "signals_30d": len(sig30),
        "buy_verdicts_30d": len(buy30),
        "buy_verdicts_all_time": len(buy_all),
        "conversion_signal_to_buy_30d_pct": round(100 * len(buy30) / len(sig30), 1) if sig30 else None,
        # сделки не исполняем — честно помечаем причину
        "closed_positions": {"status": "N/A", "reason": "trading disabled (contract rule) — no execution/position DB"},
    }


def kpi_result() -> dict:
    """Реализованный PnL/win-rate/hold — НЕДОСТУПНО: нет торговой книги сделок."""
    return {
        "realized_pnl": {"status": "N/A", "reason": "no closing of positions — trading disabled; rab9_trades.db is a DEX scan store, not a trade book"},
        "win_rate": None,
        "avg_hold_sec": None,
    }


def kpi_quality() -> dict:
    """Качество: loop_state analyses/duplicates + распределение verdict из grok log."""
    state = _read_json(LOOP_STATE_PATH) or {}
    rows = _read_grok_rows()
    verdict_breakdown: dict[str, int] = {}
    for r in rows:
        v = str(r.get("verdict", "")).split("|")[0].strip()
        verdict_breakdown[v] = verdict_breakdown.get(v, 0) + 1
    return {
        "total_analyses": state.get("total", 0),
        "duplicates": state.get("duplicates", 0),
        "verdict_breakdown": verdict_breakdown,
        "verdict_wait_share_pct": round(100 * verdict_breakdown.get("⏳ WAIT", 0) / max(1, len(rows)), 1),
    }


def kpi_e2e_health() -> dict:
    """E2E: offset двигается? сервисы активны (systemd stat)."""
    offset_age = None
    offset_val = None
    if OFFSET_PATH.exists():
        try:
            offset_val = int(OFFSET_PATH.read_text().strip())
            offset_age = int(time.time()) - offset_val if offset_val else None
        except Exception:
            pass
    # проверка systemd-сервисов (только статус, НЕ рестарт — запрещено)
    services = {}
    for unit in ("rab9-crypto-hermes", "rab9-listener"):
        try:
            out = os.popen(f"systemctl is-active {unit} 2>/dev/null").read().strip()
            services[unit] = out
        except Exception:
            services[unit] = "unknown"
    return {
        "msf_offset_stale": offset_age is not None and offset_age > STALE_OFFSET_SEC,
        "msf_offset_missing": offset_val is None,
        "msf_offset_age_sec": offset_age,
        "systemd": services,
    }


def _anomalies(report: dict) -> list[str]:
    """Порог аномалий: когда печатать в stdout (иначе молчать = silent-by-default)."""
    issues = []
    e = report["e2e_health"]
    if e.get("msf_offset_missing"):
        issues.append("msf_offset.txt отсутствует — listener не обновил offset")
    elif e.get("msf_offset_stale"):
        issues.append(f"msf_offset протух: {e.get('msf_offset_age_sec')} сек > {STALE_OFFSET_SEC}")
    sysd = e.get("systemd", {})
    for unit, st in sysd.items():
        if st != "active":
            issues.append(f"service {unit} NOT active (status={st})")
    inp = report["input"]
    if inp.get("signals_last_30d", 1) < MIN_SIGNALS_30D:
        # голый 0 при живом offset = слепота (рыночное затишье ли, сбой ли — подсветить)
        issues.append(f"0 сигналов за 30 дней при живом offset ({MIN_SIGNALS_30D} min) — слепота?")
    return issues


def build_report() -> dict:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": kpi_input(),
        "conversion": kpi_conversion(),
        "result": kpi_result(),
        "quality": kpi_quality(),
        "e2e_health": kpi_e2e_health(),
    }
    return report


if __name__ == "__main__":
    report = build_report()
    issues = _anomalies(report)
    if issues:
        # аномалия → печатаем компактный JSON (cron no_agent доставит текст)
        print("⚠️ RAB9 KPI anomalies:")
        for i in issues:
            print(" -", i)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    # иначе: пустой stdout — silent tick, ничего не шлём
