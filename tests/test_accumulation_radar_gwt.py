"""GWT-тесты спеки accumulation-radar v1.0 (FROZEN) — поток сделок, radar-тик, дайджест.

Сценарии 1–2: pumpportal_listener._trade_stream + восстановление подписки в _session
(фейковый WS, файл потока на tmp_path).
Сценарии 3–6: analyzer_main.accumulation_radar / digest_timer (sink/Mock-sink, без сети).
"""
import asyncio
import contextlib
import json
import os
import sys
import time

import pytest

sys.path.insert(0, "/home/hermes-workspace/rab9")

BURNIE_MINT = "CGEDT9QZDvvH5GmVkWJH2BXiMJqMJySC9ihWyr7Spump"


# ── фейковая WS-сессия (герметично, без сети) ──
class _FakeWS:
    """Двойник websockets-соединения: очередь входящих кадров + запись отправленных подписок."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.sent = []  # исходящие JSON-кадры (подписки)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if not self.frames:
            raise asyncio.TimeoutError("fake ws: no ack frame")
        return self.frames.pop(0)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.frames:
            raise StopAsyncIteration
        return self.frames.pop(0)

    def subscriptions(self):
        return [f for f in self.sent if "method" in f and "keys" in f]


def _ack():
    """Кадр подтверждения подписки (subscription-liveness ищет «subscribed»)."""
    return json.dumps({"message": "Successfully subscribed"})


def _trade_frame(wallet, tx_type, token_amount, sol_amount, mint=BURNIE_MINT):
    return json.dumps({
        "txType": tx_type,
        "traderPublicKey": wallet,
        "tokenAmount": token_amount,
        "solAmount": sol_amount,
        "mint": mint,
    })


def _run_ws_sessions(tmp_path, monkeypatch, frames_per_session):
    """Прокатывает pumpportal_listener._session() по одной фейковой сессии на элемент списка.

    Возвращает список использованных _FakeWS (реконнект/рестарт = новая сессия).
    """
    import pumpportal_listener as pl

    monkeypatch.setattr(pl, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(pl, "PPP_API_KEY", "test-funded-key")  # funded-тир: tokenTrade доступен
    monkeypatch.setattr(pl, "PPP_FAILED_FILE", str(tmp_path / "ingress_failed.jsonl"))
    monkeypatch.setattr(pl, "WALLET_FILE", str(tmp_path / "wallet_watch.json"))
    monkeypatch.setattr(pl, "read_wallets", lambda: [])  # wallet-ветка не участвует в сценарии

    made = []
    queue = [list(f) for f in frames_per_session]

    def _connect(*args, **kwargs):
        ws = _FakeWS(queue.pop(0))
        made.append(ws)
        return ws

    monkeypatch.setattr(pl.websockets, "connect", _connect)
    for _ in frames_per_session:
        asyncio.run(pl._session())
    return made


def _stream_rows(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


# ── Сценарий 1 ──
@pytest.mark.scenario("accumulation-radar.trade_row_written")
def test_trade_row_written(tmp_path, monkeypatch):
    """THEN: строка {ts, wallet, tx_type, token_amount, sol_amount} дописана в поток."""
    wallet = "4EMfevH3Ysbw6S5CATzsgBJbutLV62MtrJJmo3F9zaQ9"
    sessions = _run_ws_sessions(
        tmp_path, monkeypatch,
        [[_ack(), _ack(), _trade_frame(wallet, "buy", 1000, 1.5)]],
    )
    stream = tmp_path / "data" / "trades_stream.jsonl"
    rows = _stream_rows(stream)
    assert len(rows) == 1, "сделка BURNIE должна дать ровно одну строку потока"
    row = rows[0]
    assert set(row) == {"ts", "wallet", "tx_type", "token_amount", "sol_amount"}
    assert row["wallet"] == wallet
    assert row["tx_type"] == "buy"
    assert row["token_amount"] == 1000.0
    assert row["sol_amount"] == 1.5
    assert abs(row["ts"] - time.time()) < 120
    # подписка на поток сделок BURNIE отправлена в живой сессии
    assert {"method": "subscribeTokenTrade", "keys": [BURNIE_MINT]} in sessions[0].sent


# ── Сценарий 2 ──
@pytest.mark.scenario("accumulation-radar.stream_survives_restart")
def test_stream_survives_restart(tmp_path, monkeypatch):
    """THEN: подписка восстанавливается, новые сделки дописываются в тот же файл."""
    w1 = "4EMfevH3Ysbw6S5CATzsgBJbutLV62MtrJJmo3F9zaQ9"
    w2 = "DAqCpTpQN1JNCDYLXWir28q1J2eXSufiNNADsSnUQTBZ"
    sessions = _run_ws_sessions(
        tmp_path, monkeypatch,
        [
            [_ack(), _ack(), _trade_frame(w1, "buy", 500, 2.0)],
            [_ack(), _ack(), _trade_frame(w2, "sell", 250, 1.0)],  # после перезапуска
        ],
    )
    stream = tmp_path / "data" / "trades_stream.jsonl"
    rows = _stream_rows(stream)
    assert [r["wallet"] for r in rows] == [w1, w2], "обе сделки в ОДНОМ файле потока"
    assert [r["tx_type"] for r in rows] == ["buy", "sell"]
    for i, ws in enumerate(sessions):
        assert {"method": "subscribeTokenTrade", "keys": [BURNIE_MINT]} in ws.sent, \
            f"сессия {i}: подписка на поток не восстановлена"
        assert {"method": "subscribeMigration"} in ws.sent


# ── хелперы radar-тика (общая рыночная картина на tmp_path) ──
def _radar_env(tmp_path, monkeypatch, buys, sells, change_24h=-12.0):
    """Собирает поток сделок 24ч + просадку в sentiment-снапшоте. Никаких прод-файлов."""
    import analyzer_main as am

    now = time.time()
    rows = [json.dumps({"ts": now - 3600, "wallet": w, "tx_type": "buy",
                        "token_amount": 1000, "sol_amount": s}) for w, s in buys]
    rows += [json.dumps({"ts": now - 1800, "wallet": w, "tx_type": "sell",
                         "token_amount": 900, "sol_amount": s}) for w, s in sells]
    stream = tmp_path / "trades_stream.jsonl"
    stream.write_text("\n".join(rows) + "\n")

    monkeypatch.setattr(am, "TRADES_STREAM", stream)
    monkeypatch.setattr(am, "RADAR_COOLDOWN", tmp_path / "radar_cooldown.json")
    monkeypatch.setattr(am, "DATA", tmp_path)
    monkeypatch.setattr(am, "_known_accumulators", lambda: set())
    monkeypatch.setattr(am, "_extract_baseline",
                        lambda a: {"price_usd": "0.001", "liquidity_usd": 200000})
    (tmp_path / "community_sentiment.jsonl").write_text(
        json.dumps({"change_24h": change_24h, "sentiment": "pos"}) + "\n"
    )
    return am


def _dip_accumulation():
    """8 кошельков на просадке −12%, продажи 1/80 объёма (<25%), покупатели держат."""
    buys = [(f"wallet{i}", 10) for i in range(8)]
    sells = [("wallet0", 1)]
    return buys, sells


# ── Сценарий 3 ──
@pytest.mark.scenario("accumulation-radar.organized_buy_on_dip")
def test_organized_buy_on_dip(tmp_path, monkeypatch):
    """THEN: сигнал «организованный выкуп» записан в sink + cooldown зафиксирован."""
    from unittest.mock import AsyncMock, Mock

    buys, sells = _dip_accumulation()
    am = _radar_env(tmp_path, monkeypatch, buys, sells)

    sink = Mock()
    sink.write = AsyncMock(return_value="alert-id")
    asyncio.run(am.accumulation_radar(sink))

    sink.write.assert_awaited_once()
    args = sink.write.await_args.args
    assert args[0] == "alert"          # radar-delivery: type=alert
    assert args[1] == BURNIE_MINT      # адрес BURNIE
    assert args[2] == "BURNIE"
    assert "ОРГАНИЗОВАННЫЙ ВЫКУП" in args[3]
    assert "8 кошельков" in args[3] and "держат" in args[3]
    cool = json.loads((tmp_path / "radar_cooldown.json").read_text())
    assert time.time() - cool["last_signal_ts"] < 120, "cooldown сигнала не записан"


# ── Сценарий 4 ──
@pytest.mark.scenario("accumulation-radar.calm_market_no_signal")
def test_calm_market_no_signal(tmp_path, monkeypatch):
    """THEN: продают 60% купленного объёма → сигнала нет."""
    from unittest.mock import AsyncMock, Mock

    buys = [(f"wallet{i}", 10) for i in range(10)]     # 100 SOL покупок, 10 покупателей
    sells = [(f"wallet{i}", 20) for i in range(3)]     # 60 SOL продаж = 60% объёма
    am = _radar_env(tmp_path, monkeypatch, buys, sells)
    assert sum(s for _, s in sells) / sum(s for _, s in buys) == pytest.approx(0.6)

    sink = Mock()
    sink.write = AsyncMock(return_value="x")
    asyncio.run(am.accumulation_radar(sink))
    sink.write.assert_not_awaited()


# ── Сценарий 5 ──
@pytest.mark.scenario("accumulation-radar.anti_repeat_cooldown")
def test_anti_repeat_cooldown(tmp_path, monkeypatch):
    """THEN: сигнал за последние 6ч уже был → новая запись не делается."""
    from unittest.mock import AsyncMock, Mock

    buys, sells = _dip_accumulation()
    am = _radar_env(tmp_path, monkeypatch, buys, sells)

    cool_path = tmp_path / "radar_cooldown.json"
    prev_ts = time.time() - 3600  # 1ч назад — внутри 6ч окна анти-повтора
    cool_path.write_text(json.dumps({"last_signal_ts": prev_ts}))

    sink = Mock()
    sink.write = AsyncMock(return_value="x")
    asyncio.run(am.accumulation_radar(sink))

    sink.write.assert_not_awaited()
    assert json.loads(cool_path.read_text())["last_signal_ts"] == prev_ts, \
        "cooldown-метка не должна перезаписываться"

    # контроль: та же картина без свежего cooldown → сигнал есть (иначе тест вакуумный)
    cool_path.unlink()
    sink2 = Mock()
    sink2.write = AsyncMock(return_value="alert-id")
    asyncio.run(am.accumulation_radar(sink2))
    sink2.write.assert_awaited_once()


# ── Сценарий 6 ──
async def _drive_digest(sink_obj, am, timeout=5.0):
    """Прокручивает digest_timer до первой доставки дайджеста и гасит его."""
    task = asyncio.create_task(am.digest_timer(sink_obj))
    deadline = time.time() + timeout
    try:
        while sink_obj.write.await_count < 1 and time.time() < deadline:
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.mark.scenario("accumulation-radar.signal_into_digest")
def test_signal_into_digest(tmp_path, monkeypatch):
    """THEN: свод выкупа доставлен владельцу вместе с пачкой окна дайджеста."""
    from unittest.mock import AsyncMock

    import analyzer_main as am
    import sink as sink_mod

    out_dir = tmp_path / "analyses_out"
    monkeypatch.setattr(sink_mod, "JSONL", out_dir / "analyses.jsonl")  # ротация — только tmp

    buys, sells = _dip_accumulation()
    _radar_env(tmp_path, monkeypatch, buys, sells)
    monkeypatch.setattr(am, "DIGEST_CURSOR", tmp_path / "digest_cursor.json")
    monkeypatch.setattr(am, "DIGEST_THRESHOLD", 3)
    monkeypatch.setattr(am, "DIGEST_POLL_S", 0.01)

    # GIVEN: сигнал выкупа зафиксирован в sink (реальная запись в tmp-файл)
    real_sink = sink_mod.Sink(out_dir=out_dir)
    asyncio.run(am.accumulation_radar(real_sink))

    recs = _stream_rows(out_dir / "analyses.jsonl")
    alerts = [r for r in recs if r.get("type") == "alert"]
    assert len(alerts) == 1 and "ОРГАНИЗОВАННЫЙ ВЫКУП" in alerts[0]["text"], \
        "сигнал выкупа не зафиксирован в sink — дайджест-проверка была бы вакуумной"

    # добираем окно до порога дайджеста (более ранние записи анализатора)
    with open(out_dir / "analyses.jsonl", "a") as f:
        f.write(json.dumps({"id": "old-1", "ts": time.time() - 120, "type": "reject",
                            "address": "4EMfevH3Ysbw6S5CATzsgBJbutLV62MtrJJmo3F9zaQ9",
                            "token": "?", "text": "Токен не пережил t0-каскад."}) + "\n")
        f.write(json.dumps({"id": "old-2", "ts": time.time() - 60, "type": "verdict",
                            "address": "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
                            "token": "T", "text": "Вердикт."}) + "\n")

    # WHEN: окно дайджеста (владелец в тесте = Mock-sink)
    owner = sink_mod.Sink(out_dir=out_dir)
    owner.write = AsyncMock(return_value="digest-id-1")
    asyncio.run(_drive_digest(owner, am))

    owner.write.assert_awaited_once()
    call = owner.write.await_args
    assert call is not None
    args = call.args
    meta = call.kwargs["digest_meta"]
    assert args[0] == "digest"
    assert meta["counts"]["alert"] == 1
    assert args[3].startswith("Дайджест окна") and "alert=1" in args[3]
    titles = [e["title"] for e in meta["entries"] if e["type"] == "alert"]
    assert titles and any("ОРГАНИЗОВАННЫЙ ВЫКУП" in t for t in titles), \
        "пачка выкупа не попала в дайджест"
    assert any(e["token"] == "BURNIE" and e["address"] == BURNIE_MINT for e in meta["entries"])
    assert meta["window_end"] >= alerts[0]["ts"] >= meta["window_start"]
    assert json.loads((tmp_path / "digest_cursor.json").read_text())["last_digest_id"] == "digest-id-1"
    assert os.path.exists(out_dir / "analyses.jsonl")
