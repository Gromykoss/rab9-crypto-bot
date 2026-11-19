"""GWT-тесты спеки openspec/specs/pumpportal-ingress.md (v0.3 FROZEN).

По одному тесту на каждый `#### Scenario:`. Проверяется реальное поведение
pumpportal_listener.py через его публичные входы:

* `_session()` — живое соединение: подписка, ack-liveness, разбор событий,
  отправка POST в /msf-signal, повтор отложенных событий;
* `main()` — reconnect-цикл и backoff-политика при обрыве/таймаутах;
* `_post_signal()` / `_replay_failed()` / `_journal_*` — журнал неудач.

Герметичность: `websockets.connect` и `requests.post/get` подменены фейками
(фикстура `_hermetic` падает, если тест забудет подмену), все пути к данным
уведены в tmp_path, таймауты и backoff — миллисекунды. Реальной сети и
реальных файлов репозитория тесты не касаются.
"""
import asyncio
import json
import logging
import sys
import time
from unittest import mock

import pytest
import websockets
from websockets.frames import Close

sys.path.insert(0, "/home/hermes-workspace/rab9")

ADDR = "4EMfevH3bDfnThB8EeNfF9KPiSD9YhEvgiFtUYFaWdEr"
ADDR_DEFERRED_1 = "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"
ADDR_DEFERRED_2 = "DAqCpTpQN1JNCDYLXWir28q1J2eXSufiNNADsSnUQTBZ"
SECRET = "SUPERSECRET-XYZ"


# ── фейковый WS ──
class _FakeWS:
    """Соединение: подаёт заранее заданные кадры, помнит исходящие и закрытие.

    Пустой скрипт ≠ StopAsyncIteration для recv: `recv()` уходит в тишину
    (эмулирует «ack не пришёл»), а `__anext__` завершает поток — как закрытый
    сервером стрим.
    """

    def __init__(self, incoming=()):
        self.incoming = list(incoming)
        self.sent = []
        self.closed = False
        self.exit_exc = None
        self.opened_at = None

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if not self.incoming:
            await asyncio.Event().wait()  # тишина: реальный таймаут wait_for в _session
        item = self.incoming.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.incoming:
            raise StopAsyncIteration
        item = self.incoming.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def __aenter__(self):
        self.opened_at = time.monotonic()
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        self.exit_exc = exc
        return False


class _StopLoop(Exception):
    """Сигнал тесту: прогон бесконечного main() завершён (main её не ловит)."""


class _FakeConnect:
    """Фабрика соединений: N-й вызов `websockets.connect` берёт N-й скрипт.

    `stop_after=N` — реальный `pl.main()` бесконечен; на (N+1)-й попытке
    подключения фабрика бросает `_StopLoop`, которую main() не перехватывает,
    и прогон заканчивается детерминированно (без отмены задач по таймеру).
    """

    def __init__(self, scripts=(), stop_after=None):
        self.scripts = list(scripts)
        self.stop_after = stop_after
        self.attempts = []       # monotonic-метка каждой попытки подключения
        self.calls = []          # kwargs состоявшихся подключений
        self.conns = []          # _FakeWS по порядку подключений

    def __call__(self, url, **kwargs):
        self.attempts.append(time.monotonic())
        if self.stop_after is not None and len(self.attempts) > self.stop_after:
            raise _StopLoop()
        self.calls.append({"url": url, **kwargs})
        idx = len(self.conns)
        conn = _FakeWS(self.scripts[idx] if idx < len(self.scripts) else [])
        self.conns.append(conn)
        return conn


def _ack(text="Successfully subscribed to subscribeMigration"):
    return json.dumps({"message": text})


def _drop_exc():
    """Обрыв ровно того класса, который ловит main(): websockets.ConnectionClosed.

    Библиотека кидает его же при истечении ping-таймаута (half-open) и при
    падении recv — этим тестом эмулируется сам факт обрыва.
    """
    return websockets.ConnectionClosed(Close(1006, ""), None)


def _fake_response(status_code):
    return mock.Mock(status_code=status_code)


def _ok_post(seen):
    """POST-фейк ingress: 200 + запись фактического вызова."""

    def _post(url, json=None, headers=None, timeout=None):
        seen.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _fake_response(200)

    return _post


