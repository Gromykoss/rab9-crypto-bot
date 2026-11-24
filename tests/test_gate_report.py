#!/usr/bin/env python3
"""Тесты gate-report (scripts/gate_report.py, 24.11.2026).

Read-only сводка гейтов фильтра доставки для решения владельца 24.11
(«ЖДЁМ 3 дня, гейты не трогать, 27.11 — сводка по гейтам»). Офлайн, без сети.

1) каждый блокер живого фильтра распознаётся своим гейтом (нет «прочих»);
2) считаются: задето гейтом, отсеяно только этим гейтом, прошло фильтр;
3) отдельно считается вариант «умные деньги = бонус к оценке»;
4) ротированные файлы sink читаются вместе с текущим, дубли по id не двоятся;
5) окно режется по ts, запись без оценки/капы не считается кандидатом;
6) отчёт — русский текст с числами по гейтам и вердиктом «гейты не трогаем»;
7) отчёт ничего не пишет в каталог sink.
"""

import importlib.util
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gr = _load("gate_report", ROOT / "scripts" / "gate_report.py")
dr = _load("delivery_reader_for_gate_report", ROOT / "scripts" / "delivery_reader.py")


def _verdict_text(
    token="TEST",
    mc="$6.0M",
    score=91,
    risk="🟢",
    sm="набор",
    top10=20,
    holders=800,
    avoid=False,
    pp="1.3",
) -> str:
    """Тело verdict-записи как его пишет анализатор (та же форма, что в тестах delivery-reader)."""
    text = (
        f"🔍 {token} | MC: {mc} | DEX: pumpswap\n"
        f"📊 Оценка {score}/125 ХОРОШИЙ | риск={risk} GMGN=8/15 поток={'набор' if sm == 'набор' else 'нет'}\n"
        f"🧬 GMGN: держатели={holders} топ10={top10}% ловушка=нет отказ_mint/freeze=да/да лок=да\n"
        f"📡 Умные деньги: {sm} | SM 18 сделок (12пок/6прод) KOL 35\n\n"
        "📝 Что это: мемкоин на pumpswap.\n\n"
        "Что делать: Ждать сигналов набора позиции.\n"
        f"📈 Кап: {mc} | Пок/Прод: {pp}x | Оценка: {score}/115\n\n"
    )
    text += "🎯 ⚠️ AVOID (RugCheck: HIGH RISK)\n" if avoid else "🎯 ⏳ WAIT | ❓ НЕИЗВЕСТНО\n"
    text += f"🔗 https://dexscreener.com/solana/{token}addr\n"
    return text


def _row(rid: str, rtype: str, text: str, ts, address="Addr111", token="TEST") -> dict:
    return {"id": rid, "ts": ts, "type": rtype, "token": token, "address": address, "text": text}


def _verdict(rid: str, token="Satoshi", mc="$6.0M", score=91, risk="🟢", sm="набор", top10=20,
             avoid=False, address="Addr111", ts=None) -> dict:
    return _row(
        rid,
        "verdict",
        _verdict_text(token=token, mc=mc, score=score, risk=risk, sm=sm, top10=top10, avoid=avoid),
        ts=ts if ts is not None else time.time(),
        address=address,
        token=token,
    )


def _sink(tmp_path: Path, name: str, rows) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


# ── 1. распознавание гейтов ──


def test_every_live_blocker_maps_to_its_gate():
    # худший кандидат: задет всеми гейтами сразу
    worst = {
        "token": "BAD",
        "address": "CabalAddr",
        "score": 40,
        "mc": 100_000.0,
        "risk_green": False,
        "sm_accumulating": False,
        "avoid": True,
        "top10": 55,
        "holders": 90,
        "sm_deals": "",
        "kol": None,
        "buy_sell": "",
        "action": "",
        "link": "",
    }
    blockers = dr.potential_blockers(worst, {"CabalAddr"})
    keys = {gr.gate_of(blocker) for blocker in blockers}
    assert keys == {"mc", "score", "avoid", "risk", "sm", "top10", "cabal"}
    assert gr.OTHER_KEY not in keys
    assert gr.gate_threshold_note("mc") == f"капа ниже {dr.money(dr.MC_MIN_USD)}"
    assert f"{dr.SCORE_MIN}/125" in gr.gate_threshold_note("score")


