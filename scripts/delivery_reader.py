#!/usr/bin/env python3
"""delivery-reader: доставка digest+alert из sink анализатора в чат владельца.

Контракт `standalone-analyzer.delivery-reader-contract` (openspec/specs/standalone-analyzer.md,
сценарий помечен `<!-- no-ci -->`): доставку делает ВНЕШНИЙ RAB9-агент (Hermes-профиль), НЕ анализатор.

Правила:
  * sink-файл `data/analyses_out/analyses.jsonl` читается целиком (инкрементально по offset-файлу
    `data/analyses_out/delivery_offset.json`, поле `last_delivered_id` — последний доставленный id);
  * записи ПОСЛЕ offset = очередь; записи ДО offset = уже доставлены (повторной доставки нет);
  * в чат уходит ТОЛЬКО `digest` (свод окна) и `alert` (фазы кабала/KOL); `verdict`/`reject`
    отдельными сообщениями НЕ уходят — они либо внутри дайджеста, либо помечаются доставленными молча;
  * не чаще одного сообщения в час (интервал настраивается `--interval`);
  * пустое окно = пустой stdout = тишина (для no_agent-крона это «сообщения нет»);
  * при ротации/обрезании sink offset сбрасывается, но даётся не более `MAX_QUEUE` последних записей.

Режимы ручного запуска (в крон не попадают):
  --dry-run   — показать, что было бы отправлено, состояние НЕ менять;
  --status    — показать состояние offset-файла;
  --force     — игнорировать часовой интервал;
  --sink/--state — альтернативные пути (тесты).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SINK_PATH = ROOT / "data" / "analyses_out" / "analyses.jsonl"
STATE_PATH = ROOT / "data" / "analyses_out" / "delivery_offset.json"
LOCK_PATH = ROOT / "data" / "analyses_out" / "delivery_reader.lock"

DELIVER_TYPES = ("digest", "alert")
MIN_INTERVAL_S = 3600          # «не чаще раза в час»
MAX_QUEUE = 200                # сколько последних записей брать, если offset потерян
MAX_RECORDS_PER_MSG = 20       # ограничение размера одного сообщения (записи)
MAX_CHARS = 3800               # ограничение размера одного сообщения (символы)


def _now() -> float:
    return time.time()


def _fmt_ts(ts) -> str:
    try:
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (TypeError, ValueError):
        return "?"
    return dt.strftime("%d.%m %H:%M UTC")


def read_sink(path: Path):
    """Прочитать sink-jsonl. Битые строки пропускаются молча (файл может писаться в момент чтения)."""
    rows = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("id"):
                    rows.append(row)
    except FileNotFoundError:
        return []
    return rows


def load_state(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            state = json.load(fh)
        if isinstance(state, dict):
            return state
    except (FileNotFoundError, ValueError):
        pass
    return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _index_of_id(rows, target_id):
    if not target_id:
        return None
    for index in range(len(rows) - 1, -1, -1):
        if rows[index].get("id") == target_id:
            return index
    return None


def build_queue(rows, last_delivered_id):
    """Очередь = записи после offset. Возврат: (queue, offset_lost)."""
    index = _index_of_id(rows, last_delivered_id)
    if index is not None:
        return rows[index + 1 :], False
    if last_delivered_id:
        # offset потерян: ротация файла или ручная правка — берём хвост, чтобы не залить всю историю
        return rows[-MAX_QUEUE:], True
    return rows[-MAX_QUEUE:], False


def render(window, delivered_count: int, skipped: int) -> str:
    """Собрать текст сообщения для чата владельца (только digest + alert)."""
    digests = [r for r in window if r.get("type") == "digest"]
    alerts = [r for r in window if r.get("type") == "alert"]
    first_ts = window[0].get("ts") if window else None
    last_ts = window[-1].get("ts") if window else None

    parts = [
        "📬 RAB9 · анализатор → доставка",
        f"Окно: {_fmt_ts(first_ts)} – {_fmt_ts(last_ts)}",
        f"В очереди: {len(window)} записей (дайджестов: {len(digests)}, алертов: {len(alerts)}); "
        f"вердиктов/отказов без отдельного сообщения: {skipped}",
    ]
    if digests:
        parts += ["", "———— ДАЙДЖЕСТ ЗА ОКНО ————"]
        for row in digests:
            parts.append((row.get("text") or "").strip())
    if alerts:
        parts += ["", "———— ⚠️ АЛЕРТЫ (кабал/KOL) ————"]
        for row in alerts:
            parts.append((row.get("text") or "").strip())

    text = "\n".join(parts).strip()
    if len(text) > MAX_CHARS:
        text = text[: MAX_CHARS - 40].rstrip() + "\n… (обрезано, полный текст в sink)"
    return text


def run(args) -> int:
    sink = Path(args.sink) if args.sink else SINK_PATH
    state_path = Path(args.state) if args.state else STATE_PATH

    if args.status:
        state = load_state(state_path)
        out = {
            "sink": str(sink),
            "sink_exists": sink.exists(),
            "sink_size": sink.stat().st_size if sink.exists() else 0,
            "records": len(read_sink(sink)),
            "state": state,
        }
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0

    lock_fh = open(LOCK_PATH, "a+") if not (args.sink or args.state) else None
    if lock_fh is not None:
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # параллельный прогон уже работает — молча выходим, повторной доставки не будет
            return 0

    try:
        rows = read_sink(sink)
        if not rows:
            return 0
        state = load_state(state_path)
        last_id = state.get("last_delivered_id")
        queue, offset_lost = build_queue(rows, last_id)

        last_delivery_ts = float(state.get("last_delivered_ts") or 0)
        now = _now()
        interval_ok = args.force or (now - last_delivery_ts) >= float(args.interval)

        deliverable = [r for r in queue if r.get("type") in DELIVER_TYPES]

        if not deliverable:
            # Очередь прочитана, но доставлять нечего (verdict/reject — молча).
            if queue:
                state["last_delivered_id"] = queue[-1]["id"]
            state["last_read_ts"] = now
            state["offset_lost"] = bool(offset_lost)
            save_state(state_path, state)
            if args.verbose or args.dry_run:
                print("[SILENT] новых digest/alert нет — сообщение не отправлено")
            return 0

        if not interval_ok:
            # Есть что отдать, но часовой интервал не истёк — очередь копится, offset не двигаем.
            state["last_read_ts"] = now
            save_state(state_path, state)
            if args.verbose or args.dry_run:
                wait_s = int(float(args.interval) - (now - last_delivery_ts))
                print(f"[SILENT] интервал не истёк (ещё {wait_s} с), в очереди {len(deliverable)} записей")
            return 0

        window = queue[:MAX_RECORDS_PER_MSG]
        sent_ids = {r.get("id") for r in deliverable}
        skipped = sum(1 for r in window if r.get("type") not in DELIVER_TYPES)
        text = render(window, len(deliverable), skipped)

        if args.dry_run:
            print("--- DRY-RUN, состояние не меняется ---")
            print(text)
            return 0

        print(text)

        state["last_delivered_id"] = window[-1]["id"]
        state["last_delivered_ts"] = now
        state["last_read_ts"] = now
        state["delivered_records"] = int(state.get("delivered_records") or 0) + len(
            [r for r in window if r.get("id") in sent_ids]
        )
        history = state.get("history") or []
        history.append(
            {
                "at": now,
                "records": len(window),
                "delivered": len([r for r in window if r.get("id") in sent_ids]),
                "digests": [r.get("id") for r in window if r.get("type") == "digest"],
                "alerts": [r.get("id") for r in window if r.get("type") == "alert"],
            }
        )
        state["history"] = history[-20:]
        save_state(state_path, state)
        return 0
    finally:
        if lock_fh is not None:
            try:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)
            finally:
                lock_fh.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="delivery-reader: digest+alert из sink в чат")
    parser.add_argument("--dry-run", action="store_true", help="показать сообщение, состояние не менять")
    parser.add_argument("--status", action="store_true", help="показать состояние offset-файла")
    parser.add_argument("--force", action="store_true", help="игнорировать часовой интервал")
    parser.add_argument("--verbose", action="store_true", help="печатать [SILENT]-пояснения (не для крона)")
    parser.add_argument("--interval", type=float, default=MIN_INTERVAL_S, help="минимальный интервал, с")
    parser.add_argument("--sink", default=None, help="путь к jsonl (по умолчанию data/analyses_out/analyses.jsonl)")
    parser.add_argument("--state", default=None, help="путь к offset-файлу")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
