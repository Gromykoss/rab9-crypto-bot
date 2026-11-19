"""GWT-тесты спеки openspec/specs/wallet-watch.md (v1.0 FROZEN).

Проверяется реальное поведение pumpportal_listener._session / _wallet_event /
read_wallets и sink.Sink: фейковый WS (ack'и + поток событий), все пути — в
tmp_path, сеть не задействована.

Замечание по спеку/код: sink-запись wallet-события (type=wallet) содержит
address=mint, token="?" и text; поля wallet/tx_type/token_amount/sol_amount/mint
пишутся продакшн-кодом в парный журнал data/wallet_events.jsonl тем же вызовом
_wallet_event. Тесты проверяют обе части — как они реально пишутся.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
import types

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]  # корень репо: локально и в CI (не хардкод пути)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

WALLET_A = "4EMfevH3Ysbw6S5CATzsgBJbutLV62MtrJJmo3F9zaQ9"
WALLET_B = "DAqCpTpQN1JNCDYLXWir28q1J2eXSufiNNADsSnUQTBZ"  # не в wallet_watch.json
TOKEN_MINT = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"  # != BURNIE_MINT


# ── фейковый WS ──
class _FakeWS:
    """WS-хендшейк: recv/__anext__ отдают заранее заданные ack'и и события."""

    def __init__(self, acks, events):
        self._incoming = list(acks) + list(events)
        self.sent = []
        self.closed = False

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if not self._incoming:
            raise AssertionError("fake WS: recv без сообщений (ack'и подписок не поданы)")
        return self._incoming.pop(0)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._incoming:
            raise StopAsyncIteration
        return self._incoming.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False


class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _ack(text):
    return json.dumps({"message": text})


def _acks():
    """ack'и всех подписок funded-конфигурации: migration + accountTrade + tokenTrade."""
    return [
        _ack("Successfully subscribed to subscribeMigration"),
        _ack("Successfully subscribed to subscribeAccountTrade"),
        _ack("Successfully subscribed to subscribeTokenTrade"),
    ]


