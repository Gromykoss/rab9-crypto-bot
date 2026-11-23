#!/usr/bin/env python3
"""Чтение X через веб-сессию (cookies → внутренний GraphQL x.com) вместо платного X API.

Зачем (23.11.2026): X API начал отдавать `402 Payment Required · credits depleted`
на ВСЕ чтения (поиск, профиль, таймлайн), хотя ключи живы и валидны. Пока владелец
разбирался с балансом, трекер сентимента BURNIE два прогона подряд (22.11 15:00 UTC,
23.11 03:00 UTC) приходил без X-данных. Распоряжение владельца (23.11): «уйду от
платного API» — читать X веб-сессией, кредиты X API не нужны вообще.

Как это работает: те же данные, что отдавал API v2, собираются из внутреннего
GraphQL веб-клиента x.com — POST на `/i/api/graphql/<queryId>/<Operation>` с cookies
`auth_token` + `ct0` (из .env профиля rab9) и публичным веб-bearer фронтенда.
GET для этих операций отдаёт 404, поэтому только POST (замерено 23.11.2026).

queryId операций меняются с релизами фронтенда, поэтому модуль резолвит их из
бандла `main.<hash>.js` и кэширует в `data/x_web_queryids.json` (TTL 6ч), с жёстким
fallback на замеренные значения — падение резолвера не ломает прогон.

Форма ответа — X API v2 (`data`, `includes.users`, `public_metrics`,
`referenced_tweets`), чтобы вызывающий код трекера не менялся.

Границы: READ-ONLY. Никаких write-операций (правило AGENTS.md: X/Twitter write
для rab9 запрещён — публикация только у robot-man). Живые X API-креды не нужны.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "x_web_queryids.json"
QUERY_IDS_TTL = 6 * 3600

# Публичный bearer веб-клиента x.com (не секрет: тот же токен отдаёт фронтенд всем).
WEB_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Замерено 23.11.2026 из main.394feab1cb309e80a.js — fallback, если резолвер не смог.
DEFAULT_QUERY_IDS = {
    "UserByScreenName": "AMIBMjtxEEATh4z8V9GtRg",
    "UserTweets": "D6z-FJI2pKuwEeYYxVIGbg",
    "SearchTimeline": "vLHjqbDv7TPFMBkIIO1nOA",
    "UsersByRestIds": "ubfbnAM4qTlMTOYleYhXSg",
}
WANTED_OPS = tuple(DEFAULT_QUERY_IDS)
QUERY_ID_CACHE_TTL = QUERY_IDS_TTL

ACCOUNT_DEFAULT = "BurnieSendersX"
_account = ACCOUNT_DEFAULT

# Веб-поиск отдаёт одну страницу ≈20 постов (X-side), больше не просим.
WEB_PAGE_MAX = 20
# Кэш «кто ретвитнул»: один поиск репостов аккаунта покрывает все горячие посты прогона.
REPOST_CACHE_TTL = 300

_ENV_FILES = (
    Path("/home/hermes-workspace/.hermes/profiles/rab9/.env"),
    ROOT / ".env",
)


class XWebAuthError(RuntimeError):
    """Cookie-сессия X недоступна/протухла."""


def set_account(screen_name: str) -> None:
    """Официальный аккаунт проекта — нужен для поиска репостов (filter:nativeretweets)."""
    global _account
    if screen_name:
        _account = screen_name.lstrip("@")


def account() -> str:
    return _account


# ---------------------------------------------------------------- credentials


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                out[key] = value
    except OSError:
        pass
    return out


def creds() -> tuple[str, str]:
    """(auth_token, ct0). Сначала окружение, затем .env профиля rab9 / репо."""
    auth = (os.environ.get("TWITTER_AUTH_TOKEN") or "").strip()
    ct0 = (os.environ.get("TWITTER_CT0") or "").strip()
    if auth and ct0:
        return auth, ct0
    for path in _ENV_FILES:
        data = _parse_env_file(path)
        auth = auth or (data.get("TWITTER_AUTH_TOKEN") or "").strip()
        ct0 = ct0 or (data.get("TWITTER_CT0") or "").strip()
        if auth and ct0:
            break
    if not (auth and ct0):
        raise XWebAuthError(
            "нет cookies X (TWITTER_AUTH_TOKEN/TWITTER_CT0) — проверь .env профиля rab9"
        )
    return auth, ct0


def _headers(referer: str = "https://x.com/") -> dict[str, str]:
    auth, ct0 = creds()
    return {
        "authorization": f"Bearer {WEB_BEARER}",
        "x-csrf-token": ct0,
        "cookie": f"auth_token={auth}; ct0={ct0}",
        "user-agent": UA,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "content-type": "application/json",
        "accept": "*/*",
        "referer": referer,
    }


# ---------------------------------------------------------------- query ids


def _extract_query_ids(bundle: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    # Оба порядка встречаются в бандле: operationName ↔ queryId.
    for op, qid in re.findall(
        r'operationName:"([A-Za-z0-9_]+)"[^}]{0,120}?queryId:"([A-Za-z0-9_\-]{15,40})"', bundle
    ):
        pairs.setdefault(op, qid)
    for qid, op in re.findall(
        r'queryId:"([A-Za-z0-9_\-]{15,40})"[^}]{0,120}?operationName:"([A-Za-z0-9_]+)"', bundle
    ):
        pairs.setdefault(op, qid)
    return {op: pairs[op] for op in WANTED_OPS if op in pairs}


def _http_get(url: str, timeout: int, headers: dict[str, str] | None = None) -> str:
    req = urllib.request.Request(url, headers=headers or {"user-agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _read_cache() -> dict[str, str] | None:
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if time.time() - float(data.get("ts") or 0) < QUERY_ID_CACHE_TTL:
            ids = data.get("ids") or {}
            if isinstance(ids, dict) and all(op in ids for op in WANTED_OPS):
                return {op: str(ids[op]) for op in WANTED_OPS}
    except (OSError, ValueError, TypeError):
        pass
    return None


def _write_cache(ids: dict[str, str]) -> None:
    """Атомарная запись (CP-5: chmod до os.replace)."""
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts": time.time(), "ids": ids}), encoding="utf-8")
        os.chmod(tmp, 0o644)
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass


_QUERY_IDS_MEM: dict[str, str] = {}


def resolve_query_ids(force: bool = False, timeout: int = 30) -> dict[str, str]:
    """queryId операций из бандла фронтенда → кэш → fallback (замеренные значения)."""
    if not force and _QUERY_IDS_MEM:
        return dict(_QUERY_IDS_MEM)
    if not force:
        cached = _read_cache()
        if cached:
            _QUERY_IDS_MEM.update(cached)
            return dict(cached)
    ids: dict[str, str] = {}
    try:
        html = _http_get(f"https://x.com/{_account}", timeout)
        match = re.search(
            r"https://abs\.twimg\.com/responsive-web/client-web/main\.[a-f0-9]+\.js", html
        )
        if match:
            bundle = _http_get(match.group(0), timeout)
            ids = _extract_query_ids(bundle)
            if ids:
                _write_cache(ids)
    except Exception:
        ids = {}
    if not ids:
        ids = dict(DEFAULT_QUERY_IDS)
    _QUERY_IDS_MEM.clear()
    _QUERY_IDS_MEM.update(ids)
    return dict(ids)


# ---------------------------------------------------------------- graphql core


def _gql(op: str, variables: dict[str, Any], timeout: int = 30) -> tuple[int, Any, str]:
    """POST GraphQL. Возвращает (http_status, payload|None, error_text)."""
    try:
        headers = _headers()
    except XWebAuthError as exc:
        return 0, None, str(exc)
    qid = resolve_query_ids().get(op)
    if not qid:
        return 0, None, f"web: queryId для {op} не найден"
    body = json.dumps({"variables": variables, "features": {}, "queryId": qid}).encode()
    req = urllib.request.Request(
        f"https://x.com/i/api/graphql/{qid}/{op}", data=body, method="POST", headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace")), ""
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:
            detail = ""
        return exc.code, None, f"HTTP {exc.code} {detail}".strip()
    except Exception as exc:  # таймаут/сеть
        return 0, None, f"{type(exc).__name__}: {exc}"


def _fail(status: int, title: str, raw: str) -> tuple[int, dict[str, Any], str]:
    code = int(status) if int(status or 0) else 1
    return code, {"status": int(status or 0) or None, "title": title}, raw[:300]


# ---------------------------------------------------------------- shaping (v2)


def _iso(created_at: str) -> str:
    """'Sun Nov 22 01:01:13 +0000 2026' → '2026-11-22T01:01:13Z' (форма X API v2)."""
    raw = (created_at or "").strip()
    if not raw:
        return ""
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw, fmt).astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except ValueError:
            continue
    return ""


def _v2_user(node: dict[str, Any] | None) -> dict[str, Any]:
    """GraphQL user.result → объект user в форме X API v2."""
    node = node or {}
    core = node.get("core") or {}
    rel = node.get("relationship_counts") or {}
    legacy = node.get("legacy") or {}
    followers = rel.get("followers")
    if followers is None:
        followers = legacy.get("followers_count")
    following = rel.get("following")
    if following is None:
        following = legacy.get("friends_count")
    tweets = legacy.get("statuses_count")
    if tweets is None:
        tweets = (node.get("tweet_counts") or {}).get("tweets")
    if tweets is None:
        tweets = (node.get("action_counts") or {}).get("tweets_count")
    verified = bool(node.get("is_blue_verified") or legacy.get("verified"))
    return {
        "id": str(node.get("rest_id") or legacy.get("id_str") or ""),
        "username": core.get("screen_name") or legacy.get("screen_name") or "",
        "name": core.get("name") or legacy.get("name") or "",
        "public_metrics": {
            "followers_count": int(followers or 0),
            "following_count": int(following or 0),
            "tweet_count": int(tweets or 0),
            "listed_count": int(legacy.get("listed_count") or 0),
        },
        "verified": verified,
        "verified_type": "blue" if verified else "",
        "created_at": _iso(core.get("created_at") or ""),
        "description": (legacy.get("description") or ""),
    }


def _user_from_tweet(tweet: dict[str, Any]) -> dict[str, Any] | None:
    core = tweet.get("core") or {}
    node = (core.get("user_results") or {}).get("result")
    if isinstance(node, dict):
        return _v2_user(node)
    return None


def _v2_tweet(tweet: dict[str, Any]) -> dict[str, Any]:
    """GraphQL tweet.result → пост в форме X API v2 (text/created_at/public_metrics/refs)."""
    legacy = tweet.get("legacy") or {}
    text = legacy.get("full_text") or ""
    note = ((tweet.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {}
    if note.get("text"):
        text = note["text"]
    refs: list[dict[str, str]] = []
    rt_node = (legacy.get("retweeted_status_result") or {}).get("result") or {}
    rt_id = rt_node.get("rest_id") or legacy.get("retweeted_status_id_str")
    if rt_id:
        refs.append({"type": "retweeted", "id": str(rt_id)})
    q_node = (legacy.get("quoted_status_result") or {}).get("result") or {}
    q_id = q_node.get("rest_id") or legacy.get("quoted_status_id_str")
    if q_id:
        refs.append({"type": "quoted", "id": str(q_id)})
    reply_uid = legacy.get("in_reply_to_user_id_str") or legacy.get("in_reply_to_user_id")
    if reply_uid:
        refs.append({"type": "replied_to", "id": str(reply_uid)})

    author = _user_from_tweet(tweet) or {}
    metrics = {
        "retweet_count": int(legacy.get("retweet_count") or 0),
        "reply_count": int(legacy.get("reply_count") or 0),
        "like_count": int(legacy.get("favorite_count") or 0),
        "quote_count": int(legacy.get("quote_count") or 0),
        "bookmark_count": int(legacy.get("bookmark_count") or 0),
    }
    views = tweet.get("views") or {}
    if isinstance(views, dict) and views.get("count") is not None:
        metrics["impression_count"] = int(views.get("count") or 0)

    post: dict[str, Any] = {
        "id": str(tweet.get("rest_id") or legacy.get("id_str") or ""),
        "text": text,
        "created_at": _iso(legacy.get("created_at") or ""),
        "public_metrics": metrics,
        "author_id": author.get("id") or "",
        "referenced_tweets": refs,
    }
    if reply_uid:
        post["in_reply_to_user_id"] = str(reply_uid)
    if legacy.get("in_reply_to_screen_name"):
        post["in_reply_to_screen_name"] = legacy.get("in_reply_to_screen_name")
    if legacy.get("lang"):
        post["lang"] = legacy.get("lang")
    return post


def _collect_tweets(obj: Any, out: list[dict[str, Any]], depth: int = 0) -> None:
    """Собрать все tweet_results.result в дереве ответа (порядок обхода сохраняется)."""
    if depth > 14:
        return
    if isinstance(obj, dict):
        node = obj.get("tweet_results")
        if isinstance(node, dict):
            result = node.get("result")
            if isinstance(result, dict):
                out.append(result)
        for value in obj.values():
            _collect_tweets(value, out, depth + 1)
    elif isinstance(obj, list):
        for value in obj:
            _collect_tweets(value, out, depth + 1)


def _payload_from_response(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(посты v2, пользователи v2) из произвольного GraphQL-ответа с твитами."""
    raw_tweets: list[dict[str, Any]] = []
    _collect_tweets(payload, raw_tweets)
    posts: list[dict[str, Any]] = []
    users: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for node in raw_tweets:
        post = _v2_tweet(node)
        if not post["id"] or post["id"] in seen:
            continue
        seen.add(post["id"])
        posts.append(post)
        author = _user_from_tweet(node)
        if author and author["id"]:
            users.setdefault(author["id"], author)
    return posts, list(users.values())


