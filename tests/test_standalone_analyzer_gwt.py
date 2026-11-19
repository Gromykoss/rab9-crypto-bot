"""GWT-тесты спеки openspec/specs/standalone-analyzer.md (v1.4 FROZEN).

Проверяется реальное поведение продакшн-кода: analyzer_main (t0_enroll/t0_tick/
rate_gate/digest_timer), sink.Sink (write/read_new/read_new_from), msf_http
(_parse_signal + do_POST /msf-signal, /analyze, send_msf_pairresolve), operators
(check_safety/check_verifier/check_destination), loop_memory/msf_dedupe (дедуп 24ч).

Герметичность: все пути состояния — tmp_path; границы системы (LLM, DexScreener,
cabal_detector) — детерминированные заглушки; исходящие сетевые вызовы за пределы
loopback запрещены autouse-фикстурой. Реальный data/ не затрагивается.
HTTP-тесты поднимают настоящий ingress (start_msf_http_server) на 127.0.0.1:0.

Offset-файл доставки (delivery-reader-contract) намеренно вне репозитория.
"""
import asyncio
import builtins
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]  # корень репо: локально и в CI (не хардкод пути)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ADDR_A = "4EMfevH3bDfnThB8EeNfF9KPiSD9YhEvgiFtUYFaWdEr"
ADDR_B = "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"
ALLOWED_CHAT = "-1004425561477"  # operators.ALLOWED_DESTINATIONS
SECRET = "gwt-secret"

REPORT_TEXT = "🎯 PASS — SOLID setup\n🔍 TESTTOK\n📝 AI-анализ токена TESTTOK"
SAFETY_OK = {"honeypot": "pass", "rugcheck": "low", "phase": "alive"}
SAFETY_RUGGED = {"honeypot": "pass", "rugcheck": "rugged", "phase": "alive"}
BASELINE = {"price_usd": "0.00123", "liquidity_usd": 42000}
VERIFIER_PASS = {"verdict": "PASS", "score": 91, "fixed_text": "", "issues": []}


