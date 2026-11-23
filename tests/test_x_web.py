#!/usr/bin/env python3
"""Тесты веб-читалки X (x_web.py) и совместимости с трекером.

Офлайн: сеть не нужна — GraphQL-ответы подменяются фикстурами той же формы, что
отдаёт веб-клиент x.com (замерено 23.11.2026 на живых вызовах). Проверяем:
1) сборку payload в форме X API v2 (данные, которые ждёт трекер);
2) диспетчер xurl-совместимых вызовов (user / search / v2-пути);
3) перевод оператора retweets_of → filter:nativeretweets;
4) деградацию без cookies и без резолвера queryId;
5) что трекер принимает наши payload'ы (extract_catalysts) и печатает ошибки.
"""

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


x_web = _load("x_web", ROOT / "x_web.py")


# ---------------------------------------------------------------- фикстуры GraphQL


def gql_user(screen_name="BurnieSendersX", followers=27150, rest_id="2037254626060234752",
             verified=True):
    return {
        "__typename": "User",
        "rest_id": rest_id,
        "core": {
            "screen_name": screen_name,
            "name": screen_name,
            "created_at": "Thu Mar 26 19:45:34 +0000 2026",
        },
        "relationship_counts": {"followers": followers, "following": 378},
        "tweet_counts": {"tweets": 3983, "media_tweets": 2559},
        "is_blue_verified": verified,
    }


def gql_tweet(rest_id="1", text="hello $BURNIE", created="Sun Nov 22 01:01:13 +0000 2026",
              author=None, rt_of=None, quoted=None, reply_uid=None, likes=1, rts=0,
              replies=0, quotes=0, views=None, note=None):
    legacy = {
        "full_text": text,
        "created_at": created,
        "favorite_count": likes,
        "retweet_count": rts,
        "reply_count": replies,
        "quote_count": quotes,
    }
    if rt_of:
        legacy["retweeted_status_result"] = {"result": {"rest_id": rt_of}}
    if quoted:
        legacy["quoted_status_id_str"] = quoted
    if reply_uid:
        legacy["in_reply_to_user_id_str"] = reply_uid
        legacy["in_reply_to_screen_name"] = "BurnieSendersX"
    node = {
        "__typename": "Tweet",
        "rest_id": rest_id,
        "legacy": legacy,
        "core": {"user_results": {"result": author or gql_user()}},
    }
    if note:
        node["note_tweet"] = {"note_tweet_results": {"result": {"text": note}}}
    if views is not None:
        node["views"] = {"count": views}
    return node


def timeline_payload(tweets):
    entries = [
        {"content": {"__typename": "TimelineTweet", "itemContent": {"tweet_results": {"result": t}}}}
        for t in tweets
    ]
    return {
        "data": {
            "user": {
                "result": {
                    "timeline": {"timeline": {"instructions": [{"entries": entries}]}}
                }
            }
        }
    }


def search_payload(tweets):
    entries = [
        {"content": {"__typename": "TimelineTweet", "itemContent": {"tweet_results": {"result": t}}}}
        for t in tweets
    ]
    return {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {"timeline": {"instructions": [{"entries": entries}]}}
            }
        }
    }


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    monkeypatch.setattr(x_web, "_QUERY_IDS_MEM", {})
    monkeypatch.setattr(x_web, "_REPOST_CACHE", {"ts": 0.0, "by_orig": {}, "empty": False})
    monkeypatch.setattr(x_web, "_read_cache", lambda: dict(x_web.DEFAULT_QUERY_IDS))
    yield


# ---------------------------------------------------------------- 1. сборка payload


def test_user_payload_is_v2_shaped():
    user = x_web._v2_user(gql_user(followers=27150))
    assert user["id"] == "2037254626060234752"
    assert user["username"] == "BurnieSendersX"
    assert user["public_metrics"]["followers_count"] == 27150
    assert user["verified"] is True and user["verified_type"] == "blue"