def _wrap(posts: list[dict[str, Any]], users: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "data": posts,
        "includes": {"users": users},
        "meta": {"result_count": len(posts)},
    }


# ---------------------------------------------------------------- public reads


def user_by_screen_name(screen_name: str, timeout: int = 30) -> tuple[int, dict[str, Any] | None, str]:
    status, payload, err = _gql("UserByScreenName", {"screen_name": screen_name}, timeout)
    if status != 200 or not isinstance(payload, dict):
        return _fail(status, f"web UserByScreenName: {err or 'нет ответа'}", err)
    node = ((payload.get("data") or {}).get("user") or {}).get("result")
    if not isinstance(node, dict):
        return _fail(status, "web UserByScreenName: пустой result", json.dumps(payload)[:200])
    return 0, {"data": _v2_user(node)}, ""


def user_tweets(user_id: str, count: int = 10, timeout: int = 30) -> tuple[int, dict[str, Any] | None, str]:
    variables = {
        "userId": str(user_id),
        "count": max(10, min(WEB_PAGE_MAX, int(count or 10))),
        "includePromotedContent": False,
        "withVoice": True,
        "withArticlePlainText": False,
    }
    status, payload, err = _gql("UserTweets", variables, timeout)
    if status != 200 or not isinstance(payload, dict):
        return _fail(status, f"web UserTweets: {err or 'нет ответа'}", err)
    posts, users = _payload_from_response(payload)
    return 0, _wrap(posts, users), ""


