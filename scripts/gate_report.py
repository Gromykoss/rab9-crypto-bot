#!/usr/bin/env python3
"""gate-report: read-only сводка «сколько токенов прошло фильтр доставки и каким гейтом отсеяны».

Зачем: владелец 24.11 (через fleet-шину) решил фильтр доставки `433a2c592e05`
НЕ трогать трое суток и 27.11 получить сводку: сколько токенов прошло/отсеяно и
каким гейтом, особенно гейтом «умные деньги: набор». Если прошедших ноль —
нужна заготовка варианта «набор = бонус к оценке, не обязательный» (внедрять
только после «да» владельца).

Что делает скрипт:
  * читает sink анализатора (`data/analyses_out/analyses.jsonl` + ротированные
    `analyses.<ts>.jsonl`) — только чтение, ничего не пишет и не двигает offset;
  * берёт ТЕКУЩИЕ пороги и правила фильтра из `scripts/delivery_reader.py`
    (единый источник — своей копии порогов здесь нет, дрейф невозможен);
  * на окне считает: сколько оценок, сколько прошло фильтр, сколько токенов
    задет каждым гейтом и сколько отсеяно ТОЛЬКО этим гейтом;
  * отдельно считает вариант «умные деньги = бонус» (сколько токенов прошло бы,
    если снять обязательность гейта набора) — как заготовку решения владельца.

Режимы:
  --hours N      окно в часах назад от --until (по умолчанию 72)
  --since/--until ISO («2026-11-24T15:00»), UTC
  --out-dir DIR  каталог sink (по умолчанию data/analyses_out, нужен тестам)
  --json         машинный вывод вместо человеческого текста
  --examples N   сколько токенов показывать примерами (по умолчанию 5)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT / "data" / "analyses_out"

sys.path.insert(0, str(ROOT / "scripts"))
import delivery_reader as dr  # noqa: E402  (единый источник порогов фильтра)

CURRENT_SINK = "analyses.jsonl"
ROTATED_GLOB = "analyses.*.jsonl"
ROTATION_MARGIN_S = 3600.0     # запас на расхождение mtime ротации и первой записи окна

# гейт → (ключ, маркер в тексте блокера из delivery_reader, подпись для отчёта)
GATES = (
    ("mc", "капа ", "капа ниже порога"),
    ("score", "оценка ", "оценка ниже порога"),
    ("avoid", "анализатор пометил AVOID", "анализатор пометил AVOID"),
    ("risk", "ончейн-риск", "ончейн-риск не низкий (🔴)"),
    ("sm", "умные деньги не набирают", "умные деньги не набирают позицию"),
    ("top10", "топ-10 держат", "концентрация у топ-10 выше порога"),
    ("cabal", "по адресу есть кабал-алерт", "кабал-алерт по адресу за сутки"),
)
OTHER_KEY = "other"
OTHER_LABEL = "прочая причина (формулировка блока не распознана)"


def gate_of(blocker: str) -> str:
    """Ключ гейта по тексту блокера из delivery_reader.potential_blockers."""
    text = str(blocker or "")
    for key, marker, _label in GATES:
        if marker in text:
            return key
    return OTHER_KEY


def gate_label(key: str) -> str:
    for gate_key, _marker, label in GATES:
        if gate_key == key:
            return label
    return OTHER_LABEL


def gate_threshold_note(key: str) -> str:
    """Расшифровка порога — из живых констант фильтра, не из копии."""
    return {
        "mc": f"капа ниже {dr.money(dr.MC_MIN_USD)}",
        "score": f"оценка ниже {dr.SCORE_MIN}/125",
        "top10": f"концентрация у топ-10 выше {dr.TOP10_MAX_PCT}%",
    }.get(key, gate_label(key))


# ── чтение sink ──


def sink_files(out_dir: Path, since_ts: float):
    """Файлы sink за окно: текущий + ротированные, чья ротация не старше окна.

    Ротированный файл содержит записи до времени ротации (mtime), значит файл с
    mtime < since записей окна содержать не может — читать его незачем (файлов
    накапливается много, полный перебор тормозит отчёт).
    """
    out_dir = Path(out_dir)
    files = []
    for path in sorted(out_dir.glob(ROTATED_GLOB)):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime + ROTATION_MARGIN_S >= since_ts:
            files.append(path)
    current = out_dir / CURRENT_SINK
    if current.is_file():
        files.append(current)
    return files


def load_rows(out_dir: Path, since_ts: float):
    """Все записи sink за окно (файлы + ротированные), без дублей по id, по времени."""
    rows, seen = [], set()
    for path in sink_files(out_dir, since_ts):
        try:
            handle = path.open(encoding="utf-8")
        except OSError:
            continue
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or not row.get("id"):
                    continue
                rid = row.get("id")
                if rid in seen:
                    continue
                seen.add(rid)
                rows.append(row)
    rows.sort(key=lambda row: float(row.get("ts") or 0))
    return rows


# ── статистика гейтов ──


def _token_line(info: dict) -> str:
    return f"{info['token']} — капа {dr.money(info['mc'])} · оценка {info['score']}/125"


def evaluate(rows, since_ts: float, until_ts: float) -> dict:
    """Применить текущие гейты фильтра к записям окна (ничего не меняет)."""
    window = [row for row in rows if since_ts <= float(row.get("ts") or 0) <= until_ts]
    cabal = dr.cabal_addresses(rows, now=until_ts)

    stats = {
        "window_start": since_ts,
        "window_end": until_ts,
        "window_hours": round((until_ts - since_ts) / 3600, 2),
        "types": dict(Counter(str(row.get("type") or "?") for row in window)),
        "verdicts": 0,
        "scored": 0,
        "unscored": 0,
        "passed": 0,
        "blocked": 0,
        "gate_hits": Counter(),
        "gate_only": Counter(),
        "sm_only": [],
        "passed_tokens": [],
        "thresholds": {
            "mc_min_usd": dr.MC_MIN_USD,
            "score_min": dr.SCORE_MIN,
            "top10_max_pct": dr.TOP10_MAX_PCT,
        },
    }
    for row in window:
        if row.get("type") != "verdict":
            continue
        stats["verdicts"] += 1
        info = dr.parse_token_info(row)
        if info is None:
            stats["unscored"] += 1
            continue
        stats["scored"] += 1
        blockers = dr.potential_blockers(info, cabal)
        if not blockers:
            stats["passed"] += 1
            stats["passed_tokens"].append(_token_line(info))
            continue
        stats["blocked"] += 1
        keys = []
        for blocker in blockers:
            key = gate_of(blocker)
            if key not in keys:
                keys.append(key)
        for key in keys:
            stats["gate_hits"][key] += 1
        if len(keys) == 1:
            stats["gate_only"][keys[0]] += 1
        if keys == ["sm"]:
            stats["sm_only"].append(_token_line(info))

    stats["sm_bonus_passed"] = stats["passed"] + len(stats["sm_only"])
    stats["gate_hits"] = dict(stats["gate_hits"])
    stats["gate_only"] = dict(stats["gate_only"])
    return stats


# ── человеческий отчёт ──


def _fmt_moment(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%d.%m %H:%M")


def render(stats: dict, examples: int = 5) -> str:
    blocked = stats["blocked"]
    parts = [
        "📊 RAB9 · анализатор — гейты фильтра «нужные токены»",
        f"Окно: {_fmt_moment(stats['window_start'])} – {_fmt_moment(stats['window_end'])} UTC "
        f"({stats['window_hours']:g} ч)",
        f"Оценок в окне: {stats['scored']} · прошло фильтр: {stats['passed']} · отсеяно: {blocked}",
    ]
    types = stats["types"]
    parts.append(
        "Служебное в окне (в чат не идёт): "
        + ", ".join(
            f"{dr.TYPE_RU.get(key, key)} {types.get(key, 0)}"
            for key in ("alert", "reject", "digest")
        )
    )
    if stats["unscored"]:
        parts.append(f"Без оценки/капы в записи (не токен-кандидат): {stats['unscored']}")
    parts.append("")
    parts.append("Отсев по гейтам — задето токенов / отсеяно только этим гейтом:")
    ordered = sorted(
        stats["gate_hits"].items(),
        key=lambda item: (-item[1], item[0]),
    )
    for key, hits in ordered:
        parts.append(
            f"   • {gate_threshold_note(key)} — {hits} / {stats['gate_only'].get(key, 0)}"
        )
    if not ordered:
        parts.append("   • отсева нет")

    parts.append("")
    parts.append("Гейт «умные деньги: набор» (ключевой вопрос владельца):")
    sm_only = stats["sm_only"]
    parts.append(
        f"   • только им отсеяно: {len(sm_only)} из {blocked}"
        if blocked
        else "   • отсева нет"
    )
    parts.append(
        f"   • если набор сделать бонусом к оценке (не обязательным) — прошло бы "
        f"{stats['sm_bonus_passed']} вместо {stats['passed']}"
    )
    parts.append(
        "   • прочие гейты остаются: часть отсеянных по капе/оценке бонус не вытянет"
        " (бонусные баллы в расчёте не учитывались)"
    )
    if sm_only:
        parts.append("   • снят только SM-гейт у:")
        for line in sm_only[:examples]:
            parts.append(f"      – {line}")

    parts.append("")
    if stats["passed_tokens"]:
        parts.append("Прошли фильтр: " + "; ".join(stats["passed_tokens"][:examples]))
    else:
        parts.append("Прошли фильтр: нет — за окно ни один токен не прошёл все гейты")
    parts.append("Гейты не трогаем (решение владельца 24.11), ждём 3 суток.")
    return "\n".join(parts)


# ── запуск ──


def _parse_moment(value: str) -> float:
    text = value.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        moment = datetime.strptime(text, "%Y-%m-%dT%H:%M")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="read-only сводка гейтов фильтра доставки")
    parser.add_argument("--hours", type=float, default=72.0, help="окно в часах назад от --until")
    parser.add_argument("--since", default=None, help="начало окна, ISO UTC")
    parser.add_argument("--until", default=None, help="конец окна, ISO UTC (по умолчанию сейчас)")
    parser.add_argument("--out-dir", default=None, help="каталог sink (по умолчанию data/analyses_out)")
    parser.add_argument("--json", action="store_true", help="машинный вывод")
    parser.add_argument("--examples", type=int, default=5, help="сколько токенов показывать примерами")
    args = parser.parse_args(argv)

    until_ts = _parse_moment(args.until) if args.until else datetime.now(tz=timezone.utc).timestamp()
    since_ts = _parse_moment(args.since) if args.since else until_ts - args.hours * 3600
    if since_ts > until_ts:
        since_ts, until_ts = until_ts, since_ts

    out_dir = Path(args.out_dir) if args.out_dir else DEFAULT_OUT_DIR
    rows = load_rows(out_dir, since_ts)
    stats = evaluate(rows, since_ts, until_ts)

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=1))
    else:
        print(render(stats, examples=max(0, args.examples)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
