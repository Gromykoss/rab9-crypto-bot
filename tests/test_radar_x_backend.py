#!/usr/bin/env python3
"""Тесты транспорта X-поиска в radar_x.py (карточка t_eb994c6a, 24.11.2026).

Офлайн: сеть подменяется. Проверяем:
1) off — ни одного запроса наружу (requests.get падает, если его позвали), снимок нейтральный;
2) off — lookup_account не ходит в API;
3) api — шейпер собирает посты/инфлюенсеров/предупреждения из ответа X API v2;
4) web — поиск через x_web.search_recent, лимит темпа (≤N/час), стоп на 401/403;
5) формат для Grok при off не меняется («X: нет данных.»).
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


radar_x = _load("radar_x", ROOT / "radar_x.py")


V2_PAYLOAD = {
    "data": [
        {
            "id": "1",
            "author_id": "u1",
            "text": "$WIF to the moon",
            "public_metrics": {"like_count": 5, "retweet_count": 2},
        },
        {
            "id": "2",
            "author_id": "u2",
            "text": "I voted YES for Moonshot listing, 3 more votes",
            "public_metrics": {"like_count": 1, "retweet_count": 0},
        },
    ],
    "includes": {
        "users": [
            {"id": "u1", "username": "Ansem", "public_metrics": {"followers_count": 700000}},
            {"id": "u2", "username": "spammer", "public_metrics": {"followers_count": 12}},
        ]
    },
}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Никаких живых вызовов и никаких файлов вне tmp_path."""
    monkeypatch.setenv("RADAR_X_BACKEND", "off")
    monkeypatch.setattr(radar_x, "WEB_RATE_PATH", tmp_path / "rate.json")
    monkeypatch.setattr(radar_x, "WEB_STOP_PATH", tmp_path / "stop.json")
    monkeypatch.setattr(radar_x, "WEB_MAX_PER_HOUR", 2)
    yield


def _boom(*_args, **_kwargs):
    raise AssertionError("off-режим не должен ходить в сеть")


# --------------------------------------------------------------------- off


def test_off_makes_no_network_call(monkeypatch):
    monkeypatch.setattr(radar_x.requests, "get", _boom)
    res = radar_x.search_x("WIF")
    assert res["ok"] is False
    assert res["api_called"] is False
    assert res["cacheable"] is False
    assert res["backend"] == "off"
    assert res["posts"] == [] and res["influencers"] == []


def test_off_lookup_account_no_network(monkeypatch):
    monkeypatch.setattr(radar_x.requests, "get", _boom)
    assert radar_x.lookup_account("@ansem") is None


def test_off_grok_format_unchanged(monkeypatch):
    res = radar_x.search_x("WIF")
    assert radar_x.format_for_grok(res) == "X: нет данных."


@pytest.mark.parametrize("value", ["off", "api", "web"])
def test_backend_reads_env(monkeypatch, value):
    monkeypatch.setenv("RADAR_X_BACKEND", value)
    assert radar_x.backend() == value
    assert radar_x.enabled() is (value != "off")


# --------------------------------------------------------------------- api


def test_api_shaper_builds_snapshot(monkeypatch):
    class _Resp:
        ok = True

        def json(self):
            return V2_PAYLOAD

    monkeypatch.setenv("RADAR_X_BACKEND", "api")
    monkeypatch.setattr(radar_x, "_load_oauth", lambda: object())
    monkeypatch.setattr(radar_x.requests, "get", lambda *a, **k: _Resp())
    res = radar_x.search_x("WIF")
    assert res["ok"] is True and res["backend"] == "api"
    assert res["count"] == 1  # vote-spam отфильтрован
    assert res["spam_detected"] == 1
    assert any("Ansem" in p for p in res["posts"])
    assert res["cacheable"] is True


def test_api_shaper_flags_kol_swarm(monkeypatch):
    payload = {
        "data": [
            {"id": "1", "author_id": "a", "text": "gm $WIF", "public_metrics": {}},
            {"id": "2", "author_id": "b", "text": "buying $WIF", "public_metrics": {}},
        ],
        "includes": {
            "users": [
                {"id": "a", "username": "whale1", "public_metrics": {"followers_count": 120000}},
                {"id": "b", "username": "whale2", "public_metrics": {"followers_count": 90000}},
            ]
        },
    }
    out = radar_x._shape_v2_result("WIF", payload["data"], {u["id"]: u for u in payload["includes"]["users"]}, [])
    assert out["count"] == 2
    assert any("KOL-SWARM" in w for w in out["kabal_warnings"])


# --------------------------------------------------------------------- web


def test_web_uses_x_web_and_limits_rate(monkeypatch):
    calls = []

    def _fake_search(query, count=20):
        calls.append((query, count))
        return 0, V2_PAYLOAD, ""

    monkeypatch.setenv("RADAR_X_BACKEND", "web")
    monkeypatch.setitem(sys.modules, "x_web", types.SimpleNamespace(search_recent=_fake_search))
    monkeypatch.setattr(radar_x, "WEB_MAX_PER_HOUR", 1)
    first = radar_x.search_x("WIF")
    second = radar_x.search_x("WIF")
    assert first["ok"] is True and first["backend"] == "web"
    assert first["count"] == 1
    assert second["ok"] is False and second["skipped"] == "rate_limit"
    assert len(calls) == 1


def test_web_stops_on_401(monkeypatch):
    monkeypatch.setenv("RADAR_X_BACKEND", "web")
    monkeypatch.setitem(
        sys.modules,
        "x_web",
        types.SimpleNamespace(search_recent=lambda query, count=20: (401, None, "unauthorized")),
    )
    res = radar_x.search_x("WIF")
    assert res["ok"] is False and res["backend"] == "web"
    assert radar_x.web_stop_reason()
    again = radar_x.search_x("WIF")
    assert again["skipped"] == "stopped"