# ── 2–3. счёт гейтов и вариант «SM = бонус» ──


def test_counts_gates_and_sm_bonus_variant(tmp_path):
    now = time.time()
    rows = [
        _verdict("v1", token="Satoshi", mc="$6.0M", score=91, ts=now - 60),                 # прошёл
        _verdict("v2", token="Newbie", mc="$1.0M", score=90, sm="нет", ts=now - 120),       # только SM
        _verdict("v3", token="Tiny", mc="$100K", score=90, ts=now - 180),                   # капа
        _verdict("v4", token="Weak", mc="$1.0M", score=60, ts=now - 240),                   # оценка
        _verdict("v5", token="Whale", mc="$1.0M", score=90, sm="нет", top10=55, ts=now - 300),  # SM + топ-10
    ]
    _sink(tmp_path, "analyses.jsonl", rows)
    stats = gr.evaluate(gr.load_rows(tmp_path, now - 86400), now - 86400, now)

    assert stats["scored"] == 5
    assert stats["passed"] == 1
    assert stats["blocked"] == 4
    assert stats["gate_hits"]["sm"] == 2                 # Newbie, Whale
    assert stats["gate_only"]["sm"] == 1                 # только Newbie
    assert stats["gate_only"]["mc"] == 1
    assert stats["gate_only"]["score"] == 1
    assert stats["gate_hits"]["top10"] == 1
    assert stats["sm_only"] == ["Newbie — капа $1,0 млн · оценка 90/125"]
    assert stats["sm_bonus_passed"] == 2                 # прошёл + снятый только-SM
    assert stats["passed_tokens"] == ["Satoshi — капа $6,0 млн · оценка 91/125"]


def test_types_and_unscored_verdicts_counted(tmp_path):
    now = time.time()
    rows = [
        _row("d1", "digest", "Дайджест окна 4.0ч: 3 записей (verdict=1, reject=0, alert=1).", now - 30),
        _row("a1", "alert", "⚠️ КАБАЛ: coin ($coin)\nФаза: CABAL_EXPLOSION | Риск: high", now - 40,
             address="CoinAddr", token="coin"),
        _row("r1", "reject", "DROP: scam", now - 50),
        _row("v9", "verdict", "🔍 USDC | ручной разбор без оценки и капы", now - 60, token="USDC"),
        _verdict("v1", token="Satoshi", ts=now - 70),
    ]
    _sink(tmp_path, "analyses.jsonl", rows)
    stats = gr.evaluate(gr.load_rows(tmp_path, now - 86400), now - 86400, now)

    assert stats["types"] == {"digest": 1, "alert": 1, "reject": 1, "verdict": 2}
    assert stats["verdicts"] == 2
    assert stats["unscored"] == 1                        # разбор без оценки/капы — не кандидат
    assert stats["scored"] == 1 and stats["passed"] == 1


def test_cabal_alert_blocks_token(tmp_path):
    now = time.time()
    rows = [
        _row(
            "a1",
            "alert",
            "⚠️ КАБАЛ: coin ($coin)\nФаза: CABAL_EXPLOSION | Риск: high",
            now - 3600,
            address="PumpAddr",
            token="coin",
        ),
        _verdict("v1", token="coin", address="PumpAddr", ts=now - 60),
    ]
    _sink(tmp_path, "analyses.jsonl", rows)
    stats = gr.evaluate(gr.load_rows(tmp_path, now - 86400), now - 86400, now)

    assert stats["passed"] == 0
    assert stats["gate_only"]["cabal"] == 1
    assert stats["gate_hits"]["cabal"] == 1