def _web_query(raw_query: str) -> str:
    """Перевод v2-операторов в веб-синтаксис поиска.

    `retweets_of:ACCOUNT` в веб-бэкенде не работает (проверено 23.11.2026: 0 результатов),
    эквивалент — `ACCOUNT filter:nativeretweets`.
    """
    query = (raw_query or "").strip()
    match = re.match(r"^retweets_of:([A-Za-z0-9_]{1,15})$", query)
    if match:
        return f"{match.group(1)} filter:nativeretweets"
    return query


def search_recent(
    query: str, count: int = 20, timeout: int = 30, product: str = "Latest"
) -> tuple[int, dict[str, Any] | None, str]:
    web_query = _web_query(query)
    if not web_query:
        return _fail(0, "web SearchTimeline: пустой запрос", "")
    variables = {
        "rawQuery": web_query,
        "count": max(10, min(WEB_PAGE_MAX, int(count or 20))),
        "querySource": "typed_query",
        "product": product,
    }
    status, payload, err = _gql("SearchTimeline", variables, timeout)
    if status != 200 or not isinstance(payload, dict):
        return _fail(status, f"web SearchTimeline: {err or 'нет ответа'}", err)
    posts, users = _payload_from_response(payload)
    return 0, _wrap(posts, users), ""


