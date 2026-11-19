"""GWT-тесты FROZEN-спеки analysis-filters v1.3.

Герметичность: сеть/время/внешние API замоканы, все пути состояния — tmp_path.
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]  # корень репо: локально и в CI (не хардкод пути)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from operators.operator_social_weight import classify_negative, _post_negative

NOW = 1_800_000_000.0  # фиксированное «сейчас» (никакого реального времени)
ADDR_A = "4EMfevH3bDfnThB8EeNfF9KPiSD9YhEvgiFtUYFaWdEr"
ADDR_B = "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"
ADDR_K = "CGEDT9QZDvvH5GmVkWJH2BXiMJqMJySC9ihWyr7Spump"


class _StopLoop(BaseException):
    """Останавливает бесконечный while-loop воркера (BaseException — не глушится except Exception)."""


def _paths(monkeypatch, tmp_path):
    """Все персистентные пути домена → tmp_path (реальный data/ не трогаем)."""
    import importlib

    import analyzer_main as am
    watched = ("analyzer_main", "msf_http", "msf_analysis", "config", "operators")
    foreign_loaded = any(
        module is not None
        and getattr(module, "__file__", None)
        and REPO_ROOT not in Path(module.__file__).resolve().parents
        for name, module in sys.modules.items()
        if name in watched or name.startswith("operators.")
    )
    if REPO_ROOT not in Path(am.__file__).resolve().parents or foreign_loaded:
        for module_name in list(sys.modules):
            if module_name in watched or module_name.startswith("operators."):
                del sys.modules[module_name]
        previous_path = list(sys.path)
        try:
            sys.path[:] = [p for p in sys.path if p != str(REPO_ROOT)]
            sys.path.insert(0, str(REPO_ROOT))
            am = importlib.import_module("analyzer_main")
        finally:
            sys.path[:] = previous_path

    monkeypatch.setattr(am, "T0_QUEUE", tmp_path / "t0_queue.jsonl")
    monkeypatch.setattr(am, "ANALYSIS_QUEUE", tmp_path / "analysis_queue.jsonl")
    monkeypatch.setattr(am, "OUTCOMES", tmp_path / "verdict_outcomes.jsonl")
    monkeypatch.setattr(am, "RATE_LOG", tmp_path / "analysis_rate.jsonl")
    monkeypatch.setattr(am, "DIGEST_CURSOR", tmp_path / "analyses_out" / "digest_cursor.json")
    return am


def _freeze_time(monkeypatch, now=NOW):
    import analyzer_main as am

    monkeypatch.setattr(am.time, "time", lambda: now)


def _stop_loop(monkeypatch, sleeps=1):
    """Подменяет asyncio.sleep: первые N вызовов — мгновенно, дальше — стоп-сигнал."""
    import analyzer_main as am

    state = {"n": 0}

    async def _sleep(_delay):
        state["n"] += 1
        if state["n"] > sleeps:
            raise _StopLoop()

    monkeypatch.setattr(am.asyncio, "sleep", _sleep)


def _mock_sink():
    from unittest.mock import AsyncMock, Mock

    s = Mock()
    s.write = AsyncMock(return_value="id-1")
    s.read_new = Mock(return_value=[])
    s.read_new_from = Mock(return_value=([], 0))
    return s


def _lines(path):
    if not path.exists():
        return []
    return [l.strip() for l in path.read_text().splitlines() if l.strip()]


def _jsonl(path):
    return [json.loads(l) for l in _lines(path)]


# ── 1. t0-cascade ──────────────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.t0_survives_recheck")
def test_t0_survives_recheck_queued_for_full_analysis(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    am = _paths(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    monkeypatch.setattr(am, "T0_INTERVAL_MIN", 20)
    # GIVEN мигрант на t=0 (записан в персистентную очередь перепроверки)
    am.T0_QUEUE.write_text(
        json.dumps({"address": ADDR_A, "ts": NOW - (20 * 60 + 60), "baseline": {"liquidity_usd": 1500}}) + "\n"
    )
    # WHEN на перепроверке ликвидность на месте
    monkeypatch.setattr(am, "_extract_baseline", lambda a: {"price_usd": "0.01", "liquidity_usd": 24000})
    monkeypatch.setattr(am, "_is_kabal", AsyncMock(return_value=False))
    sink = _mock_sink()

    asyncio.run(am.t0_tick(sink))

    # THEN токен поставлен в очередь полного анализа, из t0-очереди ушёл
    queued = _jsonl(am.ANALYSIS_QUEUE)
    assert [r["address"] for r in queued] == [ADDR_A]
    assert queued[0]["priority"] == 24000.0
    assert _lines(am.T0_QUEUE) == []
    sink.write.assert_not_awaited()


# ── 2. t0-cascade ──────────────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.t0_dead_before_recheck")
def test_t0_dead_before_recheck_no_analysis_digest_line(tmp_path, monkeypatch):
    import sink as sink_mod

    am = _paths(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    monkeypatch.setattr(am, "T0_INTERVAL_MIN", 20)
    am.T0_QUEUE.write_text(json.dumps({"address": ADDR_A, "ts": NOW - 3600}) + "\n")
    # WHEN на перепроверке пул пуст (ликвидности нет)
    monkeypatch.setattr(am, "_extract_baseline", lambda a: {})

    s = sink_mod.Sink(out_dir=tmp_path / "analyses_out")
    asyncio.run(am.t0_tick(s))

    # THEN полный анализ не запускается, из очередей токен удалён
    assert _lines(am.ANALYSIS_QUEUE) == []
    assert _lines(am.T0_QUEUE) == []
    recs = _jsonl(s.jsonl)
    assert [r["type"] for r in recs] == ["reject"]
    assert recs[0]["address"] == ADDR_A and "t0-каскад" in recs[0]["text"]

    # THEN факт уходит СТРОКОЙ в дайджест (не отдельным сообщением)
    monkeypatch.setattr(am, "DIGEST_THRESHOLD", 1)
    _stop_loop(monkeypatch, sleeps=1)
    with pytest.raises(_StopLoop):
        asyncio.run(am.digest_timer(s))

    digest = [r for r in _jsonl(s.jsonl) if r["type"] == "digest"]
    assert len(digest) == 1
    assert digest[0]["digest_meta"]["counts"]["reject"] == 1
    assert any(e["address"] == ADDR_A for e in digest[0]["digest_meta"]["entries"])


# ── 3. t0-cascade ──────────────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.t0_queue_survives_restart")
def test_t0_queue_survives_restart(tmp_path, monkeypatch):
    import importlib
    from unittest.mock import AsyncMock

    am = _paths(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    monkeypatch.setattr(am, "_extract_baseline", lambda a: {"price_usd": "0.01", "liquidity_usd": 1200})

    # GIVEN непустая очередь перепроверки
    asyncio.run(am.t0_enroll(ADDR_A))
    asyncio.run(am.t0_enroll(ADDR_B))
    assert [r["address"] for r in _jsonl(am.T0_QUEUE)] == [ADDR_A, ADDR_B]

    # WHEN процесс перезапущен (модуль переинициализирован — in-memory состояния нет)
    am = importlib.reload(am)
    monkeypatch.setattr(am, "T0_QUEUE", tmp_path / "t0_queue.jsonl")
    monkeypatch.setattr(am, "ANALYSIS_QUEUE", tmp_path / "analysis_queue.jsonl")
    _freeze_time(monkeypatch)

    # THEN очередь восстановлена из персистентного хранилища
    restored = am._load(am.T0_QUEUE)
    assert len(restored) == 2
    assert ADDR_A in restored[0] and ADDR_B in restored[1]

    # и восстановленная очередь работоспособна: t0_tick берёт её прямо из файла
    monkeypatch.setattr(am, "T0_INTERVAL_MIN", 0)
    monkeypatch.setattr(am, "_extract_baseline", lambda a: {"price_usd": "0.02", "liquidity_usd": 9000})
    monkeypatch.setattr(am, "_is_kabal", AsyncMock(return_value=False))
    asyncio.run(am.t0_tick(_mock_sink()))
    assert sorted(r["address"] for r in _jsonl(am.ANALYSIS_QUEUE)) == sorted([ADDR_A, ADDR_B])


# ── 4. migrant-risk-profile ───────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.supply_concentration_flag")
def test_supply_concentration_flag_fraction_and_percent():
    import importlib
    import inspect
    existing = sys.modules.get("msf_analysis")
    if existing is not None and REPO_ROOT not in Path(existing.__file__).resolve().parents:
        del sys.modules["msf_analysis"]
    previous_path = list(sys.path)
    try:
        sys.path[:] = [p for p in sys.path if p != str(REPO_ROOT)]
        sys.path.insert(0, str(REPO_ROOT))
        msf_analysis = importlib.import_module("msf_analysis")
    finally:
        sys.path[:] = previous_path
    from operators import concentration_flag

    # GMGN документирован как 0..100: 1.0 означает 1%, а не fraction=100%.
    assert concentration_flag(1.0, 50, source="gmgn_percent") == ""
    assert "61.0%" in concentration_flag(61, 50, source="gmgn_percent")
    # Эквивалент production verdict-wiring: флаг добавляется к итоговому summary.
    verdict = msf_analysis._apply_summary_risk_flags("⚠️ AVOID (RugCheck: HIGH RISK)", {"top10_pct": 61})
    assert "RugCheck: HIGH RISK" in verdict and "CONCENTRATION" in verdict
    # Удаление вызова из build_compact_analysis_text обязано ломать этот тест.
    source = inspect.getsource(msf_analysis.build_compact_analysis_text)
    assert "_apply_summary_risk_flags(verdict, security_hints," in source


def _negative_radar_payload():
    return {
        "ok": True,
        "query": "test",
        "posts": [
            "@alice (100): obvious scam rug",
            "@bob (200): honeypot drain stay away",
        ],
        "post_records": [
            {"username": "alice", "text": "obvious scam rug"},
            {"username": "bob", "text": "honeypot drain stay away"},
        ],
        "count": 2,
        "spam_detected": 0,
    }


def _radar_cache_path(monkeypatch, tmp_path):
    p = tmp_path / "radar_x_per_token.json"
    monkeypatch.setenv("RADAR_X_CACHE_PATH", str(p))
    return p


def _cacheable_radar(posts=None, **extra):
    base = {
        "ok": True,
        "cacheable": True,
        "api_called": True,
        "query": "t",
        "posts": [],
        "post_records": posts or [],
        "count": len(posts or []),
        "spam_detected": 0,
    }
    base.update(extra)
    return base


def _enqueue(am, rows):
    am.ANALYSIS_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    am.ANALYSIS_QUEUE.write_text("".join(json.dumps(r) + "\n" for r in rows))


# ── 5. social-weight ─────────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.social_negative_priority")
def test_social_negative_priority_lowers_queue_and_verdict_flag(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    am = _paths(monkeypatch, tmp_path)
    import msf_analysis
    _radar_cache_path(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    calls = {"x": 0}

    def _fake_search(_query):
        calls["x"] += 1
        if calls["x"] == 1:
            return _cacheable_radar(
                post_records=[
                    {"username": "alice", "text": "obvious scam rug"},
                    {"username": "bob", "text": "honeypot drain stay away"},
                ]
            )
        return _cacheable_radar()

    monkeypatch.setattr("radar_x.search_x", _fake_search)
    monkeypatch.setattr(msf_analysis, "probe_token_name_for_x", lambda _a: "TEST")
    monkeypatch.setattr(am, "_extract_baseline", lambda a: {"price_usd": "0.01", "liquidity_usd": 24000})
    monkeypatch.setattr(am, "_is_kabal", AsyncMock(return_value=False))

    _enqueue(
        am,
        [
            {"address": ADDR_A, "ts": NOW, "priority": 24000.0},
            {"address": ADDR_B, "ts": NOW, "priority": 10000.0},
        ],
    )
    sent = {"flags": []}

    async def _send(sink, address, manual=False):
        sent["address"] = address
        ctx = msf_analysis.take_analysis_queue_context(address)
        sent["flags"] = list(ctx.get("verdict_flags") or [])
        sent["social_confirmed"] = bool(ctx.get("social_confirmed"))
        return "sent"

    monkeypatch.setattr(am, "send_msf_pairresolve", _send)
    asyncio.run(am.rate_gate(_mock_sink()))

    queued = _jsonl(am.ANALYSIS_QUEUE)
    neg_row = next(r for r in queued if r["address"] == ADDR_A)
    assert neg_row["priority"] == pytest.approx(24000.0 * 0.75)
    assert neg_row.get("social_penalized") is True
    assert neg_row.get("verdict_flags") == ["negative_sentiment"]
    assert sent.get("address") == ADDR_B
    assert calls["x"] == 2

    asyncio.run(am.rate_gate(_mock_sink()))
    assert sent.get("address") == ADDR_A
    assert calls["x"] == 2
    assert sent.get("flags") == ["negative_sentiment"]
    assert sent.get("social_confirmed") is True

    verdict_line = msf_analysis._apply_summary_risk_flags(
        "SOLID",
        {},
        social_confirmed=sent.get("social_confirmed"),
    )
    assert "SOCIAL" in verdict_line and "негатив" in verdict_line.lower()

    neutral_root = tmp_path / "neutral"
    neutral_root.mkdir()
    am2 = _paths(monkeypatch, neutral_root)
    _radar_cache_path(monkeypatch, neutral_root)
    neutral_x = {"x": 0}
    monkeypatch.setattr(
        "radar_x.search_x",
        lambda _q: neutral_x.__setitem__("x", neutral_x["x"] + 1) or _cacheable_radar(),
    )

    async def _send2(sink, address, manual=False):
        return "sent"

    monkeypatch.setattr(am2, "send_msf_pairresolve", _send2)
    _enqueue(am2, [{"address": ADDR_B, "ts": NOW, "priority": 24000.0}])
    asyncio.run(am2.rate_gate(_mock_sink()))
    assert neutral_x["x"] == 1
    assert not _jsonl(am2.ANALYSIS_QUEUE)
    import inspect

    assert "community_sentiment" not in inspect.getsource(am._social_weight_sync)
    src = inspect.getsource(am.t0_tick)
    assert "_social_weight_sync" not in src
    assert "_prime_social" not in src


def test_social_x_calls_one_per_analyzed_including_deferred(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    am = _paths(monkeypatch, tmp_path)
    import msf_analysis
    _radar_cache_path(monkeypatch, tmp_path)
    calls = {"x": 0}

    def _fake_search(_q):
        calls["x"] += 1
        if calls["x"] == 1:
            return _cacheable_radar(
                post_records=[
                    {"username": "a", "text": "scam rug"},
                    {"username": "b", "text": "honeypot drain"},
                ]
            )
        return _cacheable_radar()

    monkeypatch.setattr("radar_x.search_x", _fake_search)
    monkeypatch.setattr(msf_analysis, "probe_token_name_for_x", lambda _a: "TKN")
    monkeypatch.setattr(am, "send_msf_pairresolve", AsyncMock(return_value="sent"))
    _enqueue(
        am,
        [
            {"address": ADDR_A, "ts": NOW, "priority": 30000.0},
            {"address": ADDR_B, "ts": NOW, "priority": 20000.0},
        ],
    )
    asyncio.run(am.rate_gate(_mock_sink()))
    asyncio.run(am.rate_gate(_mock_sink()))
    assert calls["x"] == 2


def test_social_x_calls_match_analyzed_tokens(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    am = _paths(monkeypatch, tmp_path)
    import msf_analysis
    _radar_cache_path(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    calls = {"x": 0}

    def _fake_search(_q):
        calls["x"] += 1
        return _cacheable_radar()

    monkeypatch.setattr("radar_x.search_x", _fake_search)
    monkeypatch.setattr(msf_analysis, "probe_token_name_for_x", lambda a: "TKN")
    monkeypatch.setattr(am, "send_msf_pairresolve", AsyncMock(return_value="sent"))

    k = 3
    rows = [
        {"address": f"{i:02d}" + ADDR_A[2:], "ts": NOW, "priority": 1000.0 * (k - i)}
        for i in range(k)
    ]
    _enqueue(am, rows)
    for _ in range(k):
        asyncio.run(am.rate_gate(_mock_sink()))
    assert calls["x"] == k
    q = msf_analysis.plan_x_query(rows[0]["address"], "TKN")
    raw, need = msf_analysis.resolve_x_enrichment_raw(rows[0]["address"], q)
    assert raw and not need
    assert calls["x"] == k


# ── 6. outcome-loop ────────────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.outcome_recorded_after_24h")
def test_outcome_recorded_after_24h(tmp_path, monkeypatch):
    import sink as sink_mod

    am = _paths(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    monkeypatch.setattr(am, "OUTCOME_AFTER_H", 24)

    s = sink_mod.Sink(out_dir=tmp_path / "analyses_out")
    s.out_dir.mkdir(parents=True, exist_ok=True)
    old = {
        "id": "v-old", "ts": NOW - 25 * 3600, "type": "verdict", "address": ADDR_A,
        "token": "TKN", "text": "🎯 PASS — TKN", "baseline": {"price_usd": "1.0", "liquidity_usd": 50000},
    }
    fresh = {
        "id": "v-new", "ts": NOW - 60, "type": "verdict", "address": ADDR_B,
        "token": "FRSH", "text": "🎯 PASS — FRSH", "baseline": {"price_usd": "1.0", "liquidity_usd": 50000},
    }
    s.jsonl.write_text(json.dumps(old) + "\n" + json.dumps(fresh) + "\n")
    monkeypatch.setattr(am, "_extract_baseline", lambda a: {"price_usd": "2.5", "liquidity_usd": 60000})

    _stop_loop(monkeypatch, sleeps=1)
    with pytest.raises(_StopLoop):
        asyncio.run(am.outcome_loop(s))

    # THEN строка {token, verdict, ts, outcome} дописана в jsonl — только для вердикта старше 24ч
    rows = _jsonl(am.OUTCOMES)
    assert len(rows) == 1
    assert {"token", "verdict", "ts", "outcome"} <= set(rows[0])
    assert rows[0]["token"] == "TKN"
    assert rows[0]["ts"] == old["ts"]
    assert rows[0]["outcome"] == "2x"


# ── 7. delivery-discipline ─────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.reject_batched_no_spam")
def test_reject_batched_no_spam(tmp_path, monkeypatch):
    import sink as sink_mod

    am = _paths(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    monkeypatch.setattr(am, "DIGEST_THRESHOLD", 3)
    monkeypatch.setattr(am, "DIGEST_WINDOW_H", 4)

    s = sink_mod.Sink(out_dir=tmp_path / "analyses_out")
    # GIVEN 10 REJECT за интервал дайджеста
    for i in range(10):
        asyncio.run(s.write("reject", ADDR_A, "?", f"REJECT #{i}"))

    # WHEN время дайджеста
    _stop_loop(monkeypatch, sleeps=1)
    with pytest.raises(_StopLoop):
        asyncio.run(am.digest_timer(s))

    # THEN владельцу доставлена одна пачка, не 10 сообщений
    recs = _jsonl(s.jsonl)
    assert sum(1 for r in recs if r["type"] == "reject") == 10
    digests = [r for r in recs if r["type"] == "digest"]
    assert len(digests) == 1
    assert digests[0]["digest_meta"]["counts"]["reject"] == 10
    assert digests[0]["digest_meta"]["threshold"] == 3
    assert "reject=10" in digests[0]["text"]


# ── 8. delivery-discipline ─────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.kabal_alert_not_pulsing")
def test_kabal_alert_not_pulsing(tmp_path, monkeypatch):
    import sink as sink_mod

    am = _paths(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    monkeypatch.setattr(am, "DIGEST_THRESHOLD", 3)

    s = sink_mod.Sink(out_dir=tmp_path / "analyses_out")
    # GIVEN KABAL-активность зафиксирована (alert в sink)
    alert_id = asyncio.run(s.write("alert", ADDR_K, "KBL", "⚠️ КАБАЛ: KBL (KBL)\nФаза: KOL_ACTIVATION"))
    assert alert_id
    asyncio.run(s.write("reject", ADDR_A, "?", "r1"))
    asyncio.run(s.write("reject", ADDR_B, "?", "r2"))

    # WHEN формируется очередь доставки
    _stop_loop(monkeypatch, sleeps=1)
    with pytest.raises(_StopLoop):
        asyncio.run(am.digest_timer(s))

    recs = _jsonl(s.jsonl)
    # THEN alert записан в дайджест, немедленной доставки нет (единственный канал — digest)
    assert {r["type"] for r in recs} == {"alert", "reject", "digest"}
    digests = [r for r in recs if r["type"] == "digest"]
    assert len(digests) == 1
    assert digests[0]["digest_meta"]["counts"]["alert"] == 1
    assert any(e["type"] == "alert" and e["address"] == ADDR_K for e in digests[0]["digest_meta"]["entries"])


# ── 9. delivery-discipline ─────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.empty_digest_window")
def test_empty_digest_window_no_delivery(tmp_path, monkeypatch):
    am = _paths(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    sink = _mock_sink()  # GIVEN за окно дайджеста записей нет

    _stop_loop(monkeypatch, sleeps=1)
    with pytest.raises(_StopLoop):
        asyncio.run(am.digest_timer(sink))

    # THEN доставка не выполняется, сообщений нет
    sink.write.assert_not_awaited()
    assert not am.DIGEST_CURSOR.exists()


# ── 10. rate-cap ───────────────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.rate_cap_queue_overflow")
def test_rate_cap_queue_overflow_deferred_and_persistent(tmp_path, monkeypatch):
    import importlib
    from unittest.mock import AsyncMock

    am = _paths(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    monkeypatch.setattr(am, "RATE_CAP_H", 15)
    monkeypatch.setattr(am, "KABAL_CAP_H", 5)
    # GIVEN порог анализов в час исчерпан
    am.ANALYSIS_QUEUE.write_text(json.dumps({"address": ADDR_A, "ts": NOW, "priority": 9000.0}) + "\n")
    am.RATE_LOG.write_text(
        "".join(json.dumps({"ts": NOW - 60, "address": f"done{i}"}) + "\n" for i in range(20))
    )
    send = AsyncMock(return_value="sent")
    monkeypatch.setattr(am, "send_msf_pairresolve", send)

    # WHEN приходит новый кандидат (проход rate_gate)
    asyncio.run(am.rate_gate(_mock_sink()))

    # THEN кандидат поставлен в очередь, анализ отложен
    send.assert_not_awaited()
    assert [r["address"] for r in _jsonl(am.ANALYSIS_QUEUE)] == [ADDR_A]
    assert len(_lines(am.RATE_LOG)) == 20

    # THEN событие переживает рестарт (очередь — персистентный jsonl)
    am = importlib.reload(am)
    monkeypatch.setattr(am, "ANALYSIS_QUEUE", tmp_path / "analysis_queue.jsonl")
    monkeypatch.setattr(am, "RATE_LOG", tmp_path / "analysis_rate.jsonl")
    monkeypatch.setattr(am, "send_msf_pairresolve", send)
    _freeze_time(monkeypatch)
    assert [json.loads(l)["address"] for l in am._load(am.ANALYSIS_QUEUE)] == [ADDR_A]

    # и после освобождения окна кандидат не потерян — уходит в анализ
    am.RATE_LOG.write_text(json.dumps({"ts": NOW - 7200, "address": "old"}) + "\n")
    asyncio.run(am.rate_gate(_mock_sink()))
    send.assert_awaited_once()
    assert send.await_args.args[1] == ADDR_A
    assert _lines(am.ANALYSIS_QUEUE) == []


# ── 11. rate-cap ───────────────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.kabal_cap_overflow")
def test_kabal_cap_overflow_uses_common_queue_and_formula(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    am = _paths(monkeypatch, tmp_path)
    _freeze_time(monkeypatch)
    monkeypatch.setattr(am, "RATE_CAP_H", 15)
    monkeypatch.setattr(am, "KABAL_CAP_H", 5)
    monkeypatch.setattr(am, "T0_INTERVAL_MIN", 20)
    monkeypatch.setattr(am, "_is_kabal", AsyncMock(return_value=True))  # KABAL-эскалация подтверждена
    monkeypatch.setattr(am, "_extract_baseline", lambda a: {"price_usd": "0.01", "liquidity_usd": 8000})
    am.T0_QUEUE.write_text(json.dumps({"address": ADDR_A, "ts": NOW - 3600}) + "\n")

    asyncio.run(am.t0_tick(_mock_sink()))

    # THEN эскалация попадает в ОБЩУЮ очередь по обычной формуле приоритета (liq + бонус)
    queued = _jsonl(am.ANALYSIS_QUEUE)
    assert [r["address"] for r in queued] == [ADDR_A]
    assert queued[0]["priority"] == 8000.0 + 10.0

    send = AsyncMock(return_value="sent")
    monkeypatch.setattr(am, "send_msf_pairresolve", send)
    # GIVEN лимит KABAL-эскалаций в час исчерпан (общий потолок cap+KABAL выбран)
    am.ANALYSIS_QUEUE.write_text(
        json.dumps({"address": ADDR_B, "ts": NOW, "priority": 20000.0}) + "\n" + json.dumps(queued[0]) + "\n"
    )
    am.RATE_LOG.write_text(
        "".join(json.dumps({"ts": NOW - 30, "address": f"esc{i}"}) + "\n" for i in range(15 + 5))
    )

    asyncio.run(am.rate_gate(_mock_sink()))

    # THEN обход rate cap не происходит: эскалация ждёт в общей очереди
    send.assert_not_awaited()
    assert sorted(r["address"] for r in _jsonl(am.ANALYSIS_QUEUE)) == sorted([ADDR_A, ADDR_B])

    # WHEN окно освободилось — берётся лучший по обычной формуле, не KABAL-бонус
    am.RATE_LOG.write_text("")
    asyncio.run(am.rate_gate(_mock_sink()))
    send.assert_awaited_once()
    assert send.await_args.args[1] == ADDR_B
    assert [r["address"] for r in _jsonl(am.ANALYSIS_QUEUE)] == [ADDR_A]


# ── 12. safety-priority ───────────────────────────────────────────────────
@pytest.mark.scenario("analysis-filters.confirmed_scam_drop")
def test_confirmed_scam_drop_removes_both_queues_and_writes_reject(tmp_path, monkeypatch):
    import sink as sink_mod

    am = _paths(monkeypatch, tmp_path)
    import msf_http
    assert REPO_ROOT in Path(msf_http.__file__).resolve().parents
    # analyzer_main должен нести именно production extractor этого worktree.
    assert am._extract_baseline is msf_http._extract_baseline
    _freeze_time(monkeypatch)
    monkeypatch.setattr(am, "T0_INTERVAL_MIN", 0)
    class Response:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, *, params=None, timeout=None):
        if "dexscreener.com" in url:
            return Response(200, [{"priceUsd": "0.01", "liquidity": {"usd": 20000}}])
        # Jupiter: sell token→SOL отсутствует, buy SOL→token существует.
        if params["inputMint"] == ADDR_A:
            return Response(400, {"errorCode": "NO_ROUTES_FOUND"})
        return Response(200, {"outAmount": "123", "routePlan": [{}]})

    # Граница сети подменена, но production carrier _extract_baseline выполняется целиком.
    monkeypatch.setattr(msf_http.requests, "get", fake_get)
    am.T0_QUEUE.write_text(json.dumps({"address": ADDR_A, "ts": NOW - 1}) + "\n")
    am.ANALYSIS_QUEUE.write_text(json.dumps({"address": ADDR_A, "ts": NOW, "priority": 1}) + "\n")
    sink = sink_mod.Sink(out_dir=tmp_path / "analyses_out")

    asyncio.run(am.t0_tick(sink))

    assert _lines(am.T0_QUEUE) == []
    assert _lines(am.ANALYSIS_QUEUE) == []
    records = _jsonl(sink.jsonl)
    assert [record["type"] for record in records] == ["reject"]
    assert records[0]["address"] == ADDR_A
    assert "DROP: confirmed scam" in records[0]["text"]

    # Тот же hard DROP обязан остаться на втором production переходе QUEUED→ANALYZED.
    am.ANALYSIS_QUEUE.write_text(json.dumps({
        "address": ADDR_B, "ts": NOW, "priority": 2,
        "safety": {"honeypot": "fail"},
    }) + "\n")
    asyncio.run(am.rate_gate(sink))
    assert _lines(am.ANALYSIS_QUEUE) == []
    records = _jsonl(sink.jsonl)
    assert [record["type"] for record in records] == ["reject", "reject"]
    assert records[-1]["address"] == ADDR_B


def _lexicon_posts(*pairs):
    return [{"username": u, "text": t} for u, t in pairs]


def test_social_lexicon_negation_not_negative():
    posts = _lexicon_posts(
        ("alice", "this is not a scam"),
        ("bob", "anti-rug team, looks fine"),
    )
    _, confirmed, _ = classify_negative(posts)
    assert not confirmed


def test_social_lexicon_ticker_rugger_ignored():
    posts = _lexicon_posts(
        ("alice", "aping $RUGGER now"),
        ("bob", "RUGGER is the play"),
    )
    _, confirmed, _ = classify_negative(posts, token_symbol="RUGGER")
    assert not confirmed


def test_social_lexicon_no_substring_shrug_drug():
    posts = _lexicon_posts(
        ("alice", "I shrug at this chart"),
        ("bob", "not drug related, just a ticker"),
    )
    assert not _post_negative(posts[0]["text"])
    assert not _post_negative(posts[1]["text"])
    _, confirmed, _ = classify_negative(posts)
    assert not confirmed


def test_social_lexicon_russian_negation():
    assert not _post_negative("это не скам, норм проект")