def _read_jsonl(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _drive_session(pl, sink_cls, monkeypatch, tmp_path, wallets, acks, events):
    """Реальный pl._session() на фейковом WS. Возвращает (ws, sink_out_dir)."""
    wfile = tmp_path / "wallet_watch.json"
    wfile.write_text(json.dumps(wallets), encoding="utf-8")
    monkeypatch.setattr(pl, "WALLET_FILE", str(wfile))       # read_wallets → tmp_path
    monkeypatch.setattr(pl, "BASE_DIR", str(tmp_path))       # журналы wallet_events/trades_stream
    monkeypatch.setattr(pl, "PPP_API_KEY", "test-funded-key")  # accountTrade требует funded
    out_dir = tmp_path / "analyses_out"
    monkeypatch.setattr(pl, "_ReportSink", lambda: sink_cls(out_dir=out_dir))
    ws = _FakeWS(acks, events)
    monkeypatch.setattr(pl, "websockets", types.SimpleNamespace(connect=lambda url, **kw: ws))
    asyncio.run(pl._session())
    return ws, out_dir


# ── wallet-subscription: двойная подписка ──
@pytest.mark.scenario("wallet-watch.double_subscription_ack")
def test_wallet_watch_double_subscription_ack(tmp_path, monkeypatch, caplog):
    """GWT: WS установлен + ≥1 адрес → ack'и subscribeMigration и subscribeAccountTrade, «subscription active» в логе."""
    import pumpportal_listener as pl
    import sink as sink_mod

    wallets = [WALLET_A, "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"]
    cap = _LogCapture()
    pl.log.addHandler(cap)
    old_level = pl.log.level
    pl.log.setLevel(logging.INFO)
    try:
        ws, _ = _drive_session(pl, sink_mod.Sink, monkeypatch, tmp_path, wallets, _acks(), [])
    finally:
        pl.log.setLevel(old_level)
        pl.log.removeHandler(cap)

    # список кошельков реально прочитан из wallet_watch.json
    assert pl.read_wallets() == wallets

    methods = [m.get("method") for m in ws.sent]
    assert "subscribeMigration" in methods
    assert "subscribeAccountTrade" in methods
    acct = next(m for m in ws.sent if m.get("method") == "subscribeAccountTrade")
    assert acct["keys"] == wallets  # подписка на каждый адрес из wallet_watch.json
    assert ws.closed

    active = [m for m in cap.messages if "subscription active" in m]
    assert active, "нет лога «subscription active» после ack'ов"
    assert any("subscribeMigration" in m for m in active)
    assert any("subscribeAccountTrade" in m for m in active)
    assert "(3/3)" in active[-1]  # все ожидаемые ack'и получены


# ── wallet-event-to-sink: продажа кита ──
@pytest.mark.scenario("wallet-watch.whale_sell_to_sink")
def test_wallet_watch_whale_sell_to_sink(tmp_path, monkeypatch):
    """GWT: txType=sell watched-кошелька → sink-запись type=wallet с wallet/tx_type/token_amount/sol_amount."""
    import pumpportal_listener as pl
    import sink as sink_mod

    events = [_acks()[0], _acks()[1], _acks()[2], json.dumps({
        "txType": "sell",
        "traderPublicKey": WALLET_A,
        "tokenAmount": 1868523,
        "solAmount": 22.3,
        "mint": TOKEN_MINT,
    })]
    ws, out_dir = _drive_session(pl, sink_mod.Sink, monkeypatch, tmp_path, [WALLET_A], [], events)
    assert ws.closed

    sink_records = _read_jsonl(out_dir / "analyses.jsonl")
    assert len(sink_records) == 1
    rec = sink_records[0]
    assert rec["type"] == "wallet"
    assert rec["id"] and rec["ts"]
    assert rec["address"] == TOKEN_MINT
    assert "ПРОДАЖА" in rec["text"]

    wallet_records = _read_jsonl(tmp_path / "data" / "wallet_events.jsonl")
    assert len(wallet_records) == 1
    w = wallet_records[0]
    assert w["wallet"] == WALLET_A
    assert w["tx_type"] == "sell"
    assert w["token_amount"] == 1868523
    assert w["sol_amount"] == 22.3
    assert w["mint"] == TOKEN_MINT


# ── wallet-event-to-sink: чужой кошелёк ──
@pytest.mark.scenario("wallet-watch.foreign_wallet_ignored")
def test_wallet_watch_foreign_wallet_ignored(tmp_path, monkeypatch):
    """GWT: accountTrade по кошельку не из wallet_watch.json → sink-запись НЕ создана."""
    import pumpportal_listener as pl
    import sink as sink_mod

    events = _acks() + [json.dumps({
        "txType": "buy",
        "traderPublicKey": WALLET_B,
        "tokenAmount": 10,
        "solAmount": 0.5,
        "mint": TOKEN_MINT,
    })]
    ws, out_dir = _drive_session(pl, sink_mod.Sink, monkeypatch, tmp_path, [WALLET_A], [], events)
    assert ws.closed
    assert WALLET_B not in pl.read_wallets()

    assert not (out_dir / "analyses.jsonl").exists()
    assert _read_jsonl(out_dir / "analyses.jsonl") == []
    assert _read_jsonl(tmp_path / "data" / "wallet_events.jsonl") == []


# ── wallet-no-dedup: повторное движение ──
@pytest.mark.scenario("wallet-watch.no_dedup_repeat_move")
def test_wallet_watch_no_dedup_repeat_move(tmp_path, monkeypatch):
    """GWT: два движения одного watched-кошелька за час → обе записи в sink, дедуп 24ч не срабатывает."""
    import pumpportal_listener as pl
    import sink as sink_mod

    base_ts = 1_760_000_000
    events = _acks() + [
        json.dumps({"txType": "buy", "traderPublicKey": WALLET_A, "tokenAmount": 1000,
                    "solAmount": 1.5, "mint": TOKEN_MINT, "ts": base_ts}),
        json.dumps({"txType": "sell", "traderPublicKey": WALLET_A, "tokenAmount": 1000,
                    "solAmount": 2.1, "mint": TOKEN_MINT, "ts": base_ts + 3600}),  # тот же токен, +1 час
    ]
    ws, out_dir = _drive_session(pl, sink_mod.Sink, monkeypatch, tmp_path, [WALLET_A], [], events)
    assert ws.closed

    sink_records = _read_jsonl(out_dir / "analyses.jsonl")
    assert len(sink_records) == 2  # дедуп 24ч к wallet-событиям не применён
    for rec in sink_records:
        assert rec["type"] == "wallet"
    assert "ПОКУПКА" in sink_records[0]["text"]
    assert "ПРОДАЖА" in sink_records[1]["text"]

    wallet_records = _read_jsonl(tmp_path / "data" / "wallet_events.jsonl")
    assert len(wallet_records) == 2
    assert [r["tx_type"] for r in wallet_records] == ["buy", "sell"]
    assert {r["mint"] for r in wallet_records} == {TOKEN_MINT}
    assert len({r["id"] for r in wallet_records}) == 2  # разные записи, не схлопнутые
