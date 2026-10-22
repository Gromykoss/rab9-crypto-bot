"""Import-guard (D-A5) + v1.2 контракты standalone-analyzer."""
import asyncio
import json
import sys
from unittest import mock

import pytest

sys.path.insert(0, "/home/hermes-workspace/rab9")


def test_no_telegram_in_analyzer_modules():
    """GWT «демонтаж не ломает пайплайн»: telegram не импортируется."""
    import analyzer_main  # noqa: F401
    import msf_http  # noqa: F401
    import sink  # noqa: F401

    assert not any(m.startswith("telegram") for m in sys.modules), "telegram утёк в analyzer"


def test_import_guard_grep(tmp_path):
    """grep-guard: исходники ядра не содержат telegram-импортов."""
    for f in ("analyzer_main.py", "sink.py", "msf_http.py"):
        src = open(f"/home/hermes-workspace/rab9/{f}").read()
        assert "from telegram" not in src and "import telegram" not in src, f


def test_cascade_does_not_write_dedup_key(tmp_path, monkeypatch):
    """N1 (v1.2): каскад T0 не пишет ключ дедупа; ключ — только на ANALYZED."""
    import analyzer_main as am
    from unittest.mock import AsyncMock, Mock

    monkeypatch.setattr(am, "T0_QUEUE", tmp_path / "t0_queue.jsonl")
    monkeypatch.setattr(am, "ANALYSIS_QUEUE", tmp_path / "analysis_queue.jsonl")
    monkeypatch.setattr(am, "_extract_baseline", lambda a: {"price_usd": "0.001", "liquidity_usd": 20000})
    import loop_memory
    import msf_dedupe
    dedup_calls = []
    monkeypatch.setattr(
        loop_memory,
        "record_analysis",
        lambda *a, **k: dedup_calls.append(a) or {"duplicate": False, "duplicates": 0},
    )
    monkeypatch.setattr(
        msf_dedupe,
        "check_dedupe",
        lambda *a, **k: dedup_calls.append(("check_dedupe",)) or None,
    )

    asyncio.run(am.t0_enroll("4EMfevH3bDfnThB8EeNfF9KPiSD9YhEvgiFtUYFaWdEr"))
    assert dedup_calls == [], "каскад T0 не имеет права писать/читать дедуп-ключ (v1.2)"


def test_rate_gate_on_transition(monkeypatch, tmp_path):
    """N2: rate gate на переходе QUEUED→ANALYZED — из очереди уходит лучший."""
    import analyzer_main as am
    from unittest.mock import AsyncMock, Mock

    q = tmp_path / "analysis_queue.jsonl"
    recs = [
        {"address": "4EMfevH3bDfnThB8EeNfF9KPiSD9YhEvgiFtUYFaWdEr", "ts": 1, "priority": 100},
        {"address": "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2", "ts": 2, "priority": 5000},
    ]
    q.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    monkeypatch.setattr(am, "ANALYSIS_QUEUE", q)
    monkeypatch.setattr(am, "RATE_CAP_H", 15)
    monkeypatch.setattr(am, "RATE_LOG", tmp_path / "analysis_rate.jsonl")

    sink = Mock()
    sink.write = AsyncMock(return_value="x")
    sink.read_new = Mock(return_value=[])
    monkeypatch.setattr(am, "_is_kabal", AsyncMock(return_value=False))
    run_mock = AsyncMock(return_value="sent")
    monkeypatch.setattr(am, "send_msf_pairresolve", run_mock)

    asyncio.run(am.rate_gate(sink))
    left = am._load(q)
    assert len(left) == 1
    assert "4EMfevH3bDfnThB8EeNfF9KPiSD9YhEvgiFtUYFaWdEr" in left[0]  # остался слабый; лучший (5000) ушёл в ANALYZED
    assert run_mock.await_args.args[1].startswith("5UUH9")


def test_sink_baseline_and_manual(tmp_path):
    """v1.2: verdict-запись несёт baseline + manual флаг; type=manual не существует."""
    import sink as sink_mod

    monkeypatch_dir = tmp_path / "analyses_out"
    s = sink_mod.Sink(out_dir=monkeypatch_dir)
    s.jsonl = monkeypatch_dir / "analyses.jsonl"
    asyncio.run(s.write("verdict", "4EMfevH3bDfnThB8EeNfF9KPiSD9YhEvgiFtUYFaWdEr", "T", "текст", manual=True, baseline={"price_usd": "0.001", "liquidity_usd": 9000}))
    rec = json.loads(s.jsonl.read_text().strip())
    assert rec["manual"] is True
    assert rec["baseline"]["price_usd"] == "0.001"
    assert rec["type"] == "verdict"  # type=manual упразднён (v1.2)
