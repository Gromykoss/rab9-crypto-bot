#!/usr/bin/env python3
"""Тесты delivery-reader (scripts/delivery_reader.py, карточка t_eb994c6a, 24.11.2026).

Офлайн, без сети и без Telegram: проверяем контракт доставки из sink.
1) в чат уходит только токен с потенциалом роста; digest/alert/reject — молча, offset двигается;
2) «не чаще раза в час» — второй токен в том же часу не летит, --force пробивает;
3) ротация sink (offset-ид исчез) не ломает ридера, хвост берётся, история не заливается;
4) битая строка jsonl пропускается;
5) пустой sink = пустой stdout (крон молчит);
6) dry-run не меняет offset-файл;
7) размер одного сообщения ограничен (окно ≤ MAX_RECORDS_PER_MSG), остаток остаётся в очереди;
8) фильтр «потенциал роста» (владелец 24.11): капа < $5 млн, оценка < 85/125, AVOID,
   ончейн-риск 🔴, нет набора умных денег, топ-10 > 30%, кабал-алерт за сутки — архив;
9) карточка читается человеком: капа расшифрована, признаки роста перечислены, вердикт СЛЕДИТЬ;
10) перевод сигналов кабала и сводки окна по-русски (оставлены для возврата алертов в чат).
"""

import importlib.util
import json
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dr = _load("delivery_reader", ROOT / "scripts" / "delivery_reader.py")


def _verdict_text(
    token="TEST",
    mc="$6.0M",
    score=91,
    tier="ХОРОШИЙ",
    risk="🟢",
    sm="набор",
    top10=20,
    holders=800,
    avoid=False,
    pp="1.3",
) -> str:
    """Реалистичное тело verdict-записи (как его пишет анализатор)."""
    text = (
        f"🔍 {token} | MC: {mc} | DEX: pumpswap\n"
        f"📊 Оценка {score}/125 {tier} | риск={risk} GMGN=8/15 поток={'набор' if sm == 'набор' else 'нет'}\n"
        f"🧬 GMGN: держатели={holders} топ10={top10}% ловушка=нет отказ_mint/freeze=да/да лок=да\n"
        f"📡 Умные деньги: {sm} | SM 18 сделок (12пок/6прод) KOL 35\n\n"
        "📝 Что это: мемкоин на pumpswap.\n\n"
        "Почему смотреть: покупок больше продаж.\n\n"
        "Риски: капитализация низкая.\n\n"
        "Что делать: Ждать сигналов набора позиции.\n"
        f"📈 Кап: {mc} | Пок/Прод: {pp}x | Оценка: {score}/115\n\n"
    )
    text += "🎯 ⚠️ AVOID (RugCheck: HIGH RISK)\n" if avoid else "🎯 ⏳ WAIT | ❓ НЕИЗВЕСТНО\n"
    text += f"🔗 https://dexscreener.com/solana/{token}addr\n"
    return text


def _row(rid: str, rtype: str, text: str, ts=None, address: str = "Addr111", token: str = "TEST") -> dict:
    return {
        "id": rid,
        "ts": ts if ts is not None else time.time(),
        "type": rtype,
        "token": token,
        "address": address,
        "text": text,
    }


def _good(rid: str, token="Satoshi", mc="$6.0M", score=91, address="Addr111", ts=None) -> dict:
    return _row(rid, "verdict", _verdict_text(token=token, mc=mc, score=score), ts=ts, address=address, token=token)