_REPOST_CACHE: dict[str, Any] = {"ts": 0.0, "by_orig": {}, "empty": False}


def _repost_index(timeout: int = 30) -> dict[str, list[dict[str, Any]]]:
    """Карта оригинальный пост → кто его ретвитнул (один поиск на прогон)."""
    if time.time() - float(_REPOST_CACHE["ts"]) < REPOST_CACHE_TTL and _REPOST_CACHE["by_orig"]:
        return _REPOST_CACHE["by_orig"]
    code, payload, _ = search_recent(f"{_account} filter:nativeretweets", count=WEB_PAGE_MAX, timeout=timeout)
    by_orig: dict[str, list[dict[str, Any]]] = {}
    if code == 0 and isinstance(payload, dict):
        users = {str(u.get("id")): u for u in (payload.get("includes") or {}).get("users", [])}
        for post in payload.get("data") or []:
            refs = post.get("referenced_tweets") or []
            orig = next((r.get("id") for r in refs if r.get("type") == "retweeted"), "")
            author = users.get(str(post.get("author_id") or ""))
            if orig and author:
                by_orig.setdefault(str(orig), []).append(author)
    _REPOST_CACHE.update({"ts": time.time(), "by_orig": by_orig})
    return by_orig


def retweeted_by(post_id: str, timeout: int = 30) -> tuple[int, dict[str, Any] | None, str]:
    """Кто ретвитнул пост (форма /2/tweets/{id}/retweeted_by)."""
    try:
        users = _repost_index(timeout=timeout).get(str(post_id)) or []
    except XWebAuthError as exc:
        return _fail(401, str(exc), "")
    return 0, {"data": users, "meta": {"result_count": len(users)}}, ""


