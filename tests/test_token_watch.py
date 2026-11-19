import importlib.util
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "token_watch.py"
SPEC = importlib.util.spec_from_file_location("token_watch", MODULE_PATH)
token_watch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(token_watch)


def dex_data(chg_24h=0.0, ratio=1.0):
    return {
        "ok": True,
        "price": 0.01,
        "mc": 1_000_000,
        "liq": 100_000,
        "vol24": 24_000,
        "vol1h": 0,
        "chg_1h": 0,
        "chg_24h": chg_24h,
        "buys": 10,
        "sells": 10,
        "ratio": ratio,
        "pairs": 1,
        "dexes": 1,
        "pool_url": "https://example.invalid/pool",
    }


def test_rpc_failure_on_first_tick_is_unknown_and_retried(monkeypatch):
    state = {"tokens": {}}
    calls = []
    monkeypatch.setattr(token_watch, "fetch_dex", lambda mint: dex_data())
    monkeypatch.setattr(token_watch, "fetch_supply", lambda mint: 1_000_000)
    monkeypatch.setattr(token_watch, "fetch_authorities", lambda mint: calls.append(mint) or {})

    messages = token_watch.handle_token(token_watch.TOKENS[0], state)
    assert "Права минта: н/д | Права заморозки: н/д" in messages[0]
    assert "отозваны ✅" not in messages[0]
    token_state = state["tokens"][token_watch.TOKENS[0]["mint"]]
    assert "authorities" not in token_state

    token_watch.handle_token(token_watch.TOKENS[0], state)
    assert len(calls) == 2


def test_corrupt_state_is_backed_up_and_second_run_does_not_announce(monkeypatch, tmp_path, capsys):
    state_path = tmp_path / "token_watch_state.json"
    state_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(token_watch, "STATE_PATH", state_path)
    monkeypatch.setattr(token_watch, "fetch_dex", lambda mint: dex_data())
    monkeypatch.setattr(token_watch, "fetch_supply", lambda mint: 1_000_000)
    monkeypatch.setattr(token_watch, "fetch_authorities", lambda mint: {
        "mint_authority": None, "freeze_authority": None, "decimals": 6
    })
    monkeypatch.setattr(token_watch, "maybe_digest", lambda cfg, state: [])

    assert token_watch.main() == 0
    first = capsys.readouterr()
    assert "ВЗЯТ ПОД НАБЛЮДЕНИЕ" in first.out
    assert "повреждённый снапшот сохранён" in first.err
    assert list(tmp_path.glob("token_watch_state.json.corrupt-*"))

    assert token_watch.main() == 0
    second = capsys.readouterr()
    assert "ВЗЯТ ПОД НАБЛЮДЕНИЕ" not in second.out
    assert second.out == ""


def test_unwritable_state_suppresses_messages(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(token_watch, "STATE_PATH", tmp_path / "token_watch_state.json")
    monkeypatch.setattr(token_watch, "fetch_dex", lambda mint: dex_data())
    monkeypatch.setattr(token_watch, "fetch_supply", lambda mint: 1_000_000)
    monkeypatch.setattr(token_watch, "fetch_authorities", lambda mint: {})
    monkeypatch.setattr(token_watch, "maybe_digest", lambda cfg, state: [])
    monkeypatch.setattr(token_watch, "save_state", lambda state: False)

    assert token_watch.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "сообщения подавлены" in captured.err


def test_digest_verdict_uses_unchanged_fifteen_percent_threshold(monkeypatch):
    class DigestTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 19, token_watch.DIGEST_UTC_HOUR, tzinfo=timezone.utc)

    monkeypatch.setattr(token_watch, "datetime", DigestTime)
    monkeypatch.setattr(token_watch, "fetch_dex", lambda mint: dex_data(15.0, 1.0))
    state = {"tokens": {}}

    assert token_watch.DIGEST_TREND_PCT == 15.0
    assert "🟢 РАЗОГРЕВ" in token_watch.maybe_digest(token_watch.TOKENS[0], state)[0]

    state = {"tokens": {}}
    monkeypatch.setattr(token_watch, "fetch_dex", lambda mint: dex_data(-15.0, 1.0))
    assert "🔴 ОТКАТ" in token_watch.maybe_digest(token_watch.TOKENS[0], state)[0]