def _run_main(pl):
    """Прогон реального бесконечного `pl.main()` с детерминированной остановкой."""
    async def _runner():
        try:
            await pl.main()
        except _StopLoop:
            pass

    asyncio.run(_runner())


def _write_journal(path, addresses):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for i, addr in enumerate(addresses):
            f.write(json.dumps({"address": addr, "error": "ingress_unreachable",
                                "id": f"id{i}", "ts": time.time()}) + "\n")


def _journal_lines(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    """Изоляция: ни реальной сети, ни записей в репо, таймауты — миллисекунды."""
    import pumpportal_listener as pl

    def _forbidden(*a, **kw):
        raise AssertionError("hermetic: тест обратился к сети без подмены мока")

    monkeypatch.setattr(pl.websockets, "connect", _forbidden)
    monkeypatch.setattr(pl.requests, "post", _forbidden)
    monkeypatch.setattr(pl.requests, "get", _forbidden)

    monkeypatch.setattr(pl, "BASE_DIR", str(tmp_path))  # trades_stream / wallet_events
    monkeypatch.setattr(pl, "PPP_FAILED_FILE", str(tmp_path / "ingress_failed.jsonl"))
    monkeypatch.setattr(pl, "WALLET_FILE", str(tmp_path / "wallet_watch.json"))  # нет файла → []
    monkeypatch.setattr(pl, "PPP_WS_URL", "wss://pumpportal.invalid/api/data")
    monkeypatch.setattr(pl, "PPP_API_KEY", "")
    monkeypatch.setattr(pl, "PPP_INGRESS_URL", "http://ingress.invalid:8089")
    monkeypatch.setattr(pl, "PPP_MAX_POST_ATTEMPTS", 3)
    monkeypatch.setattr(pl, "PPP_POST_BACKOFF_S", 0.01)
    monkeypatch.setattr(pl, "PPP_RECONNECT_BACKOFF_S", 0.02)
    monkeypatch.setattr(pl, "PPP_RECONNECT_CAP_S", 0.04)
    monkeypatch.setattr(pl, "PPP_SUB_ACK_TIMEOUT_S", 0.05)
    monkeypatch.setattr(pl, "PPP_WS_PING_INTERVAL_S", 0.05)
    monkeypatch.setattr(pl, "PPP_WS_PING_TIMEOUT_S", 0.05)
    monkeypatch.setattr(pl, "PPP_REPLAY_DELAY_S", 0.01)
    monkeypatch.setattr(pl, "RAB9_HTTP_SECRET", SECRET)


# ── migration-ingest: миграция принята ──
@pytest.mark.scenario("pumpportal-ingress.migration_accepted")
def test_migration_accepted(tmp_path, monkeypatch, caplog):
    """GWT: живое WS + событие migration с валидным адресом → POST /msf-signal, ответ 200."""
    import pumpportal_listener as pl

    caplog.set_level(logging.INFO, logger="pumpportal_listener")
    posted = []
    monkeypatch.setattr(pl.requests, "post", _ok_post(posted))
    fake = _FakeConnect([[_ack(), json.dumps({"mint": ADDR})]])
    monkeypatch.setattr(pl.websockets, "connect", fake)

    asyncio.run(pl._session())

    assert fake.calls, "WS-соединение не устанавливалось"
    assert fake.calls[0]["url"] == pl.PPP_WS_URL
    assert len(posted) == 1, f"ожидался ровно один POST, было {len(posted)}"
    assert posted[0]["url"].endswith("/msf-signal")
    assert posted[0]["json"] == {"chain": "solana", "address": ADDR}
    assert posted[0]["headers"]["X-RAB9-SECRET"] == SECRET
    assert posted[0]["timeout"] == pl.PPP_HTTP_TIMEOUT_S  # не бесконечный
    # ответ 200 → статус обработки зафиксирован в логе
    assert f"ingest: {ADDR} accepted" in caplog.text
    # доставлено с первой попытки → журнал неудач не создаётся
    assert _journal_lines(tmp_path / "ingress_failed.jsonl") == []


# ── migration-ingest: событие без валидного адреса ──
@pytest.mark.scenario("pumpportal-ingress.invalid_address_filtered")
def test_invalid_address_filtered(tmp_path, monkeypatch, caplog):
    """GWT: событие с пустым/невалидным адресом → POST не отправляется."""
    import pumpportal_listener as pl

    caplog.set_level(logging.INFO, logger="pumpportal_listener")
    posted = []
    monkeypatch.setattr(pl.requests, "post", _ok_post(posted))
    fake = _FakeConnect([[
        _ack(),
        json.dumps({"mint": ""}),                 # пустой адрес
        json.dumps({"mint": "not-a-solana-addr"}),  # не base58/короткий
        json.dumps({"mint": "0OIl" * 11}),          # 44 символа, но 0/O/I/l вне base58
        json.dumps({"something": "else"}),          # адреса нет вовсе
    ]])
    monkeypatch.setattr(pl.websockets, "connect", fake)

    asyncio.run(pl._session())

    assert not pl.is_msf_solana_address("0OIl" * 11)
    assert fake.conns[0].sent == [{"method": "subscribeMigration"}]  # дошли до приёма событий
    assert posted == [], "POST отправлен для невалидного адреса"
    assert "accepted" not in caplog.text
    # отфильтрованное событие — не неудача ingress: в журнал оно не попадает
    assert _journal_lines(tmp_path / "ingress_failed.jsonl") == []


# ── ingress-failure-handling: ingress недоступен ──
@pytest.mark.scenario("pumpportal-ingress.ingress_down_journal")
def test_ingress_down_journal_survives_restart(tmp_path, monkeypatch, caplog):
    """GWT: таймаут ingress на 3 попытки → событие в data/ingress_failed.jsonl на диске."""
    import importlib

    import pumpportal_listener as pl

    caplog.set_level(logging.INFO, logger="pumpportal_listener")
    attempts = []

    def _timeout_post(url, json=None, headers=None, timeout=None):
        attempts.append(timeout)
        raise pl.requests.Timeout("ingress timeout")

    monkeypatch.setattr(pl.requests, "post", _timeout_post)
    journal = tmp_path / "ingress_failed.jsonl"

    delivered = asyncio.run(pl._post_signal(ADDR))

    assert delivered is False
    assert pl.PPP_MAX_POST_ATTEMPTS == 3
    assert len(attempts) == 3, "не исчерпаны 3 попытки"
    assert all(t == pl.PPP_HTTP_TIMEOUT_S for t in attempts)  # каждая попытка с явным таймаутом
    assert journal.exists(), "журнал неудач не создан"
    recs = _journal_lines(journal)
    assert len(recs) == 1
    assert recs[0]["address"] == ADDR
    assert recs[0]["error"] == "ingress_unreachable"
    assert recs[0]["id"] and isinstance(recs[0]["ts"], float)

    # «рестарт процесса»: модуль переимпортируется, путь к журналу берётся из окружения
    monkeypatch.setenv("PPP_FAILED_FILE", str(journal))
    importlib.reload(pl)
    monkeypatch.setattr(pl, "RAB9_HTTP_SECRET", SECRET)
    assert pl.PPP_FAILED_FILE == str(journal)  # тот же файл после рестарта
    assert any(json.loads(line)["address"] == ADDR for line in pl._journal_load())


# ── ingress-failure-handling: восстановление ingress ──
@pytest.mark.scenario("pumpportal-ingress.ingress_recovery_replay")
def test_ingress_recovery_replay(tmp_path, monkeypatch, caplog):
    """GWT: непустой журнал + ingress отвечает 200 → отложенные события переотправлены, файл очищен."""
    import pumpportal_listener as pl

    caplog.set_level(logging.INFO, logger="pumpportal_listener")
    journal = tmp_path / "ingress_failed.jsonl"
    _write_journal(journal, [ADDR_DEFERRED_1, ADDR_DEFERRED_2])
    assert len(_journal_lines(journal)) == 2  # GIVEN: журнал непуст

    monkeypatch.setattr(pl.requests, "get", lambda url, timeout=None: _fake_response(200))
    assert pl._health_sync() is True, "GIVEN: ingress отвечает 200 на health-check"

    posted = []
    monkeypatch.setattr(pl.requests, "post", _ok_post(posted))
    fake = _FakeConnect([[_ack(), json.dumps({"mint": ADDR})]])
    monkeypatch.setattr(pl.websockets, "connect", fake)

    asyncio.run(pl._session())

    assert [p["json"]["address"] for p in posted] == [ADDR, ADDR_DEFERRED_1, ADDR_DEFERRED_2]
    assert all(p["url"].endswith("/msf-signal") for p in posted)
    assert _journal_lines(journal) == [], "журнал не очищен после успешной переотправки"
    assert journal.read_text() == ""
    assert caplog.text.count("replay: delivered") == 2


# ── resilient-connection: обрыв соединения ──
@pytest.mark.scenario("pumpportal-ingress.reconnect_after_drop")
def test_reconnect_after_drop(tmp_path, monkeypatch, caplog):
    """GWT: WS закрывается → подписка восстановлена, события после реконнекта обрабатываются."""
    import pumpportal_listener as pl

    caplog.set_level(logging.INFO, logger="pumpportal_listener")
    posted = []
    monkeypatch.setattr(pl.requests, "post", _ok_post(posted))
    fake = _FakeConnect(
        [
            [_ack(), _drop_exc()],                  # соединение 1: обрыв на recv
            [_ack(), json.dumps({"mint": ADDR})],   # соединение 2: живое
        ],
        stop_after=2,
    )
    monkeypatch.setattr(pl.websockets, "connect", fake)

    _run_main(pl)

    assert len(fake.conns) == 2, "реконнект не состоялся"
    assert fake.conns[0].closed, "оборванное соединение не закрыто"
    # активная подписка восстановлена: subscribeMigration отправлен заново
    assert [s["method"] for s in fake.conns[1].sent] == ["subscribeMigration"]
    # критерий спеки: восстановление не позднее 70с от обрыва
    assert fake.attempts[1] - fake.attempts[0] < 70.0
    assert fake.attempts[1] - fake.attempts[0] >= pl.PPP_RECONNECT_BACKOFF_S * 0.9
    # события после реконнекта обрабатываются
    assert [p["json"]["address"] for p in posted] == [ADDR]
    assert "WS down: ConnectionClosed" in caplog.text


# ── subscription-liveness: ack получен ──
@pytest.mark.scenario("pumpportal-ingress.sub_ack_received")
def test_sub_ack_received(tmp_path, monkeypatch, caplog):
    """GWT: send subscribeMigration + ack сервера → «subscription active» с текущей меткой."""
    import pumpportal_listener as pl

    caplog.set_level(logging.INFO, logger="pumpportal_listener")
    fake = _FakeConnect([[_ack()]])
    monkeypatch.setattr(pl.websockets, "connect", fake)

    started = time.time()
    asyncio.run(pl._session())

    assert fake.conns[0].sent == [{"method": "subscribeMigration"}]
    active = [r for r in caplog.records if "subscription active" in r.getMessage()]
    assert active, "нет лога «subscription active» после ack"
    assert "subscription active (1/1)" in active[0].getMessage()
    assert started <= active[0].created <= time.time() + 1  # метка времени текущая
    assert fake.conns[0].closed


# ── subscription-liveness: ack не пришёл ──
@pytest.mark.scenario("pumpportal-ingress.sub_ack_timeout")
def test_sub_ack_timeout(tmp_path, monkeypatch, caplog):
    """GWT: ack нет за PPP_SUB_ACK_TIMEOUT_S → соединение закрыто, инициирован reconnect."""
    import pumpportal_listener as pl

    caplog.set_level(logging.INFO, logger="pumpportal_listener")
    fake = _FakeConnect([[], []], stop_after=1)  # ни одного кадра: ack не приходит
    monkeypatch.setattr(pl.websockets, "connect", fake)

    _run_main(pl)

    assert len(fake.attempts) == 2, "reconnect по backoff-политике не инициирован"
    assert fake.conns[0].closed, "соединение без ack не закрыто"
    assert "session timeout (no sub ack / recv timeout)" in caplog.text
    assert caplog.text.count("connecting") == 2  # лог попытки следующего подключения (backoff)
    # повтор подключения — не раньше backoff-паузы
    assert fake.attempts[1] - fake.attempts[0] >= pl.PPP_RECONNECT_BACKOFF_S * 0.9
    assert fake.conns[0].sent == [{"method": "subscribeMigration"}]


# ── ws-keepalive: half-open соединение ──
@pytest.mark.scenario("pumpportal-ingress.ping_timeout_close")
def test_ping_timeout_close(tmp_path, monkeypatch, caplog):
    """GWT: peer не отвечает на ping, ping timeout истёк → локальное закрытие + reconnect-цикл."""
    import pumpportal_listener as pl

    caplog.set_level(logging.INFO, logger="pumpportal_listener")
    fake = _FakeConnect([[_ack(), _drop_exc()]], stop_after=1)
    monkeypatch.setattr(pl.websockets, "connect", fake)

    _run_main(pl)

    # keepalive включён и сконфигурирован (истечение ping-timeout → ConnectionClosed)
    assert fake.calls[0]["ping_interval"] == pl.PPP_WS_PING_INTERVAL_S == 0.05
    assert fake.calls[0]["ping_timeout"] == pl.PPP_WS_PING_TIMEOUT_S == 0.05
    assert fake.calls[0]["open_timeout"] == pl.PPP_HTTP_TIMEOUT_S
    assert fake.conns[0].closed, "half-open соединение не закрыто локально"
    assert "WS down: ConnectionClosed" in caplog.text
    # запущен reconnect-цикл: есть попытка повторного подключения после backoff
    assert len(fake.attempts) == 2, "reconnect-цикл не запущен"
    assert fake.attempts[1] - fake.attempts[0] >= pl.PPP_RECONNECT_BACKOFF_S * 0.9


# ── secret-hygiene: лог-чистота ──
@pytest.mark.scenario("pumpportal-ingress.secret_never_logged")
def test_secret_never_logged(tmp_path, monkeypatch, caplog):
    """GWT: любой путь (включая ошибки) → секрет отсутствует в логе и в файлах данных."""
    import pumpportal_listener as pl

    caplog.set_level(logging.DEBUG, logger="pumpportal_listener")
    monkeypatch.setattr(pl, "RAB9_HTTP_SECRET", SECRET)
    monkeypatch.setattr(pl, "PPP_API_KEY", SECRET)  # ключ PumpPortal — тоже маркер
    monkeypatch.setattr(pl, "PPP_WS_URL", f"wss://pumpportal.invalid/api/data?api-key={SECRET}")
    monkeypatch.setattr(pl, "PPP_MAX_POST_ATTEMPTS", 2)
    monkeypatch.setattr(pl, "PPP_POST_BACKOFF_S", 0.01)

    def _leaky_post(url, json=None, headers=None, timeout=None):
        assert headers["X-RAB9-SECRET"] == SECRET  # секрет реально используется (позитивный контроль)
        raise pl.requests.ConnectionError(f"401 unauthorized (secret={SECRET})")

    monkeypatch.setattr(pl.requests, "post", _leaky_post)

    # путь 1: ошибки ingress с секретом внутри текста исключения → журнал неудач
    assert asyncio.run(pl._post_signal(ADDR)) is False
    # путь 2: невалидное событие + обрыв WS → reconnect-цикл (лог ошибок)
    fake = _FakeConnect([[_ack(), json.dumps({"mint": "bad-address"}), _drop_exc()]], stop_after=1)
    monkeypatch.setattr(pl.websockets, "connect", fake)
    _run_main(pl)

    # THEN: секрет отсутствует в выводе лога
    assert caplog.text, "лог пуст — проверка гигиены ничего не значит"
    assert "POST /msf-signal" in caplog.text and "WS down" in caplog.text  # оба пути реально логировались
    assert SECRET not in caplog.text
    # и не пишется в файлы данных
    leaked_files = [
        str(p) for p in tmp_path.rglob("*")
        if p.is_file() and SECRET in p.read_text(errors="ignore")
    ]
    assert leaked_files == []
    journaled = _journal_lines(tmp_path / "ingress_failed.jsonl")
    assert [r["address"] for r in journaled] == [ADDR]
