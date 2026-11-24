#!/usr/bin/env python3
"""Тесты delivery-reader (scripts/delivery_reader.py, карточка t_eb994c6a, 24.11.2026).

Офлайн, без сети и без Telegram: проверяем контракт доставки из sink.
1) digest уходит в чат один раз, повторной доставки нет (offset = id записи);
2) verdict/reject отдельными сообщениями не уходят, offset по ним двигается молча;
3) alert уходит, verdict — нет;
4) «не чаще раза в час» — второй digest в том же часу в чат не летит, --force пробивает;
5) ротация sink (offset-ид исчез) не ломает ридера, хвост берётся, история не заливается;
6) битая строка jsonl пропускается;
7) пустой sink = пустой stdout (крон молчит);
8) dry-run не меняет offset-файл;
9) размер одного сообщения ограничен (окно ≤ MAX_RECORDS_PER_MSG), остаток остаётся в очереди.
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


def _row(rid: str, rtype: str, text: str, ts=None) -> dict:
    return {
        "id": rid,
        "ts": ts if ts is not None else time.time(),
        "type": rtype,
        "token": "TEST",
        "address": "Addr111",
        "text": text,
    }


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


def test_digest_sent_once_and_offset_advances(tmp_path, capsys):
    rc, _sink, state_path = _run(
        tmp_path,
        [_row("v1", "verdict", "ВЕРДИКТ-ПОЛНЫЙ-ОТЧЁТ"), _row("d1", "digest", "ДАЙДЖЕСТ-ЗА-4-ЧАСА")],
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "ДАЙДЖЕСТ-ЗА-4-ЧАСА" in out
    assert "ВЕРДИКТ-ПОЛНЫЙ-ОТЧЁТ" not in out
    assert _state(state_path)["last_delivered_id"] == "d1"

    # повторный прогон по тому же файлу: состояние уже на d1
    rc_again = dr.main(
        ["--sink", str(tmp_path / "analyses.jsonl"), "--state", str(state_path)]
    )
    assert rc_again == 0
    assert capsys.readouterr().out == ""


def test_verdict_and_reject_only_is_silent(tmp_path, capsys):
    rc, _sink, state_path = _run(
        tmp_path,
        [_row("v1", "verdict", "ОТЧЁТ"), _row("r1", "reject", "DROP: scam")],
    )
    assert rc == 0
    assert capsys.readouterr().out == ""
    assert _state(state_path)["last_delivered_id"] == "r1"


def test_alert_goes_verdict_does_not(tmp_path, capsys):
    rc, _sink, _state_path = _run(
        tmp_path,
        [_row("v1", "verdict", "ОТЧЁТ-НЕ-СЛАТЬ"), _row("a1", "alert", "⚠️ КАБАЛ: 3+ pairs")],
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "⚠️ КАБАЛ: 3+ pairs" in out
    assert "ОТЧЁТ-НЕ-СЛАТЬ" not in out


def test_hourly_gate_blocks_second_message(tmp_path, capsys):
    rc, sink, state_path = _run(tmp_path, [_row("d1", "digest", "ПЕРВЫЙ-ДАЙДЖЕСТ")])
    assert rc == 0
    assert "ПЕРВЫЙ-ДАЙДЖЕСТ" in capsys.readouterr().out
    assert _state(state_path)["last_delivered_id"] == "d1"

    # в том же часу появился второй дайджест
    _write_sink(sink, [_row("d1", "digest", "ПЕРВЫЙ-ДАЙДЖЕСТ"), _row("d2", "digest", "ВТОРОЙ-ДАЙДЖЕСТ")])
    assert dr.main(["--sink", str(sink), "--state", str(state_path)]) == 0
    assert capsys.readouterr().out == ""                      # сообщения нет
    assert _state(state_path)["last_delivered_id"] == "d1"    # offset не сдвинулся, запись в очереди

    # --force пробивает интервал и отдаёт накопленное
    assert dr.main(["--sink", str(sink), "--state", str(state_path), "--force"]) == 0
    out = capsys.readouterr().out
    assert "ВТОРОЙ-ДАЙДЖЕСТ" in out
    assert _state(state_path)["last_delivered_id"] == "d2"


def test_rotation_offset_lost_keeps_working(tmp_path, capsys):
    state = {"last_delivered_id": "исчез-после-ротации", "last_delivered_ts": 1.0}
    rc, _sink, state_path = _run(
        tmp_path,
        [_row("n1", "digest", "ПОСЛЕ-РОТАЦИИ")],
        state=state,
        extra=["--force"],
    )
    assert rc == 0
    assert "ПОСЛЕ-РОТАЦИИ" in capsys.readouterr().out
    assert _state(state_path)["last_delivered_id"] == "n1"


def test_broken_jsonl_line_skipped(tmp_path, capsys):
    rc, _sink, state_path = _run(
        tmp_path,
        [_row("d1", "digest", "ЦЕЛЫЙ-ДАЙДЖЕСТ"), _row("v1", "verdict", "ХВОСТ")],
        broken=True,
    )
    assert rc == 0
    assert "ЦЕЛЫЙ-ДАЙДЖЕСТ" in capsys.readouterr().out
    assert _state(state_path)["last_delivered_id"] == "v1"


def test_empty_sink_is_silent(tmp_path, capsys):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    state_path = tmp_path / "state.json"
    assert dr.main(["--sink", str(empty), "--state", str(state_path)]) == 0
    assert capsys.readouterr().out == ""


def test_dry_run_does_not_touch_state(tmp_path, capsys):
    rc, _sink, state_path = _run(
        tmp_path, [_row("d1", "digest", "ДАЙДЖЕСТ")], extra=["--dry-run"]
    )
    assert rc == 0
    assert "ДАЙДЖЕСТ" in capsys.readouterr().out
    assert not state_path.exists()


def test_message_window_is_capped(tmp_path, capsys):
    rows = [_row(f"d{i}", "digest", f"ДАЙДЖЕСТ-{i}") for i in range(1, dr.MAX_RECORDS_PER_MSG + 6)]
    rc, sink, state_path = _run(tmp_path, rows, extra=["--force"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ДАЙДЖЕСТ-1" in out
    assert f"ДАЙДЖЕСТ-{dr.MAX_RECORDS_PER_MSG + 5}" not in out              # хвост остался в очереди
    assert _state(state_path)["last_delivered_id"] == f"d{dr.MAX_RECORDS_PER_MSG}"

    # следующий прогон (интервал истёк бы, поэтому --force) доносит остаток
    assert dr.main(["--sink", str(sink), "--state", str(state_path), "--force"]) == 0
    assert f"ДАЙДЖЕСТ-{dr.MAX_RECORDS_PER_MSG + 5}" in capsys.readouterr().out