# ---------------------------------------------------------------- xurl-compat


_PATH_USER_TWEETS = re.compile(r"^/2/users/([^/]+)/tweets$")
_PATH_USER_BY_NAME = re.compile(r"^/2/users/by/username/([^/?]+)$")
_PATH_SEARCH = re.compile(r"^/2/tweets/search/recent$")
_PATH_RETWEETERS = re.compile(r"^/2/tweets/([^/]+)/retweeted_by$")


def run_compat(args: list[str], timeout: int = 45) -> tuple[int, dict[str, Any] | None, str]:
    """Замена `xurl <args>`: те же аргументы, но через веб-сессию.

    Поддержаны ровно те вызовы, которые делает трекер:
      user <screen_name> · search <query> -n <N> ·
      /2/users/{id}/tweets · /2/tweets/search/recent · /2/tweets/{id}/retweeted_by
    """
    if not args:
        return _fail(0, "web: пустой вызов", "")
    try:
        head = args[0]
        if head == "user" and len(args) >= 2:
            return user_by_screen_name(args[1].lstrip("@"), timeout=timeout)
        if head == "search" and len(args) >= 2:
            count = 10
            if "-n" in args:
                try:
                    count = int(args[args.index("-n") + 1])
                except (IndexError, ValueError):
                    count = 10
            return search_recent(args[1], count=count, timeout=timeout)
        if head.startswith("/2/"):
            path, _, query_string = head.partition("?")
            params = dict(urllib.parse.parse_qsl(query_string))
            match = _PATH_USER_BY_NAME.match(path)
            if match:
                return user_by_screen_name(match.group(1), timeout=timeout)
            match = _PATH_USER_TWEETS.match(path)
            if match:
                count = int(params.get("max_results") or 10)
                return user_tweets(match.group(1), count=count, timeout=timeout)
            if _PATH_SEARCH.match(path):
                count = int(params.get("max_results") or 20)
                return search_recent(params.get("query") or "", count=count, timeout=timeout)
            match = _PATH_RETWEETERS.match(path)
            if match:
                return retweeted_by(match.group(1), timeout=timeout)
            return _fail(0, f"web: путь {path[:40]} не поддержан", "")
        return _fail(0, f"web: вызов {head[:40]} не поддержан", "")
    except XWebAuthError as exc:
        return _fail(401, str(exc), "")


def healthcheck(timeout: int = 30) -> tuple[bool, str]:
    """Жива ли веб-читалка: профиль аккаунта + поиск. Для ручных проверок и cron-диагностики."""
    code, payload, err = user_by_screen_name(_account, timeout=timeout)
    if code != 0:
        return False, f"профиль: {err or payload}"
    followers = ((payload or {}).get("data") or {}).get("public_metrics", {}).get("followers_count")
    code2, payload2, err2 = search_recent(_account, count=10, timeout=timeout)
    if code2 != 0:
        return False, f"поиск: {err2 or payload2}"
    return True, f"@{_account}: фолловеров {followers}, постов в поиске {len((payload2 or {}).get('data') or [])}"