# ── helpers ──────────────────────────────────────────────────────────────
def _read_jsonl(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_jsonl(path, records) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def _telegram_import_guard(monkeypatch) -> list[str]:
    """Ловушка на импорты telegram* — доказательство «ни одного Telegram-вызова»."""
    seen: list[str] = []
    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        if name == "telegram" or name.startswith("telegram."):
            seen.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    return seen


def _telegram_modules_loaded() -> list[str]:
    return sorted(m for m in sys.modules if m == "telegram" or m.startswith("telegram."))


def _dedup_key_on_disk(sb, address: str) -> bool:
    """Ключ дедупа 24ч записан: запись в loop_state.json (файл, не API)."""
    state_file = Path(sb.loop_memory.STATE_FILE)
    if not state_file.exists():
        return False
    state = json.loads(state_file.read_text())
    return any(entry.get("address", "").startswith(address[:8]) for entry in state.get("analyses", []))


@pytest.fixture(autouse=True)
def _no_external_network(monkeypatch):
    """Любой исходящий HTTP за пределы loopback = провал теста (не сеть, а баг)."""
    real_get, real_post, real_request = requests.get, requests.post, requests.request

    def _guard(real):
        def wrapper(url, *args, **kwargs):
            host = str(url)
            if "127.0.0.1" in host or "localhost" in host:
                return real(url, *args, **kwargs)
            raise AssertionError(f"внешний сетевой вызов запрещён: {url}")

        return wrapper

    monkeypatch.setattr(requests, "get", _guard(real_get))
    monkeypatch.setattr(requests, "post", _guard(real_post))
    monkeypatch.setattr(requests, "request", _guard(real_request))


@pytest.fixture
def sb(tmp_path, monkeypatch):
    """Герметичная песочница: пути → tmp_path, границы системы → заглушки."""
    import analyzer_main as am
    import cabal_detector
    import loop_memory
    import loop_verifier
    import msf_dedupe
    import msf_http
    import sink as sink_mod

    out_dir = tmp_path / "analyses_out"
    calls = {"llm": [], "verifier": []}

    # пути состояния — только tmp_path
    monkeypatch.setattr(am, "DATA", tmp_path)
    monkeypatch.setattr(am, "T0_QUEUE", tmp_path / "t0_queue.jsonl")
    monkeypatch.setattr(am, "ANALYSIS_QUEUE", tmp_path / "analysis_queue.jsonl")
    monkeypatch.setattr(am, "OUTCOMES", tmp_path / "verdict_outcomes.jsonl")
    monkeypatch.setattr(am, "RATE_LOG", tmp_path / "analysis_rate.jsonl")
    monkeypatch.setattr(am, "TRADES_STREAM", tmp_path / "trades_stream.jsonl")
    monkeypatch.setattr(am, "RADAR_COOLDOWN", tmp_path / "radar_cooldown.json")
    monkeypatch.setattr(am, "DIGEST_CURSOR", out_dir / "digest_cursor.json")
    monkeypatch.setattr(loop_memory, "STATE_FILE", str(tmp_path / "loop_state.json"))
    monkeypatch.setattr(msf_dedupe, "DEDUPE_PATH", str(tmp_path / "msf_dedupe.json"))

    # границы системы: DexScreener / LLM / cabal / EOA-кабинет
    monkeypatch.setattr(am, "_extract_baseline", lambda address: dict(BASELINE))
    monkeypatch.setattr(am, "_is_kabal", AsyncMock(return_value=False))
    monkeypatch.setattr(msf_http, "_extract_baseline", lambda address: dict(BASELINE))
    monkeypatch.setattr(msf_http, "TELEGRAM_GROUP_ID", ALLOWED_CHAT)
    monkeypatch.setattr(msf_http, "RAB9_HTTP_SECRET", SECRET)
    monkeypatch.setattr(cabal_detector, "analyze", lambda address: {"ok": False})

    def fake_build(address, mode="summary"):
        calls["llm"].append(address)
        return REPORT_TEXT, dict(SAFETY_OK)

    def fake_verify(token, ai_text, context):
        calls["verifier"].append(token)
        return dict(VERIFIER_PASS)

    monkeypatch.setattr(msf_http, "build_compact_analysis_text", fake_build)
    monkeypatch.setattr(loop_verifier, "verify_analysis", fake_verify)

    return SimpleNamespace(
        am=am,
        msf_http=msf_http,
        sink_mod=sink_mod,
        loop_memory=loop_memory,
        msf_dedupe=msf_dedupe,
        loop_verifier=loop_verifier,
        cabal_detector=cabal_detector,
        tmp=tmp_path,
        out_dir=out_dir,
        sink=sink_mod.Sink(out_dir=out_dir),
        llm=calls["llm"],
        verifier_calls=calls["verifier"],
        jsonl=out_dir / "analyses.jsonl",
    )


@pytest.fixture
def ingress(sb, monkeypatch):
    """Фабрика реального HTTP-ingress (start_msf_http_server) на 127.0.0.1:0."""
    started = []

    def _start(signal_coro=None):
        monkeypatch.setattr(sb.msf_http, "RAB9_HTTP_HOST", "127.0.0.1")
        monkeypatch.setattr(sb.msf_http, "RAB9_HTTP_PORT", 0)
        ing = SimpleNamespace()
        ing.loop = asyncio.new_event_loop()
        ing.thread = threading.Thread(target=ing.loop.run_forever, daemon=True, name="gwt-http-loop")
        ing.thread.start()
        ing.server = sb.msf_http.start_msf_http_server(sb.sink, ing.loop, signal_coro=signal_coro)
        ing.port = ing.server.server_address[1]

        def _post(path, payload, secret=SECRET):
            headers = {"Content-Type": "application/json"}
            if secret is not None:
                headers["X-RAB9-SECRET"] = secret
            return requests.post(
                f"http://127.0.0.1:{ing.port}{path}",
                headers=headers,
                json=payload,
                timeout=30,
            )

        ing.post = _post
        started.append(ing)
        return ing

    yield _start

    for ing in started:
        ing.server.shutdown()
        ing.server.server_close()
        ing.loop.call_soon_threadsafe(ing.loop.stop)
        ing.thread.join(timeout=5)


# ── 1. t0_no_llm_on_arrival ──────────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.t0_no_llm_on_arrival")
def test_t0_no_llm_on_arrival(sb, ingress):
    """GIVEN валидный POST /msf-signal нового адреса WHEN сигнал обработан
    THEN состояние T0_PENDING (мягкий чек, без LLM), DeepSeek не вызван."""
    ing = ingress(signal_coro=sb.am.t0_enroll)

    response = ing.post("/msf-signal", {"chain": "solana", "address": ADDR_A})

    assert response.status_code == 200
    # THEN: сигнал лёг в персистентную очередь t0_pending с результатом мягкого чека
    t0_records = _read_jsonl(sb.am.T0_QUEUE)
    assert [rec["address"] for rec in t0_records] == [ADDR_A]
    assert t0_records[0]["baseline"]["liquidity_usd"] == BASELINE["liquidity_usd"]
    # THEN: DeepSeek/LLM не вызван, вердикта нет
    assert sb.llm == []
    assert sb.verifier_calls == []
    assert _read_jsonl(sb.jsonl) == []
    # THEN: мягкий чек не пишет ключ дедупа 24ч (v1.2, N1)
    assert not (sb.tmp / "loop_state.json").exists()
    assert sb.msf_dedupe.check_dedupe(ADDR_A) is None


# ── 2. full_run_on_analyzed ──────────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.full_run_on_analyzed")
def test_full_run_on_analyzed(sb):
    """GIVEN токен в QUEUED с выполненным rate cap WHEN очередь допускает анализ
    THEN полный прогон выполнен, ключ дедупа записан, вердикт в sink."""
    _write_jsonl(sb.am.ANALYSIS_QUEUE, [{"address": ADDR_A, "ts": 1, "priority": 5000}])

    asyncio.run(sb.am.rate_gate(sb.sink))

    # THEN: вердикт в sink
    records = _read_jsonl(sb.jsonl)
    assert [rec["type"] for rec in records] == ["verdict"]
    assert records[0]["address"] == ADDR_A
    assert records[0]["text"] == REPORT_TEXT
    # THEN: полный прогон выполнен (LLM + verifier), токен ушёл из очереди
    assert sb.llm == [ADDR_A]
    assert sb.verifier_calls == ["TESTTOK"]
    assert sb.am._load(sb.am.ANALYSIS_QUEUE) == []
    # THEN: ключ дедупа записан на входе в ANALYZED
    assert _dedup_key_on_disk(sb, ADDR_A) is True
    assert sb.loop_memory.should_skip(ADDR_A, cooldown_minutes=15) is True


# ── 3. no_telegram_calls ─────────────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.no_telegram_calls")
def test_no_telegram_calls(sb, monkeypatch):
    """GIVEN любой прогон на машине состояний WHEN запись создана
    THEN вердикт записан в sink, ни один Telegram-вызов не выполнен."""
    telegram_imports = _telegram_import_guard(monkeypatch)
    _write_jsonl(sb.am.ANALYSIS_QUEUE, [{"address": ADDR_A, "ts": 1, "priority": 5000}])

    asyncio.run(sb.am.rate_gate(sb.sink))

    assert [rec["type"] for rec in _read_jsonl(sb.jsonl)] == ["verdict"]
    # THEN: ни одного обращения к Telegram-подсистеме
    assert telegram_imports == []
    assert _telegram_modules_loaded() == []


# ── 4. cascade_conflict_resolved ─────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.cascade_conflict_resolved")
def test_cascade_conflict_resolved(sb):
    """GIVEN мигрант на t=0 и дедуп-запись от первичного чека
    WHEN наступает внутренняя перепроверка
    THEN перепроверка выполняется (дедуп не нарушен — это не ingress-контакт)."""
    sb.msf_dedupe.record_address(ADDR_A, score=72, tier="SOLID", verdict="PASS — SOLID setup")
    dedupe_before = Path(sb.msf_dedupe.DEDUPE_PATH).read_bytes()
    _write_jsonl(sb.am.T0_QUEUE, [{"address": ADDR_A, "ts": 0, "baseline": {}}])

    asyncio.run(sb.am.t0_tick(sb.sink))

    # THEN: внутренний таймер очереди отработал — токен выжил и ушёл в QUEUED
    queued = _read_jsonl(sb.am.ANALYSIS_QUEUE)
    assert [rec["address"] for rec in queued] == [ADDR_A]
    assert _read_jsonl(sb.am.T0_QUEUE) == []
    # THEN: дедуп не нарушен — ключ первичного чека не перезаписан и не удалён
    assert Path(sb.msf_dedupe.DEDUPE_PATH).read_bytes() == dedupe_before
    assert sb.msf_dedupe.check_dedupe(ADDR_A) is not None
    # THEN: каскад не пишет ключ дедупа и не запускает LLM
    assert not (sb.tmp / "loop_state.json").exists()
    assert sb.llm == []


# ── 5. hard_drop_overrides ───────────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.hard_drop_overrides")
def test_hard_drop_overrides(sb, monkeypatch):
    """GIVEN токен в очереди t0_pending и rugcheck=rugged WHEN выполняется любой чек
    THEN немедленный DROP → sink(reject), очередь очищена."""
    from operators import Verdict, check_safety

    # THEN (оператор): подтверждённый scam = hard DROP, перекрывает мягкие гейты
    assert check_safety("pass", "rugged", "alive").verdict == Verdict.DROP

    # WHEN: полный прогон токена с подтверждённым rug — DROP перекрывает мягкие гейты
    monkeypatch.setattr(
        sb.msf_http, "build_compact_analysis_text",
        lambda address, mode="summary": (REPORT_TEXT, dict(SAFETY_RUGGED)),
    )
    status = asyncio.run(sb.msf_http.send_msf_pairresolve(sb.sink, ADDR_A))

    assert status == "dropped_safety"
    dropped = _read_jsonl(sb.jsonl)
    assert [rec["type"] for rec in dropped] == ["reject"]
    assert "DROP: confirmed scam" in dropped[0]["text"]
    assert sb.llm == []

    # WHEN: любой queue-check подтверждает honeypot=fail
    monkeypatch.setattr(
        sb.am, "_extract_baseline",
        lambda address: {"price_usd": "0.0", "liquidity_usd": 20000, "honeypot": "fail"},
    )
    _write_jsonl(sb.am.T0_QUEUE, [{"address": ADDR_B, "ts": 0, "baseline": {}}])
    _write_jsonl(sb.am.ANALYSIS_QUEUE, [{"address": ADDR_B, "ts": 0, "priority": 1}])

    asyncio.run(sb.am.t0_tick(sb.sink))

    # THEN: немедленный DROP кандидата → sink(reject) и очередь очищена
    records = _read_jsonl(sb.jsonl)
    assert [rec["type"] for rec in records] == ["reject", "reject"]
    assert records[-1]["address"] == ADDR_B
    assert "DROP: confirmed scam" in records[-1]["text"]
    assert _read_jsonl(sb.am.T0_QUEUE) == []
    assert _read_jsonl(sb.am.ANALYSIS_QUEUE) == []


# ── 6. bounded_queue_overflow ────────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.bounded_queue_overflow")
def test_bounded_queue_overflow(sb, monkeypatch):
    """GIVEN очередь анализа достигла конфиг-лимита WHEN приходит новый кандидат
    THEN кандидат → строка дайджеста, очереди не растут безгранично."""
    monkeypatch.setattr(sb.am, "QUEUE_MAX", 2)
    full_queue = [
        {"address": "TokenOneAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "ts": 1, "priority": 100},
        {"address": "TokenTwoBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB", "ts": 2, "priority": 200},
    ]
    _write_jsonl(sb.am.ANALYSIS_QUEUE, full_queue)
    _write_jsonl(sb.am.T0_QUEUE, [{"address": ADDR_A, "ts": 0, "baseline": {}}])

    asyncio.run(sb.am.t0_tick(sb.sink))

    # THEN: кандидат ушёл строкой в дайджест-канал (reject-строка), а не в очередь
    records = _read_jsonl(sb.jsonl)
    assert [rec["type"] for rec in records] == ["reject"]
    assert records[0]["address"] == ADDR_A
    assert "Очередь анализа полна" in records[0]["text"]
    # THEN: очередь не выросла
    assert len(sb.am._load(sb.am.ANALYSIS_QUEUE)) == len(full_queue)
    assert _read_jsonl(sb.am.T0_QUEUE) == []
    assert sb.llm == []


# ── 7. baseline_in_verdict_record ────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.baseline_in_verdict_record")
def test_baseline_in_verdict_record(sb):
    """GIVEN прогон завершился вердиктом PASS WHEN sink-запись создана
    THEN в jsonl присутствуют price_usd, liquidity_usd, manual."""
    asyncio.run(sb.msf_http.send_msf_pairresolve(sb.sink, ADDR_A, manual=True))

    records = _read_jsonl(sb.jsonl)
    assert [rec["type"] for rec in records] == ["verdict"]
    record = records[0]
    assert record["manual"] is True
    assert record["baseline"]["price_usd"] == BASELINE["price_usd"]
    assert record["baseline"]["liquidity_usd"] == BASELINE["liquidity_usd"]
    assert set(record["baseline"]) == {"price_usd", "liquidity_usd"}


# ── 8. verdict_written_to_sink ───────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.verdict_written_to_sink")
def test_verdict_written_to_sink(sb):
    """GIVEN прогон завершился вердиктом PASS/FLAG WHEN запись создана
    THEN jsonl-строка и файл вердикта существуют и читаемы после рестарта процесса."""
    _write_jsonl(sb.am.ANALYSIS_QUEUE, [{"address": ADDR_A, "ts": 1, "priority": 5000}])
    asyncio.run(sb.am.rate_gate(sb.sink))

    # рестарт процесса эмулируется свежим объектом Sink: состояние — только на диске
    sb.sink_mod.Sink(out_dir=sb.out_dir)
    restarted = sb.sink_mod.Sink(out_dir=sb.out_dir)
    records = restarted.read_new()
    assert [rec["type"] for rec in records] == ["verdict"]
    assert records[0]["address"] == ADDR_A
    assert records[0]["text"] == REPORT_TEXT
    assert restarted.read_new_from(0)[0] == records  # jsonl-строка валидна и перечитываема

    verdict_files = sorted(sb.out_dir.glob("*_verdict_*.md"))
    assert len(verdict_files) == 1
    assert verdict_files[0].read_text().strip() == REPORT_TEXT
    assert verdict_files[0].stat().st_size > 0


# ── 9. manual_analyze_run ────────────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.manual_analyze_run")
def test_manual_analyze_run(sb, ingress):
    """GIVEN POST /analyze валидного адреса WHEN прогон завершён
    THEN запись type=verdict c manual=true в sink и вердикт-ответ на HTTP-запрос."""
    ing = ingress()

    response = ing.post("/analyze", {"chain": "solana", "address": ADDR_A})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["verdict"] == REPORT_TEXT  # THEN: вердикт-ответ на HTTP-запрос
    records = _read_jsonl(sb.jsonl)
    assert [rec["type"] for rec in records] == ["verdict"]
    assert records[0]["manual"] is True
    assert records[0]["address"] == ADDR_A
    assert records[0]["text"] == payload["verdict"]


# ── 10. manual_endpoint_authorized ───────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.manual_endpoint_authorized")
def test_manual_endpoint_authorized(sb, ingress):
    """GIVEN POST /analyze с валидным адресом и секретом WHEN прогон завершён
    THEN HTTP-ответ содержит вердикт, sink-запись type=verdict c manual=true,
    ключ дедупа записан."""
    ing = ingress()

    response = ing.post("/analyze", {"chain": "solana", "address": ADDR_A}, secret=SECRET)

    assert response.status_code == 200  # запрос принят (не 401)
    assert response.json()["status"] == "sent"
    assert response.json()["verdict"]
    records = _read_jsonl(sb.jsonl)
    assert [rec["type"] for rec in records] == ["verdict"]
    assert records[0]["manual"] is True
    # THEN: ручной запрос пишет ключ дедупа (явное намерение владельца)
    assert _dedup_key_on_disk(sb, ADDR_A) is True
    assert sb.loop_memory.should_skip(ADDR_A, cooldown_minutes=15) is True


# ── 11. manual_endpoint_unauthorized ─────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.manual_endpoint_unauthorized")
def test_manual_endpoint_unauthorized(sb, ingress):
    """GIVEN POST /analyze без корректного X-RAB9-SECRET WHEN запрос обработан
    THEN 401, прогон не запускается."""
    ing = ingress()
    payload = {"chain": "solana", "address": ADDR_A}

    no_secret = ing.post("/analyze", payload, secret=None)
    wrong_secret = ing.post("/analyze", payload, secret="wrong-secret")

    assert no_secret.status_code == 401
    assert wrong_secret.status_code == 401
    assert no_secret.json()["error"] == "unauthorized"
    # THEN: прогон не запускался
    assert sb.llm == []
    assert sb.verifier_calls == []
    assert _read_jsonl(sb.jsonl) == []
    assert not (sb.tmp / "loop_state.json").exists()


# ── 12. digest_composition ───────────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.digest_composition")
def test_digest_composition(sb, monkeypatch):
    """GIVEN за окно накопились записи разных типов WHEN окно дайджеста наступило
    (порог ≥3 выполнен) THEN digest-запись в sink содержит свод всех записей окна."""
    monkeypatch.setattr(sb.am, "DIGEST_POLL_S", 5.0)
    ids = asyncio.run(_fill_window(sb))
    assert len(ids) == 3

    async def _run():
        try:
            await asyncio.wait_for(sb.am.digest_timer(sb.sink), timeout=1.5)
        except asyncio.TimeoutError:
            return  # ожидаемое поведение: таймер остаётся жив и уходит в sleep

    asyncio.run(_run())

    records = _read_jsonl(sb.jsonl)
    digests = [rec for rec in records if rec["type"] == "digest"]
    assert len(digests) == 1
    digest = digests[0]
    meta = digest["digest_meta"]
    # THEN: свод всех записей окна — типы, id, заголовки
    assert meta["counts"]["verdict"] == 1
    assert meta["counts"]["reject"] == 1
    assert meta["counts"]["alert"] == 1
    assert {entry["id"] for entry in meta["entries"]} == set(ids)
    assert {entry["type"] for entry in meta["entries"]} == {"verdict", "reject", "alert"}
    assert "Дайджест окна 4.0ч: 3 записей" in digest["text"]
    assert json.loads(sb.am.DIGEST_CURSOR.read_text())["last_digest_id"] == digest["id"]


async def _fill_window(sb) -> list[str]:
    """Три записи разных типов в окне (verdict/reject/alert) через реальный Sink."""
    written = [
        await sb.sink.write("verdict", ADDR_A, "TESTTOK", REPORT_TEXT, baseline=dict(BASELINE)),
        await sb.sink.write("reject", ADDR_B, "?", "Токен не пережил t0-каскад (ликвидность $0)."),
        await sb.sink.write("alert", ADDR_A, "TESTTOK", "⚠️ КАБАЛ: фаза KOL_ACTIVATION"),
    ]
    return written


# ── 13. telegram_demolition_intact ───────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.telegram_demolition_intact")
def test_telegram_demolition_intact(sb, monkeypatch):
    """GIVEN Telegram-модули удалены WHEN полный прогон выполняется
    THEN пайплайн работает, telegram не импортируется."""
    # GIVEN: в репозитории нет telegram-импортов в модулях ядра и пайплайна
    for name in ("analyzer_main.py", "sink.py", "msf_http.py", "msf_dedupe.py"):
        source = (REPO_ROOT / name).read_text()
        assert "from telegram" not in source and "import telegram" not in source, name
    # GIVEN: модули пайплайна живы
    import cabal_detector  # noqa: F401
    import loop_verifier  # noqa: F401
    import msf_dedupe  # noqa: F401
    import wallet_intel  # noqa: F401
    import operators  # noqa: F401

    telegram_imports = _telegram_import_guard(monkeypatch)
    _write_jsonl(sb.am.ANALYSIS_QUEUE, [{"address": ADDR_A, "ts": 1, "priority": 5000}])

    # WHEN: полный прогон
    asyncio.run(sb.am.rate_gate(sb.sink))

    # THEN: пайплайн отработал, telegram не импортирован
    assert [rec["type"] for rec in _read_jsonl(sb.jsonl)] == ["verdict"]
    assert telegram_imports == []
    assert _telegram_modules_loaded() == []


# ── 14. dedup_preserved_24h ──────────────────────────────────────────────
@pytest.mark.scenario("standalone-analyzer.dedup_preserved_24h")
def test_dedup_preserved_24h(sb):
    """GIVEN повторный адрес в 24ч WHEN сигнал поступает на ingress
    THEN анализ не запускается повторно (msf_dedupe работает как прежде)."""
    sb.loop_memory.record_analysis(ADDR_A, "TESTTOK", "PASS — SOLID setup", "SOLID")
    sb.msf_dedupe.record_address(ADDR_A, score=72, tier="SOLID", liq="$42K", verdict="PASS — SOLID setup")
    store_before = Path(sb.msf_dedupe.DEDUPE_PATH).read_bytes()
    _write_jsonl(sb.am.ANALYSIS_QUEUE, [{"address": ADDR_A, "ts": 1, "priority": 5000}])

    asyncio.run(sb.am.rate_gate(sb.sink))

    # THEN: повторного полного AI-прогона нет — только строка дайджеста
    assert sb.llm == []
    assert sb.verifier_calls == []
    records = _read_jsonl(sb.jsonl)
    assert [rec["type"] for rec in records] == ["reject"]
    assert "24h dedupe" in records[0]["text"]
    # THEN: 24ч-дедуп работает как прежде — recap отдаётся, ключ не переписан
    assert sb.msf_dedupe.check_dedupe(ADDR_A) is not None
    assert Path(sb.msf_dedupe.DEDUPE_PATH).read_bytes() == store_before