# ── 4. ротированные файлы и дубли ──


def test_rotated_files_merged_and_deduped(tmp_path):
    now = time.time()
    old = time.time() - 3600 * 30
    _sink(tmp_path, "analyses.20261124T072418.jsonl", [_verdict("old1", token="Old", ts=old)])
    _sink(tmp_path, "analyses.jsonl", [_verdict("new1", token="New", ts=now - 60),
                                       _verdict("old1", token="Old", ts=old)])
    rows = gr.load_rows(tmp_path, now - 86400 * 3)
    stats = gr.evaluate(rows, now - 86400 * 3, now)

    assert [row["id"] for row in rows] == ["old1", "new1"]     # дубль не двоится, порядок по ts
    assert stats["scored"] == 2
    assert stats["passed"] == 2


def test_old_rotation_file_is_skipped(tmp_path):
    now = time.time()
    moment = now - 86400 * 20
    path = _sink(tmp_path, "analyses.20261101T000000.jsonl", [_verdict("ancient", ts=moment)])
    os.utime(path, (moment, moment))          # ротация случилась 20 суток назад
    assert gr.sink_files(tmp_path, now - 3600) == []
    assert gr.load_rows(tmp_path, now - 3600) == []


# ── 5. окно ──


def test_window_cuts_rows_by_ts(tmp_path):
    now = time.time()
    _sink(tmp_path, "analyses.jsonl", [
        _verdict("v_old", token="Old", ts=now - 3600 * 100),
        _verdict("v_new", token="New", ts=now - 60),
    ])
    stats = gr.evaluate(gr.load_rows(tmp_path, now - 86400 * 3), now - 3600 * 72, now)

    assert stats["scored"] == 1
    assert stats["passed_tokens"] == ["New — капа $6,0 млн · оценка 91/125"]


# ── 6. текстовый отчёт ──


def test_render_reports_gates_and_waits(tmp_path, capsys):
    now = time.time()
    _sink(tmp_path, "analyses.jsonl", [
        _verdict("v1", token="Satoshi", mc="$6.0M", score=91, ts=now - 60),
        _verdict("v2", token="Newbie", mc="$1.0M", score=90, sm="нет", ts=now - 120),
        _verdict("v3", token="Tiny", mc="$100K", score=90, ts=now - 180),
    ])
    rc = gr.main(["--out-dir", str(tmp_path), "--hours", "3"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "гейты фильтра «нужные токены»" in out
    assert "Оценок в окне: 3 · прошло фильтр: 1 · отсеяно: 2" in out
    assert "капа ниже $500 тыс. — 1 / 1" in out
    assert "умные деньги не набирают позицию — 1 / 1" in out
    assert "только им отсеяно: 1 из 2" in out
    assert "прошло бы 2 вместо 1" in out
    assert "Satoshi — капа $6,0 млн · оценка 91/125" in out
    assert "Гейты не трогаем (решение владельца 24.11)" in out


def test_json_mode_is_machine_readable(tmp_path, capsys):
    now = time.time()
    _sink(tmp_path, "analyses.jsonl", [_verdict("v1", token="Satoshi", ts=now - 60)])
    assert gr.main(["--out-dir", str(tmp_path), "--hours", "3", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scored"] == 1 and payload["passed"] == 1
    assert payload["thresholds"]["mc_min_usd"] == 500_000


# ── 7. read-only ──


def test_report_writes_nothing(tmp_path, capsys):
    now = time.time()
    _sink(tmp_path, "analyses.jsonl", [_verdict("v1", token="Satoshi", ts=now - 60)])
    before = sorted(path.name for path in tmp_path.iterdir())
    assert gr.main(["--out-dir", str(tmp_path), "--hours", "3"]) == 0
    capsys.readouterr()
    assert sorted(path.name for path in tmp_path.iterdir()) == before