def test_tweet_payload_matches_v2_fields(monkeypatch):
    node = gql_tweet(
        rest_id="99",
        text="RT @BurnieSendersX: gm",
        rt_of="5",
        quoted="7",
        reply_uid="42",
        likes=11,
        rts=3,
        replies=2,
        quotes=1,
        views=1234,
    )
    post = x_web._v2_tweet(node)
    assert post["id"] == "99"
    assert post["created_at"] == "2026-11-22T01:01:13Z"
    assert post["author_id"] == "2037254626060234752"
    assert post["in_reply_to_user_id"] == "42"
    assert post["public_metrics"] == {
        "retweet_count": 3,
        "reply_count": 2,
        "like_count": 11,
        "quote_count": 1,
        "bookmark_count": 0,
        "impression_count": 1234,
    }
    assert {"type": "retweeted", "id": "5"} in post["referenced_tweets"]
    assert {"type": "quoted", "id": "7"} in post["referenced_tweets"]
    assert {"type": "replied_to", "id": "42"} in post["referenced_tweets"]


def test_long_text_comes_from_note_tweet():
    post = x_web._v2_tweet(gql_tweet(text="обрезанный t.co", note="полный длинный текст поста"))
    assert post["text"] == "полный длинный текст поста"


def test_collect_dedupes_and_keeps_order():
    payload = search_payload([gql_tweet(rest_id="1"), gql_tweet(rest_id="2"), gql_tweet(rest_id="1")])
    posts, users = x_web._payload_from_response(payload)
    assert [p["id"] for p in posts] == ["1", "2"]
    assert len(users) == 1  # автор один и тот же — без дублей


# ---------------------------------------------------------------- 2. диспетчер вызовов


def test_run_compat_user(monkeypatch):
    monkeypatch.setattr(x_web, "_gql", lambda op, variables, timeout=30: (200, {"data": {"user": {"result": gql_user()}}}, ""))
    code, payload, err = x_web.run_compat(["user", "BurnieSendersX"])
    assert code == 0 and payload["data"]["public_metrics"]["followers_count"] == 27150


def test_run_compat_search_cli(monkeypatch):
    seen = {}

    def fake_gql(op, variables, timeout=30):
        seen.update(variables)
        return 200, search_payload([gql_tweet(rest_id="11")]), ""

    monkeypatch.setattr(x_web, "_gql", fake_gql)
    code, payload, err = x_web.run_compat(["search", "BURNIE", "-n", "10"])
    assert code == 0 and payload["data"][0]["id"] == "11"
    assert seen["rawQuery"] == "BURNIE"


def test_run_compat_v2_timeline_path(monkeypatch):
    monkeypatch.setattr(x_web, "_gql", lambda op, variables, timeout=30: (200, timeline_payload([gql_tweet(rest_id="777")]), ""))
    code, payload, err = x_web.run_compat([
        "/2/users/2037254626060234752/tweets?max_results=10&tweet.fields=created_at,public_metrics,author_id"
    ])
    assert code == 0 and payload["data"][0]["id"] == "777"
    assert payload["includes"]["users"][0]["username"] == "BurnieSendersX"


def test_run_compat_v2_search_path(monkeypatch):
    monkeypatch.setattr(x_web, "_gql", lambda op, variables, timeout=30: (200, search_payload([gql_tweet(rest_id="12")]), ""))
    code, payload, err = x_web.run_compat([
        "/2/tweets/search/recent?query=BurnieSendersX&max_results=15&expansions=author_id"
    ])
    assert code == 0 and payload["data"][0]["id"] == "12"


def test_run_compat_retweeted_by_uses_repost_index(monkeypatch):
    monkeypatch.setattr(x_web, "_repost_index", lambda timeout=30: {"5": [x_web._v2_user(gql_user("kev_1602", followers=562))]})
    code, payload, err = x_web.run_compat(["/2/tweets/5/retweeted_by?user.fields=username,public_metrics"])
    assert code == 0
    assert payload["data"][0]["username"] == "kev_1602"
    assert payload["data"][0]["public_metrics"]["followers_count"] == 562