def _write_sink(path: Path, rows, broken_line: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            if broken_line and row.get("type") == "digest":
                fh.write("{это не json}\n")
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(tmp_path, sink_rows, state=None, extra=(), broken=False):
    sink = tmp_path / "analyses.jsonl"
    state_path = tmp_path / "delivery_offset.json"
    _write_sink(sink, sink_rows, broken_line=broken)
    if state is not None:
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return dr.main(["--sink", str(sink), "--state", str(state_path), *extra]), sink, state_path


# ── 1. что вообще попадает в чат ──


def test_promising_token_is_delivered(tmp_path, capsys):
    rc, _sink, state_path = _run(tmp_path, [_good("v1", token="Satoshi")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "RAB9 · анализатор — токены с потенциалом роста" in out
    assert "Satoshi — капа $6,0 млн · оценка 91/125" in out
    assert "умные деньги набирают (18 сделок (12 покупок / 6 продаж))" in out
    assert "ончейн-риск низкий" in out
    assert "топ-10 20%" in out
    assert "Анализатор советует: Ждать сигналов набора позиции." in out
    assert "Вердикт: СЛЕДИТЬ" in out
    assert "прошло фильтр: 1" in out
    assert _state(state_path)["last_delivered_id"] == "v1"


def test_digest_and_alert_are_not_delivered(tmp_path, capsys):
    rows = [
        _row("d1", "digest", "Дайджест окна 4.0ч: 3 записей (verdict=1, reject=0, alert=1)."),
        _row("a1", "alert", "⚠️ КАБАЛ: coin ($coin)\nФаза: CABAL_EXPLOSION | Риск: high"),
        _row("r1", "reject", "DROP: scam"),
    ]
    rc, _sink, state_path = _run(tmp_path, rows)
    assert rc == 0
    assert capsys.readouterr().out == ""                     # в чат ничего: только мусор в очереди
    assert _state(state_path)["last_delivered_id"] == "r1"   # offset прошёл молча


def test_low_cap_token_archived(tmp_path, capsys):
    # владелец 24.11: «не нужно присылать бесперспективные токены» + порог MC ≥ $500 тыс.
    rc, _sink, state_path = _run(tmp_path, [_good("v1", token="DUVAL", mc="$102K", score=90)])
    assert rc == 0
    assert capsys.readouterr().out == ""
    assert _state(state_path)["last_delivered_id"] == "v1"


def test_cap_threshold_is_500k(tmp_path, capsys):
    """Порог владельца: $5 млн → $500 тыс. (24.11, его реплика «согласен, опустить до 500 тыс.»)."""
    assert dr.MC_MIN_USD == 500_000
    assert dr.money(dr.MC_MIN_USD) == "$500 тыс."
    rc, _sink, _state_path = _run(tmp_path, [_good("v1", token="OKC", mc="$520K")])
    assert rc == 0
    assert "OKC" in capsys.readouterr().out                  # 520 тыс. — уже проходит
    rc, _sink, _state_path = _run(tmp_path, [_good("v2", token="LOWC", mc="$480K")])
    assert rc == 0
    assert capsys.readouterr().out == ""                     # 480 тыс. — ещё нет


def test_big_cap_but_avoid_and_red_risk_archived(tmp_path, capsys):
    # GOTF/UOF/UGOS из sink 24.11: капа выше порога, но анализатор сам says AVOID
    row = _row("v1", "verdict", _verdict_text(token="GOTF", mc="$161.5M", score=75, tier="РИСКОВАННЫЙ", risk="🔴", sm="нет", top10=1, avoid=True), token="GOTF")
    rc, _sink, state_path = _run(tmp_path, [row])
    assert rc == 0
    assert capsys.readouterr().out == ""
    assert _state(state_path)["last_delivered_id"] == "v1"


def test_concentrated_top10_archived(tmp_path, capsys):
    rc, _sink, _state_path = _run(tmp_path, [_good("v1", token="UGOS", mc="$154.9M", score=91, )])
    assert rc == 0
    assert capsys.readouterr().out != ""                      # база проходит
    rc, _sink, _state_path = _run(
        tmp_path,
        [_row("v1", "verdict", _verdict_text(token="UGOS", mc="$154.9M", score=91, top10=100))],
    )
    assert rc == 0
    assert capsys.readouterr().out == ""                      # топ-10 100% — дамп-риск, в архив


def test_cabal_alert_blocks_token(tmp_path, capsys):
    rows = [
        _good("v1", token="DUVAL", mc="$6.0M"),
        _row("a1", "alert", "⚠️ КАБАЛ: The White Bull ($DUVAL)\nФаза: CABAL_EXPLOSION | Риск: high", address="Addr111"),
    ]
    rc, _sink, _state_path = _run(tmp_path, rows)
    assert rc == 0
    assert capsys.readouterr().out == ""                      # кабал-алерт за сутки отменяет «потенциал»


def test_old_cabal_alert_does_not_block_forever(tmp_path, capsys):
    rows = [
        _good("v1", token="DUVAL", mc="$6.0M"),
        _row("a1", "alert", "⚠️ КАБАЛ: X ($X)\nФаза: CABAL_EXPLOSION", ts=time.time() - 3 * 86400, address="Addr111"),
    ]
    rc, _sink, _state_path = _run(tmp_path, rows)
    assert rc == 0
    assert "DUVAL" in capsys.readouterr().out                 # алерт старше суток уже не блокирует


# ── 2. контракт доставки (offset/интервал/ротация) ──


def test_hourly_gate_blocks_second_message(tmp_path, capsys):
    rc, sink, state_path = _run(tmp_path, [_good("v1", token="FIRST")])
    assert rc == 0
    assert "FIRST" in capsys.readouterr().out
    assert _state(state_path)["last_delivered_id"] == "v1"

    _write_sink(sink, [_good("v1", token="FIRST"), _good("v2", token="SECOND")])
    assert dr.main(["--sink", str(sink), "--state", str(state_path)]) == 0
    assert capsys.readouterr().out == ""                      # в том же часу сообщения нет
    assert _state(state_path)["last_delivered_id"] == "v1"    # offset не сдвинулся

    assert dr.main(["--sink", str(sink), "--state", str(state_path), "--force"]) == 0
    out = capsys.readouterr().out
    assert "SECOND" in out
    assert _state(state_path)["last_delivered_id"] == "v2"


def test_rotation_offset_lost_keeps_working(tmp_path, capsys):
    state = {"last_delivered_id": "исчез-после-ротации", "last_delivered_ts": 1.0}
    rc, _sink, state_path = _run(tmp_path, [_good("n1", token="AFTER")], state=state, extra=["--force"])
    assert rc == 0
    assert "AFTER" in capsys.readouterr().out
    assert _state(state_path)["last_delivered_id"] == "n1"


def test_broken_jsonl_line_skipped(tmp_path, capsys):
    rc, _sink, state_path = _run(
        tmp_path,
        [_row("d1", "digest", "ЦЕЛЫЙ-ДАЙДЖЕСТ"), _good("v1", token="HOLDER")],
        broken=True,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "HOLDER" in out and "ЦЕЛЫЙ-ДАЙДЖЕСТ" not in out
    assert _state(state_path)["last_delivered_id"] == "v1"


def test_empty_sink_is_silent(tmp_path, capsys):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    state_path = tmp_path / "state.json"
    assert dr.main(["--sink", str(empty), "--state", str(state_path)]) == 0
    assert capsys.readouterr().out == ""


def test_dry_run_does_not_touch_state(tmp_path, capsys):
    rc, _sink, state_path = _run(tmp_path, [_good("v1", token="DRY")], extra=["--dry-run"])
    assert rc == 0
    assert "DRY" in capsys.readouterr().out
    assert not state_path.exists()


def test_message_window_is_capped(tmp_path, capsys):
    rows = [_good(f"v{i}", token=f"TOK{i}") for i in range(1, dr.MAX_RECORDS_PER_MSG + 6)]
    rc, sink, state_path = _run(tmp_path, rows, extra=["--force"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TOK1 " in out or "TOK1 —" in out
    assert f"TOK{dr.MAX_RECORDS_PER_MSG + 5} " not in out    # хвост остался в очереди
    assert _state(state_path)["last_delivered_id"] == f"v{dr.MAX_RECORDS_PER_MSG}"

    assert dr.main(["--sink", str(sink), "--state", str(state_path), "--force"]) == 0
    assert f"TOK{dr.MAX_RECORDS_PER_MSG + 5}" in capsys.readouterr().out


# ── 3. вспомогательное (разбор/формат; алерты в чат сейчас не идут, но код жив) ──


def test_money_decoded():
    assert dr.money(161_500_000) == "$161,5 млн"
    assert dr.money(16_600_000) == "$16,6 млн"
    assert dr.money(102_000) == "$102 тыс."
    assert dr.money(1_400) == "$1 тыс."
    assert dr.money(None) == "?"


def test_parse_token_info_fields():
    info = dr.parse_token_info(_row("v1", "verdict", _verdict_text(token="JENSEN", mc="$49K", score=82, tier="РИСКОВАННЫЙ"), token="JENSEN"))
    assert info["token"] == "JENSEN"
    assert info["score"] == 82 and info["mc"] == 49_000
    assert info["risk_green"] is True and info["sm_accumulating"] is True
    assert info["top10"] == 20 and info["holders"] == 800
    assert info["buy_sell"] == "1.3"
    assert info["avoid"] is False
    assert dr.parse_token_info(_row("x", "verdict", "не оценка")) is None


def test_cabal_signals_translated():
    assert dr._ru_signal("3+ pairs in 24h (30 total, 2 DEXes)") == "за сутки создано ≥3 новых пула: всего 30, площадок 2"
    assert dr._ru_signal("Meteora preference: 2 DLMM pairs (cabal DEX)") == "предпочтение Meteora: 2 DLMM-пулов (любимая площадка кабалов)"
    assert dr._ru_signal("Multi-DEX: meteora, pumpswap") == "торгуется сразу на нескольких площадках: meteora, pumpswap"
    assert dr._ru_signal("Massive pair explosion: 11 pairs") == "массовое размножение пулов: 11"
    assert dr._ru_signal("Volume > MC: 2.7x (pump in progress)") == "объём за сутки в 2.7× больше капитализации — идёт разгон"
    assert dr._ru_signal("Price +149% in 24h") == "цена за сутки: +149%"
    assert dr._ru_signal("Неизвестный сигнал") == "Неизвестный сигнал"


def test_digest_meta_rendered_in_russian():
    row = {
        "id": "d1",
        "ts": time.time(),
        "type": "digest",
        "text": "Дайджест окна 4.0ч: 3 записей (verdict=1, reject=1, alert=1).",
        "digest_meta": {
            "window_start": 1000.0,
            "window_end": 1000.0 + 4 * 3600,
            "counts": {"verdict": 1, "reject": 1, "alert": 1},
            "entries": [
                {"type": "alert", "token": "Satoshi"},
                {"type": "reject", "token": "?"},
                {"type": "verdict", "token": "JENSEN"},
            ],
        },
    }
    text = dr._render_digest(row)
    assert "Сводка за 4 ч" in text
    assert "оценка 1, отказ 1, алерт 1" in text
    assert "Satoshi (алерт)" in text and "JENSEN (оценка)" in text