def test_run_compat_unknown_path_fails_softly():
    code, payload, err = x_web.run_compat(["xurl-something"])
    assert code != 0 and payload["status"] is None and "не поддержан" in payload["title"]


# ---------------------------------------------------------------- 3. операторы поиска


def test_retweets_of_translated_to_filter_nativeretweets():
    assert x_web._web_query("retweets_of:BurnieSendersX") == "BurnieSendersX filter:nativeretweets"


def test_plain_query_untouched():
    assert x_web._web_query("BURNIE") == "BURNIE"
    assert x_web._web_query("$BURNIE") == "$BURNIE"


# ---------------------------------------------------------------- 4. деградация


def test_missing_cookies_raise(monkeypatch):
    monkeypatch.delenv("TWITTER_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_CT0", raising=False)
    monkeypatch.setattr(x_web, "_ENV_FILES", ())
    with pytest.raises(x_web.XWebAuthError):
        x_web.creds()


def test_query_ids_fall_back_when_bundle_unavailable(monkeypatch):
    monkeypatch.setattr(x_web, "_read_cache", lambda: None)
    monkeypatch.setattr(x_web, "_http_get", lambda *a, **kw: (_ for _ in ()).throw(OSError("нет сети")))
    ids = x_web.resolve_query_ids(force=True)
    assert ids == x_web.DEFAULT_QUERY_IDS
    assert set(ids) == set(x_web.WANTED_OPS)


def test_http_error_maps_to_status_and_title(monkeypatch):
    import urllib.error

    def boom(op, variables, timeout=30):
        return 402, None, "HTTP 402 Payment Required"

    monkeypatch.setattr(x_web, "_gql", boom)
    code, payload, err = x_web.run_compat(["user", "BurnieSendersX"])
    assert code == 402 and payload["status"] == 402 and "402" in payload["title"]


def test_parse_env_file_reads_quotes(tmp_path):
    env = tmp_path / ".env"
    env.write_text('TWITTER_AUTH_TOKEN="abc"\n# comment\nTWITTER_CT0=def\nBAD_LINE\n', encoding="utf-8")
    parsed = x_web._parse_env_file(env)
    assert parsed["TWITTER_AUTH_TOKEN"] == "abc" and parsed["TWITTER_CT0"] == "def"
    assert "BAD_LINE" not in parsed


def test_iso_variants():
    assert x_web._iso("Sun Nov 22 01:01:13 +0000 2026") == "2026-11-22T01:01:13Z"
    assert x_web._iso("2026-11-22T01:01:13.000Z") == "2026-11-22T01:01:13Z"
    assert x_web._iso("") == ""


# ---------------------------------------------------------------- 5. стык с трекером


def test_tracker_consumes_our_payload(monkeypatch):
    tracker = _load("burnie_sentiment_tracker", ROOT / "burnie_sentiment_tracker.py")
    kol = gql_user("WhaleAlerts", followers=120000)
    posts = x_web._payload_from_response(
        search_payload([
            gql_tweet(rest_id="501", text="@BurnieSendersX is cooking $BURNIE", author=kol, likes=400, rts=90),
            gql_tweet(rest_id="502", text="gm", author=gql_user("micro_guy", followers=12)),
        ])
    )
    payload = x_web._wrap(*posts)
    catalysts = tracker.extract_catalysts(payload)
    assert catalysts and catalysts[0]["user"] == "WhaleAlerts"
    assert catalysts[0]["tier"] == "large"
    assert catalysts[0]["followers"] == 120000


def test_tracker_reports_web_errors(monkeypatch):
    tracker = _load("burnie_sentiment_tracker", ROOT / "burnie_sentiment_tracker.py")
    err = tracker.first_error("negative scan", 402, {"status": 402, "title": "web SearchTimeline: HTTP 402"}, "")
    assert err and "402" in err and "negative scan" in err
