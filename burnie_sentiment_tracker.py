#!/usr/bin/env python3
"""BURNIE community sentiment tracker (PolitiFi, ноябрь 2026 = катализатор).

Runs read-only X checks through the configured xurl CLI, appends one JSONL
snapshot. Hard-push (stdout → cron → Telegram) только при hard_alert:
RT/quote/reply офиц. аккаунта от ≥50k fol / known / politician.

Weights (sum=100): sentiment 20, virality 20, TA 15, smart money 15,
market 10, holders 10, security 10.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from operators import Verdict, check_destination

ROOT = Path(__file__).resolve().parent
RAB9_DIR = Path("/home/hermes-workspace/rab9")
OUTFILE = RAB9_DIR / "community_sentiment.jsonl"
ACCOUNT = "BurnieSendersX"
NEGATIVE_QUERY = (
    'BURNIE (rug OR scam OR dump OR dumped OR warning OR abandoned OR dead '
    'OR "exit liquidity") -is:retweet'
)
# Исторический bullish-запрос (CLI). 3-й X-вызов заменён на CATALYST_QUERY (raw API).
BULLISH_QUERY = (
    'BURNIE (toly OR anatoly OR buy OR signal OR primed OR send OR sending '
    'OR moonshot OR listing OR vote OR accumulation OR bottom OR bounce '
    'OR pump OR breakout OR bullish OR begged OR 700x OR 2000x)'
)
# Катализатор: RT/ответы/упоминания офиц. аккаунта + любые упоминания BURNIE.
# retweets_of ловит RT крупных аккаунтов; -is:retweet только на organic-ветке.
# Лайки крупных аккаунтов X API v2 не отдаёт search'ем (нужен liking_users per-tweet → лишние вызовы).
CATALYST_QUERY = (
    f"(retweets_of:{ACCOUNT} OR "
    f"((@{ACCOUNT} OR to:{ACCOUNT} OR BURNIE) -is:retweet)) "
    f"-from:{ACCOUNT}"
)
# Порог «не пустышка»: <1k фолловеров = шум; ≥5k = KOL; ≥50k = large; ≥500k = mega.
CATALYST_MIN_FOLLOWERS = 5000
CATALYST_LARGE_FOLLOWERS = 50_000
CATALYST_MEGA_FOLLOWERS = 500_000
CATALYST_MAX_RESULTS = 25

# Типы «офиц. касания» для hard_alert (event-first).
OFFICIAL_TOUCH_TYPES = frozenset({
    "rt_fresh",
    "rt_official",
    "quote_fresh",
    "quote_official",
    "reply_official",
})
# hard_alert только от large/mega/known/politician.
HARD_ALERT_TIERS = frozenset({"large", "mega", "known", "politician"})

# Мёртвая цитата: 0 likes + 0 RT от мелкого аккаунта — НЕ катализатор.
# Пропускаем только если likes+RT >= 5 ИЛИ fol >= 50k ИЛИ known/politician.
DEAD_QUOTE_MIN_ENGAGEMENT = 5

# Окна атрибуции (секунды): T0 → 1h / 6h / 24h.
ATTRIBUTION_WINDOWS = (
    ("h1", 3600),
    ("h6", 6 * 3600),
    ("h24", 24 * 3600),
)
# Допуск «окно закрыто» — не ждать ровно 1h, а ≥90% окна.
ATTRIBUTION_WINDOW_TOLERANCE = 0.90

# --- PolitiFi: политические аккаунты (высший tier = politician) ---
# Конгресс, MAGA, демократы, партийные, обозреватели выборов США.
POLITICIAN_WATCHLIST: tuple[str, ...] = (
    # Исполнительная / кандидаты / семья Трампа
    "realDonaldTrump",
    "DonaldJTrumpJr",
    "EricTrump",
    "LaraTrump",
    "IvankaTrump",
    "JDVance",
    "VP",
    "POTUS",
    "FLOTUS",
    "KamalaHarris",
    "JoeBiden",
    "BernieSanders",
    "RFKJr",
    "RobertKennedyJr",
    "VivekGRamaswamy",
    "GovRonDeSantis",
    "RonDeSantis",
    "KariLake",
    "NikkiHaley",
    "TulsiGabbard",
    # Конгресс — республиканцы / MAGA
    "SpeakerJohnson",
    "SteveScalise",
    "Jim_Jordan",
    "RepMattGaetz",
    "mtgreenee",
    "RepMTG",
    "EliseStefanik",
    "marcorubio",
    "SenTedCruz",
    "RandPaul",
    "SenRickScott",
    "SenTomCotton",
    "SenJohnKennedy",
    "SenTuberville",
    "SenJoniErnst",
    "SenBillCassidy",
    "RepNancyMace",
    "RepChipRoy",
    "RepAnnaPaulina",
    "RepBoebert",
    "laurenboebert",
    "RepAndyBiggsAZ",
    "RepThomasMassie",
    "RepDanCrenshaw",
    "RepBrianMast",
    "RepByronDonalds",
    "ByronDonalds",
    "RepTimBurchett",
    "SenMikeLee",
    "SenHawleyPress",
    "HawleyMO",
    "SenJoshHawley",
    # Конгресс — демократы / прогрессисты
    "AOC",
    "RepAOC",
    "SenSchumer",
    "SpeakerPelosi",
    "SenWarren",
    "SenBooker",
    "CoryBooker",
    "SenDuckworth",
    "RepAdamSchiff",
    "AdamSchiff",
    "RepJeffries",
    "HakeemJeffries",
    "SenMarkey",
    "RepRaskin",
    "IlhanMN",
    "RepJayapal",
    "SenSanders",
    "PeteButtigieg",
    "SecretaryPete",
    # Губернаторы / штаты
    "GavinNewsom",
    "GregAbbott",
    "GovAbbott",
    "JBPritzker",
    "GovKathyHochul",
    "GovKristiNoem",
    "GovSarahHuckabee",
    "BrianKempGA",
    # Партийные / комитеты
    "GOP",
    "TheDemocrats",
    "RNC",
    "DNC",
    "NRCC",
    "DCCC",
    "HouseGOP",
    "HouseDemocrats",
    "SenateGOP",
    "SenateDems",
    # Медиа / обозреватели / MAGA-бренды
    "seanhannity",
    "TuckerCarlson",
    "IngrahamAngle",
    "JesseBWatters",
    "GregGutfeld",
    "marklevinshow",
    "dbongino",
    "JackPosobiec",
    "catturd2",
    "bennyjohnson",
    "CharlieKirk11",
    "benshapiro",
    "realcandaceo",
    "Timcast",
    "scrowder",
    "BuckSexton",
    "MegynKelly",
    "BillOReilly",
    "LaraLeavittVH",
    "KarolineLeavitt",
    "DanScavino",
    "Kash_Patel",
    "StephenM",
    "SteveBannon",
    "RudyGiuliani",
    # Политобозреватели / выборы
    "NateSilver538",
    "FiveThirtyEight",
    "DecisionDeskHQ",
    "CookPolitical",
    "RealClearNews",
    "RealClearPolitics",
    "Politico",
    "thehill",
    "Axios",
    "CNNPolitics",
    "NBCPolitics",
    "CBSPolitics",
    "ABCPolitics",
    "FoxNews",
    "FoxNewsSunday",
    "MeetThePress",
    "FaceTheNation",
    "ThisWeekABC",
    "nytimes",
    "washingtonpost",
    "WSJ",
    "AP",
    "Reuters",
    "Semafor",
    "PunchbowlNews",
    "PoliticoPlaybook",
)

# Календарь политических событий до/около ноября 2026 (midterms).
# date ISO YYYY-MM-DD; окно усиления ±3 дня.
POLITICAL_CALENDAR: tuple[dict[str, str], ...] = (
    {"date": "2026-08-04", "event": "KS / MI / MO / WA primaries"},
    {"date": "2026-08-06", "event": "TN / WI primaries"},
    {"date": "2026-08-11", "event": "CO / CT / MN / VT primaries"},
    {"date": "2026-08-13", "event": "HI primary"},
    {"date": "2026-08-18", "event": "AK / WY primaries"},
    {"date": "2026-08-25", "event": "AZ / FL / OK primaries"},
    {"date": "2026-09-01", "event": "Labor Day — kickoff fall campaigns"},
    {"date": "2026-09-08", "event": "MA / NH / RI / DE primaries (est.)"},
    {"date": "2026-09-15", "event": "NY / RI primary runoff window"},
    {"date": "2026-09-22", "event": "First general-election debate window (est.)"},
    {"date": "2026-10-06", "event": "VP / Senate debate window (est.)"},
    {"date": "2026-10-13", "event": "Columbus Day debate week (est.)"},
    {"date": "2026-10-20", "event": "Final presidential-style midterm debates (est.)"},
    {"date": "2026-10-27", "event": "Final week of campaigning"},
    {"date": "2026-11-01", "event": "Get-out-the-vote weekend"},
    {"date": "2026-11-03", "event": "US Midterm Election Day 2026"},
    {"date": "2026-11-04", "event": "Election results / reaction day"},
    {"date": "2026-11-05", "event": "Post-election market reaction"},
)
CALENDAR_WINDOW_DAYS = 1  # узкое окно: только реально близкие события (±1д), иначе бонус девальвируется
CALENDAR_VIRALITY_BONUS = 2  # +к virality, только если событие впереди (не после)

# PolitiFi-соседи BURNIE на Solana (DexScreener, без X-вызовов).
# Официальный TRUMP/MELANIA + election memes / MAGA-бренды.
COMPETITOR_TOKENS: tuple[dict[str, str], ...] = (
    {
        "symbol": "TRUMP",
        "name": "OFFICIAL TRUMP",
        "address": "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN",
    },
    {
        "symbol": "MUSK",
        "name": "Musk (мем Илона Маска)",
        "address": "D4BPL1zvhhwCRJXWFxcGbVHDZg8vJqWgkkqmZajWfTqF",
    },
    {
        "symbol": "MELANIA",
        "name": "Melania Meme",
        "address": "FUAfBo2jgks6gB4Z4LfZkqSZgzNucisEHqnNebaRxM1P",
    },
    {
        "symbol": "MAGA",
        "name": "Make Aliens Great Again",
        "address": "Hon2rHAiqkcDtUzL5gA2vjXPr7T1MPCK2UT2AHKCpump",
    },
    {
        "symbol": "tremp",
        "name": "doland tremp",
        "address": "FU1q8vJpZNUrmqsciSjp8bAKKidGsLmouB8CBdf8TKQv",
    },
    {
        "symbol": "USA",
        "name": "American Coin",
        "address": "69kdRLyP5DTRkpHraaSZAQbWmAwzF9guKjZfzMXzcbAs",
    },
    {
        "symbol": "VANCE",
        "name": "OFFICIAL JD VANCE",
        "address": "CQeLUzZktFcDa5kJfa844kxK51X7BzxorVDGqLvpump",
    },
)

NEGATIVE_TERMS = (
    "rug",
    "rugpull",
    "rug pull",
    "dump warning",
    "dumped",
    "abandoned",
    "dead coin",
    "exit liquidity",
    "dev sold",
    "honeypot",
)
SCAM_PATTERNS = (
    "burnie scam",
    "burnie is a scam",
    "$burnie scam",
    "$burnie is a scam",
)
VOTE_SPAM_PATTERNS = (
    "voted yes for",
    "get listed on fomo",
    "almost on moonshot",
    "about to get listed on moonshot",
    "is so close for moonshot",
    "just voted yes",
    "community vote dashboard",
    "new listing around the corner",
    "votes left",
    "votes to go",
    "more votes",
    "start voting",
    "your vote matters",
)
POSITIVE_TERMS = (
    "bullish",
    "send",
    "sending",
    "moon",
    "100x",
    "700x",
    "2000x",
    "1000x",
    "500x",
    "based",
    "solid",
    "accumulation",
    "primed",
    "bounce",
    "breakout",
    "pump",
    "begged",
    "bought",
)
TOLY_TERMS = (
    "toly",
    "anatoly",
    "yakovenko",
    "@toly",
)
AI_BUY_TERMS = (
    "buy signal",
    "strong buy",
    "target",
    "upside",
    "x from",
    "openclaw",
    "iscan",
)


def run_xurl(args: list[str], timeout: int = 45) -> tuple[int, dict[str, Any] | None, str]:
    proc = subprocess.run(
        ["xurl", *args],
        cwd=str(RAB9_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    raw = (proc.stdout or proc.stderr or "").strip()
    try:
        payload = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        payload = None
    return proc.returncode, payload, raw[:300]


def run_x_search_raw(
    query: str,
    max_results: int = 25,
    timeout: int = 45,
) -> tuple[int, dict[str, Any] | None, str]:
    """Recent search через raw X API v2 (xurl GET) с user.public_metrics.

    CLI `xurl search` НЕ возвращает followers_count — только verified.
    Raw endpoint с expansions=author_id + user.fields=public_metrics даёт вес аккаунта.
    Считается как 1 X-вызов (тот же бюджет, что CLI search).
    """
    params = {
        "query": query,
        "max_results": str(max(10, min(100, max_results))),
        "tweet.fields": "created_at,author_id,public_metrics,referenced_tweets,in_reply_to_user_id",
        "expansions": "author_id,referenced_tweets.id",
        "user.fields": "username,name,public_metrics,verified,verified_type",
    }
    qs = urllib.parse.urlencode(params, safe="():\"@")
    path = f"/2/tweets/search/recent?{qs}"
    return run_xurl([path], timeout=timeout)


def fetch_fresh_official_interactions(
    user_id: str | None = None,
    max_posts: int = 10,
    freshness_min: int = 720,
    timeout: int = 45,
) -> dict[str, Any]:
    """Детектор свежего катализатора: посты офиц. аккаунта и кто их ретвитит.

    Логика: солидный аккаунт НЕ кричит «buy» — он ретвитит/лайкает/цитирует
    свежий пост официального аккаунта. Берём timeline @BurnieSendersX, для
    постов с активностью (RT>0) за последние freshness_min минут (12ч):
      - retweeted_by → кто ретвитнул (фильтр по CATALYST_MIN_FOLLOWERS)
      - like_count > среднего × 3 → аномальный всплеск лайков (like_spike)
      - quotes → кто процитировал (is:quote search)

    X-вызовы: 1 (timeline) + 1 на каждый «горячий» пост (retweeted_by) + 1 (quotes).
    Требует user_id (можно из user-вызова); если нет — ищем по username.
    """
    out: dict[str, Any] = {"ok": False, "hot": []}
    try:
        import urllib.parse

        # 1. Timeline официального аккаунта (последние посты)
        uid = user_id
        if not uid:
            code, up, _ = run_xurl(["user", ACCOUNT])
            uid = (up or {}).get("data", {}).get("id") if isinstance(up, dict) else None
        if not uid:
            return out
        tl_path = (
            f"/2/users/{uid}/tweets?max_results={max_posts}"
            "&tweet.fields=created_at,public_metrics,author_id"
        )
        tl_code, tl_payload, tl_raw = run_xurl([tl_path], timeout=timeout)
        if tl_code != 0 or not isinstance(tl_payload, dict):
            return out

        now = int(time.time())
        hot_ids: list[str] = []
        like_vals: list[int] = []
        timeline_posts: list[dict[str, Any]] = []
        for post in (tl_payload.get("data") or []):
            if not isinstance(post, dict):
                continue
            timeline_posts.append(post)
            pm = post.get("public_metrics") or {}
            like_vals.append(int(pm.get("like_count") or 0))
            created = post.get("created_at") or ""
            try:
                ts = int(datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())
            except ValueError:
                try:
                    ts = int(datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").timestamp())
                except ValueError:
                    continue
            age_min = (now - ts) / 60
            pm = post.get("public_metrics") or {}
            rt = int(pm.get("retweet_count") or 0)
            if age_min <= freshness_min and rt > 0:
                hot_ids.append(str(post.get("id") or ""))

        # Средний like_count по аккаунту (для аномалии ×3)
        avg_likes = (sum(like_vals) / len(like_vals)) if like_vals else 0

        # 1b. like_spike: свежий пост с аномальным числом лайков (> среднего × 3)
        hot: list[dict[str, Any]] = []
        for post in timeline_posts:
            pm = post.get("public_metrics") or {}
            likes = int(pm.get("like_count") or 0)
            created = post.get("created_at") or ""
            try:
                ts = int(datetime.strptime(created, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp())
            except ValueError:
                try:
                    ts = int(datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").timestamp())
                except ValueError:
                    continue
            age_min = (now - ts) / 60
            if age_min <= freshness_min and avg_likes > 5 and likes >= avg_likes * 3:
                hot.append(
                    {
                        "user": "",
                        "followers": 0,
                        "verified": False,
                        "tier": "spike",
                        "type": "like_spike",
                        "text": f"Аномальный всплеск лайков ({likes} против средних {avg_likes:.0f}) на свежем посте @{ACCOUNT}",
                        "id": str(post.get("id") or ""),
                        "url": f"https://x.com/{ACCOUNT}/status/{post.get('id')}" if post.get("id") else "",
                        "likes": likes,
                        "rt": 0,
                        "post_id": str(post.get("id") or ""),
                    }
                )
                break  # хватит одного аномального поста

        # 2. Для каждого горячего поста — кто ретвитнул (followers → вес)
        # Сначала соберём map author_id → id ретвит-поста (retweets_of:),
        # чтобы ссылка вела на сам ретвит, а не на оригинальный пост офиц. аккаунта.
        rt_id_by_author: dict[str, str] = {}
        try:
            ro_query = urllib.parse.quote(f"retweets_of:{ACCOUNT}")
            ro_path = (
                "/2/tweets/search/recent?query=" + ro_query
                + "&max_results=50&tweet.fields=author_id&expansions=author_id"
            )
            ro_code, ro_payload, _ = run_xurl([ro_path], timeout=timeout)
            if ro_code == 0 and isinstance(ro_payload, dict):
                for post in (ro_payload.get("data") or []):
                    if isinstance(post, dict) and post.get("author_id"):
                        rt_id_by_author[str(post["author_id"])] = str(post.get("id") or "")
        except Exception:
            pass

        for pid in hot_ids[:2]:  # максимум 2 retweeted_by-вызова
            rt_path = (
                f"/2/tweets/{pid}/retweeted_by"
                "?user.fields=username,name,public_metrics,verified,verified_type"
            )
            r_code, r_payload, _ = run_xurl([rt_path], timeout=timeout)
            if r_code != 0 or not isinstance(r_payload, dict):
                continue
            for u in (r_payload.get("data") or []):
                if not isinstance(u, dict):
                    continue
                pm = u.get("public_metrics") or {}
                fol = int(pm.get("followers_count") or 0)
                if fol < CATALYST_MIN_FOLLOWERS:
                    continue
                uname = u.get("username") or ""
                uid = str(u.get("id") or "")
                w = account_weight(fol, verified=bool(u.get("verified")), username=uname)
                # Ссылка на САМ РЕТВИТ (id из retweets_of), иначе на профиль
                rt_post_id = rt_id_by_author.get(uid, "")
                rt_url = (
                    f"https://x.com/{uname}/status/{rt_post_id}"
                    if uname and rt_post_id
                    else f"https://x.com/{uname}" if uname else ""
                )
                hot.append(
                    {
                        "user": uname,
                        "followers": fol,
                        "verified": bool(u.get("verified")),
                        "tier": w["tier"],
                        "type": "rt_fresh",
                        "text": f"Ретвит свежего поста @{ACCOUNT}",
                        "id": rt_post_id or pid,
                        "url": rt_url,
                        "likes": 0,
                        "rt": 0,
                        "post_id": pid,
                    }
                )
        hot.sort(key=lambda c: (-int(c.get("followers") or 0)))

        # 3. Quotes: кто процитировал свежий пост офиц. аккаунта (is:quote)
        # Цитата крупного аккаунта = сильный катализатор (комментирует, значит следит).
        if hot_ids:
            q_query = urllib.parse.quote(f"is:quote @{ACCOUNT} -is:retweet")
            q_path = (
                "/2/tweets/search/recent?query=" + q_query
                + "&max_results=20"
                + "&tweet.fields=created_at,author_id,public_metrics,referenced_tweets"
                + "&expansions=author_id&user.fields=username,name,public_metrics,verified"
            )
            q_code, q_payload, _ = run_xurl([q_path], timeout=timeout)
            if q_code == 0 and isinstance(q_payload, dict):
                for post in (q_payload.get("data") or []):
                    if not isinstance(post, dict):
                        continue
                    u = _user_of(post, q_payload)
                    pm = u.get("public_metrics") or {}
                    fol = int(pm.get("followers_count") or 0)
                    if fol < CATALYST_MIN_FOLLOWERS:
                        continue
                    uname = u.get("username") or ""
                    w = account_weight(fol, verified=bool(u.get("verified")), username=uname)
                    q_likes = int((post.get("public_metrics") or {}).get("like_count") or 0)
                    q_rt = int((post.get("public_metrics") or {}).get("retweet_count") or 0)
                    # Фильтр мёртвых цитат (0/0 от мелкого аккаунта ≠ катализатор)
                    if is_dead_quote(
                        likes=q_likes,
                        rt=q_rt,
                        followers=fol,
                        known=bool(w.get("known") or w.get("politician")),
                    ):
                        continue
                    pid = str(post.get("id") or "")
                    hot.append(
                        {
                            "user": uname,
                            "followers": fol,
                            "verified": bool(u.get("verified")),
                            "tier": w["tier"],
                            "type": "quote_fresh",
                            "text": "Цитата свежего поста @{}: {}".format(
                                ACCOUNT, compact_text(str(post.get("text") or ""), 80)
                            ),
                            "id": pid,
                            "url": f"https://x.com/{uname}/status/{pid}" if uname and pid else "",
                            "likes": q_likes,
                            "rt": q_rt,
                            "post_id": hot_ids[0],
                        }
                    )
        # Dedup по url (retweeted_by может вернуть один аккаунт дважды — по 2 горячим постам)
        seen_urls: set[str] = set()
        uniq_hot = []
        for c in hot:
            u = c.get("url") or ""
            if u and u in seen_urls:
                continue
            if u:
                seen_urls.add(u)
            uniq_hot.append(c)
        hot = uniq_hot
        hot.sort(key=lambda c: (-int(c.get("followers") or 0)))
        out.update({"ok": True, "hot": hot})
    except Exception:
        pass
    return out


def users_by_id(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Карта author_id → user из includes.users."""
    out: dict[str, dict[str, Any]] = {}
    try:
        for u in (payload or {}).get("includes", {}).get("users", []) or []:
            if isinstance(u, dict) and u.get("id"):
                out[str(u["id"])] = u
    except Exception:
        pass
    return out


def _username_of(post: dict[str, Any], payload: dict[str, Any] | None) -> str:
    """Resolve username for a post via includes.users in the same payload."""
    try:
        users = (payload or {}).get("includes", {}).get("users", [])
        aid = post.get("author_id", "")
        for u in users:
            if u.get("id") == aid:
                return u.get("username", "")
    except Exception:
        pass
    return ""


def _user_of(post: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    """Полный объект автора из includes (для followers/verified)."""
    aid = str(post.get("author_id") or "")
    return users_by_id(payload).get(aid, {})


def items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def is_bare_burnie(text: str) -> bool:
    """Слово BURNIE без $тикера и #хештега — двусмысленное упоминание (катализатор)."""
    if not re.search(r"\bBURNIE\b", text or "", flags=re.IGNORECASE):
        return False
    if re.search(r"\$BURNIE\b", text or "", flags=re.IGNORECASE):
        return False
    if re.search(r"#BURNIE\b", text or "", flags=re.IGNORECASE):
        return False
    return True


def _politician_set() -> set[str]:
    return {h.lower().lstrip("@") for h in POLITICIAN_WATCHLIST}


def is_politician(username: str) -> bool:
    """Аккаунт из POLITICIAN_WATCHLIST (конгресс / MAGA / обозреватели)."""
    return (username or "").lower().lstrip("@") in _politician_set()


def is_dead_quote(
    likes: int,
    rt: int,
    followers: int,
    known: bool = False,
) -> bool:
    """Мёртвая цитата: 0 лайков + 0 RT от мелкого аккаунта — НЕ катализатор.

    Живая, если: likes+RT >= 5 ИЛИ followers >= 50K ИЛИ known/politician.
    """
    if known:
        return False
    if followers >= CATALYST_LARGE_FOLLOWERS:
        return False
    if (int(likes or 0) + int(rt or 0)) >= DEAD_QUOTE_MIN_ENGAGEMENT:
        return False
    return True


def account_weight(
    followers: int,
    verified: bool = False,
    username: str = "",
) -> dict[str, Any]:
    """Вес аккаунта: отсекает пустышек, поднимает KOL/mega/known/politician.

    tier: junk | micro | kol | large | mega | known | politician
    score: 0–100 для ранжирования (не путать с weighted_score снапшота).
    politician — высший приоритет (PolitiFi / выборы).
    """
    uname = (username or "").lower().lstrip("@")
    known = uname in {h.lower() for h in KNOWN_INFLUENCERS}
    politician = uname in _politician_set()
    # Политик / партийный / обозреватель — tier выше known
    if politician:
        tier = "politician"
        score = 100
    elif known:
        # Toly / aeyakovenko и список KNOWN всегда «known» независимо от фолловеров
        tier = "known"
        score = 95
    elif followers >= CATALYST_MEGA_FOLLOWERS:
        tier = "mega"
        score = 90
    elif followers >= CATALYST_LARGE_FOLLOWERS:
        tier = "large"
        score = 75
    elif followers >= CATALYST_MIN_FOLLOWERS:
        tier = "kol"
        score = 55
    elif followers >= 1000:
        tier = "micro"
        score = 25
    else:
        tier = "junk"
        score = 5
    if verified and tier not in ("junk",) and score < 100:
        score = min(100, score + 8)
    return {
        "tier": tier,
        "score": score,
        "followers": followers,
        "verified": bool(verified),
        "known": known,
        "politician": politician,
        # сигнал: politician / known / kol+ (не junk/micro)
        "is_signal": politician or known or followers >= CATALYST_MIN_FOLLOWERS,
    }


def _is_weighted_account(user: dict[str, Any]) -> bool:
    """Есть ли у аккаунта вес для доверия негативу (≥5K fol или known influencer)."""
    try:
        pm = (user or {}).get("public_metrics") or {}
        fol = int(pm.get("followers_count") or 0)
        uname = ((user or {}).get("username") or "").lower().lstrip("@")
        known = uname in {h.lower() for h in KNOWN_INFLUENCERS}
        return known or is_politician(uname) or fol >= CATALYST_MIN_FOLLOWERS
    except Exception:
        return False


def _is_toly_author(post: dict[str, Any], payload: dict[str, Any] | None) -> bool:
    """Автор поста — Toly/aeyakovenko ИЛИ явный ответ ему (reply/mention)."""
    try:
        uname = _username_of(post, payload).lower().lstrip("@")
        if uname in ("toly", "aeyakovenko"):
            return True
        # Явный ответ: текст начинается с @toly / to:toly (не substring в середине)
        text = (post.get("text") or "").lower().strip()
        return text.startswith("@toly") or text.startswith("@aeyakovenko")
    except Exception:
        return False


def classify_interaction(post: dict[str, Any], text: str) -> str:
    """Тип взаимодействия с офиц. аккаунтом / BURNIE.

    rt_official | reply_official | quote_official | mention_official |
    bare_burnie | ticker_mention | other
    """
    refs = post.get("referenced_tweets") or []
    rtypes = {str(r.get("type") or "") for r in refs if isinstance(r, dict)}
    low = (text or "")
    low_l = low.lower()
    official = f"@{ACCOUNT}".lower()
    has_official = official in low_l or ACCOUNT.lower() in low_l

    if "retweeted" in rtypes and has_official:
        return "rt_official"
    if has_official and "quoted" in rtypes:
        return "quote_official"
    if has_official and (
        "replied_to" in rtypes
        or low_l.strip().startswith(official)
        or post.get("in_reply_to_user_id")
    ):
        # reply / mention-as-reply к офиц. или тред
        if low_l.strip().startswith(official) or "replied_to" in rtypes:
            return "reply_official"
        return "mention_official"
    if has_official:
        return "mention_official"
    if is_bare_burnie(text):
        return "bare_burnie"
    if re.search(r"\$BURNIE\b|#BURNIE\b|\bBURNIE\b", text or "", flags=re.IGNORECASE):
        return "ticker_mention"
    return "other"


def extract_catalysts(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Вытащить катализаторные сигналы: крупные аккаунты × BURNIE / @BurnieSendersX.

    Фильтр: weight.is_signal (known influencer ИЛИ followers ≥ CATALYST_MIN_FOLLOWERS).
    Сортировка: weight.score desc, затем followers.
    """
    catalysts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for post in items(payload):
        user = _user_of(post, payload)
        username = user.get("username") or ""
        metrics = user.get("public_metrics") or {}
        followers = int(metrics.get("followers_count") or 0)
        verified = bool(user.get("verified"))
        # verified_type: blue | business | government | none (если есть)
        vtype = user.get("verified_type") or ""
        text = str(post.get("text") or "")
        itype = classify_interaction(post, text)
        weight = account_weight(followers, verified=verified, username=username)
        likes = int((post.get("public_metrics") or {}).get("like_count") or 0)
        rt_n = int((post.get("public_metrics") or {}).get("retweet_count") or 0)

        # Катализатор: либо взаимодействие с офиц., либо bare BURNIE, либо known/politician —
        # но только от аккаунтов с весом (не пустышки 128 fol).
        is_official_touch = itype in (
            "rt_official",
            "reply_official",
            "quote_official",
            "mention_official",
        )
        is_ambiguous = itype == "bare_burnie"
        if not (is_official_touch or is_ambiguous or weight["known"] or weight["politician"]):
            continue
        if not weight["is_signal"] and not weight["known"] and not weight["politician"]:
            continue
        # known/politician + ticker_mention тоже берём (Toly сказал $BURNIE)
        if (weight["known"] or weight["politician"]) and itype == "other":
            continue
        # Мёртвые цитаты (quote_official 0/0 от мелкого) — не катализатор
        if itype == "quote_official" and is_dead_quote(
            likes=likes,
            rt=rt_n,
            followers=followers,
            known=bool(weight.get("known") or weight.get("politician")),
        ):
            continue

        pid = str(post.get("id") or "")
        dedup = f"{username.lower()}:{itype}:{pid}"
        if dedup in seen:
            continue
        seen.add(dedup)

        catalysts.append(
            {
                "user": username,
                "followers": followers,
                "verified": verified,
                "verified_type": vtype,
                "tier": weight["tier"],
                "weight": weight["score"],
                "type": itype,
                "text": compact_text(text, 120),
                "id": pid,
                "url": post_url(username, pid) if username and pid else "",
                "likes": likes,
                "rt": rt_n,
            }
        )

    catalysts.sort(key=lambda c: (-int(c.get("weight") or 0), -int(c.get("followers") or 0)))
    return catalysts


def compact_text(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def term_count(texts: list[str], terms: tuple[str, ...]) -> int:
    blob = "\n".join(texts).lower()
    return sum(blob.count(term) for term in terms)


def totals(posts: list[dict[str, Any]]) -> dict[str, int]:
    out = {"likes": 0, "rt": 0, "replies": 0, "views": 0}
    for post in posts:
        metrics = post.get("public_metrics") or {}
        out["likes"] += int(metrics.get("like_count") or 0)
        out["rt"] += int(metrics.get("retweet_count") or 0)
        out["replies"] += int(metrics.get("reply_count") or 0)
        out["views"] += int(metrics.get("impression_count") or 0)
    return out


def first_error(label: str, code: int, payload: dict[str, Any] | None, raw: str) -> str | None:
    if code == 0:
        return None
    status = payload.get("status") if isinstance(payload, dict) else None
    title = payload.get("title") if isinstance(payload, dict) else None
    if status or title:
        return f"{label} failed: {status or code} {title or ''}".strip()
    return f"{label} failed: exit={code} {compact_text(raw, 120)}"


def build_snapshot() -> tuple[dict[str, Any], list[str]]:
    """3 X-вызова: (1) user @BurnieSendersX (2) negative scan (3) catalyst raw search.

    3-й вызов заменяет старый bullish CLI search: тот же слот бюджета, но raw API
    с followers/verified + query (retweets_of | @official | to:official | BURNIE).
    KOL/catalyst больше не требует 4-го вызова через radar_x.
    """
    errors: list[str] = []

    # --- X call 1/4: профиль офиц. аккаунта (followers delta) ---
    user_code, user_payload, user_raw = run_xurl(["user", ACCOUNT])
    # --- X call 2/4: негативный сентимент ---
    neg_code, neg_payload, neg_raw = run_xurl(["search", NEGATIVE_QUERY, "-n", "10"])
    # --- X call 3/4: катализатор + organic BURNIE (raw → followers) ---
    cat_code, cat_payload, cat_raw = run_x_search_raw(
        CATALYST_QUERY, max_results=CATALYST_MAX_RESULTS
    )
    # --- X call 4/4: свежие посты офиц. аккаунта + кто их ретвитит ---
    # Солидный аккаунт не кричит «buy» — он ретвитит свежий пост @BurnieSendersX.
    uid = (user_payload or {}).get("data", {}).get("id") if isinstance(user_payload, dict) else None
    fresh_code, fresh_payload, fresh_raw = 0, None, ""
    try:
        fresh = fetch_fresh_official_interactions(user_id=uid)
        fresh_code, fresh_payload, fresh_raw = (0 if fresh.get("ok") else 1), fresh, ""
    except Exception:
        fresh = {"ok": False, "hot": []}

    for label, code, payload, raw in (
        (f"@{ACCOUNT} API", user_code, user_payload, user_raw),
        ("negative scan", neg_code, neg_payload, neg_raw),
        ("catalyst scan", cat_code, cat_payload, cat_raw),
        ("fresh RT scan", fresh_code, fresh_payload, fresh_raw),
    ):
        err = first_error(label, code, payload, raw)
        if err:
            errors.append(err)

    user_data = user_payload.get("data") if isinstance(user_payload, dict) else {}
    if not isinstance(user_data, dict):
        # X API мог вернуть ошибку/rate limit вместо data — не роняем прогон.
        user_data = {}
    user_metrics = user_data.get("public_metrics") if isinstance(user_data, dict) else {}
    if not isinstance(user_metrics, dict):
        user_metrics = {}
    followers = int(user_metrics.get("followers_count") or 0)
    tweet_count = int(user_metrics.get("tweet_count") or 0)
    user_id = user_data.get("id")

    negative_posts = items(neg_payload)
    # organic/catalyst-посты = источник bullish-термов и KOL-сигналов
    catalyst_posts = items(cat_payload)
    bullish_posts = catalyst_posts  # совместимость с прежней логикой strong_bullish
    bull_payload = cat_payload

    negative_texts = [str(post.get("text") or "") for post in negative_posts]
    bullish_texts = [str(post.get("text") or "") for post in bullish_posts]
    all_scan_texts = negative_texts + bullish_texts

    # Катализаторы: RT/reply/quote/mention офиц. + bare BURNIE от крупных аккаунтов
    catalysts = extract_catalysts(cat_payload)
    # Свежие RT/quote офиц. аккаунта — мержим, затем сортируем по tier (politician > known > mega > large)
    fresh_hot = (fresh.get("hot") if fresh.get("ok") else []) or []
    if fresh_hot:
        fresh_users = {f.get("user", "").lower() for f in fresh_hot}
        catalysts = fresh_hot + [
            c for c in catalysts
            if c.get("id") not in {f.get("post_id") for f in fresh_hot}
            and c.get("user", "").lower() not in fresh_users
        ]
    _tier_pri = {
        "politician": 100,
        "known": 95,
        "mega": 90,
        "large": 75,
        "kol": 55,
        "spike": 40,
        "micro": 25,
        "junk": 5,
    }
    catalysts.sort(
        key=lambda c: (
            -_tier_pri.get(c.get("tier") or "", int(c.get("weight") or 0)),
            -int(c.get("followers") or 0),
        )
    )
    # kol_mentions — подмножество для обратной совместимости weighted_score/format_alert
    kol_mentions = [
        {
            "user": c["user"],
            "followers": c["followers"],
            "text": c["text"],
            "type": c.get("type"),
            "tier": c.get("tier"),
            "id": c.get("id", ""),
            "verified": c.get("verified", False),
        }
        for c in catalysts
    ]
    kol_engagement = totals(catalyst_posts)

    # Vote-spam (Moonshot/FOMO listing campaign) is NOT a bullish driver —
    # count it separately, exclude from sentiment and strong_bullish.
    vote_spam_texts = [
        t for t in all_scan_texts
        if any(p in t.lower() for p in VOTE_SPAM_PATTERNS)
    ]
    clean_bullish_texts = [
        t for t in bullish_texts
        if not any(p in t.lower() for p in VOTE_SPAM_PATTERNS)
    ]

    neg_hits = term_count(all_scan_texts, NEGATIVE_TERMS) + term_count(
        all_scan_texts, SCAM_PATTERNS
    )
    # Уникальные посты от взвешенных аккаунтов (не вхождения слов!).
    # catalyst_posts уже отфильтрованы по ≥5K fol / known — здесь только уникальные посты
    # с позитивными терминами. Слово «pump» в 5 постах = 5 уникальных постов, не 18 вхождений.
    clean_bullish_posts = [
        p for p in bullish_posts
        if not any(sp in str(p.get("text") or "").lower() for sp in VOTE_SPAM_PATTERNS)
    ]
    pos_hits = sum(
        1 for p in clean_bullish_posts
        if any(term in str(p.get("text") or "").lower() for term in POSITIVE_TERMS)
    )
    # Toly — только если АВТОР поста = Toly/aeyakovenko, или явный ответ ему.
    # «Кто-то написал "toly" в тексте» ≠ Toly твитнул — это был мусорный сигнал.
    toly_hits = sum(
        1 for p in clean_bullish_posts
        if _is_toly_author(p, bull_payload)
    )
    ai_buy_hits = term_count(clean_bullish_texts, AI_BUY_TERMS)
    vote_spam_hits = len(vote_spam_texts)
    strong_negative = [
        {
            "text": compact_text(str(post.get("text") or ""), 100),
            "id": post.get("id", ""),
            "username": _username_of(post, neg_payload),
            "followers": int(
                ((_user_of(post, neg_payload).get("public_metrics") or {}).get("followers_count"))
                or 0
            ),
        }
        for post in negative_posts
        if any(
            term in str(post.get("text") or "").lower()
            for term in NEGATIVE_TERMS + SCAM_PATTERNS
        )
        # Риск от пустышки (5 fol) — это НЕ риск. Только аккаунты с весом ≥5K fol / known.
        and _is_weighted_account(_user_of(post, neg_payload))
    ][:3]
    strong_bullish = [
        {
            "text": compact_text(text, 100),
            "id": post.get("id", ""),
            "username": _username_of(post, bull_payload),
            "followers": int(
                ((_user_of(post, bull_payload).get("public_metrics") or {}).get("followers_count"))
                or 0
            ),
        }
        for post, text in ((p, str(p.get("text") or "")) for p in bullish_posts)
        if not any(sp in text.lower() for sp in VOTE_SPAM_PATTERNS)
        # негатив (scam/rug/dump) не должен попадать в «драйвер» — даже от KOL
        and not any(
            term in text.lower()
            for term in NEGATIVE_TERMS + SCAM_PATTERNS + ("scam", "dump", "rugged", "honeypot")
        )
        and (
            any(term in text.lower() for term in POSITIVE_TERMS + TOLY_TERMS + AI_BUY_TERMS)
            or any(
                inf in (_username_of(post, bull_payload).lower(), text.lower())
                for inf in KNOWN_INFLUENCERS
            )
            # двусмысленное bare BURNIE от KOL тоже драйвер
            or (
                is_bare_burnie(text)
                and int(
                    ((_user_of(post, bull_payload).get("public_metrics") or {}).get("followers_count"))
                    or 0
                )
                >= CATALYST_MIN_FOLLOWERS
            )
        )
    ][:5]
    # Known influencers / high-follower first
    strong_bullish.sort(
        key=lambda b: (
            not any(inf in b["username"].lower() or inf in b["text"].lower() for inf in KNOWN_INFLUENCERS),
            -int(b.get("followers") or 0),
        )
    )

    # Track follower growth from previous snapshot
    prev_followers = 0
    if OUTFILE.exists():
        try:
            with OUTFILE.open("r") as fh:
                lines = fh.readlines()
                if lines:
                    prev = json.loads(lines[-1])
                    prev_followers = prev.get("followers", 0)
        except (json.JSONDecodeError, OSError):
            pass
    follower_delta = followers - prev_followers if prev_followers else 0

    # Weighted sentiment: Toly + AI + catalyst (крупные/политические) = bullish multipliers
    clean_bull_count = len(clean_bullish_texts)
    catalyst_boost = 0
    if any(c.get("tier") in ("politician", "mega", "known") for c in catalysts):
        catalyst_boost = 4
    elif any(c.get("tier") == "large" for c in catalysts):
        catalyst_boost = 3
    elif catalysts:
        catalyst_boost = 2
    bullish_score = (
        (toly_hits * 3)
        + (ai_buy_hits * 2)
        + pos_hits
        + catalyst_boost
        + (1 if clean_bull_count >= 5 else 0)
        + (1 if follower_delta > 50 else 0)
    )
    bearish_score = neg_hits + len(strong_negative)

    if strong_negative and neg_hits >= 3 and bullish_score < bearish_score:
        sentiment = "neg"
    elif bullish_score > bearish_score:
        sentiment = "pos"
    elif toly_hits >= 1 or ai_buy_hits >= 2 or catalyst_boost >= 3:
        sentiment = "pos"
    else:
        sentiment = "neutral"

    notes = [
        f"negative scan: {len(negative_posts)} hits, strong_hits={len(strong_negative)}",
        f"catalyst scan: {len(catalyst_posts)} posts, catalysts={len(catalysts)}, "
        f"toly={toly_hits} ai_buy={ai_buy_hits}, vote_spam={vote_spam_hits}",
        f"sentiment_terms neg={neg_hits} pos={pos_hits} toly={toly_hits} ai={ai_buy_hits}",
    ]
    if catalysts:
        top_c = catalysts[0]
        notes.append(
            f"top_catalyst: @{top_c['user']} ({top_c['followers']:,} fol, "
            f"{top_c['tier']}, {top_c['type']})"
        )
    if followers:
        delta_str = f"+{follower_delta}" if follower_delta > 0 else str(follower_delta)
        notes.append(f"@{ACCOUNT}: {followers} followers ({delta_str}), {tweet_count} tweets")
    if strong_negative:
        notes.append("strong_negative: " + " | ".join(n.get("text", "") for n in strong_negative))
    elif not errors:
        notes.append("no rug-pull accusations or dump warnings detected")
    if strong_bullish:
        notes.append("strong_bullish: " + " | ".join(b["text"] for b in strong_bullish))
    if errors:
        notes.extend(errors)

    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "followers": followers,
        "followers_delta": follower_delta,
        "tweets": tweet_count,
        "sentiment": sentiment,
        "neg_hits": neg_hits,
        "pos_hits": pos_hits,
        "toly_hits": toly_hits,
        "ai_buy_hits": ai_buy_hits,
        "vote_spam_hits": vote_spam_hits,
        "strong_negative": strong_negative,
        "strong_bullish": strong_bullish,
        # катализатор (новое) + обратная совместимость kol_*
        "catalysts": catalysts,
        "catalyst_count": len(catalysts),
        "kol_mentions": kol_mentions,
        "kol_engagement": kol_engagement,
        "notes": "; ".join(notes),
        # X API сбой (rate-limit/ошибка) — чтобы main не молчал, а слал деградированный отчёт.
        "x_api_errors": list(errors),
    }
    return snapshot, strong_negative


BURNIE_MINT = "CGEDT9QZDvvH5GmVkWJH2BXiMJqMJySC9ihWyr7Spump"


def _dex_headers() -> dict[str, str]:
    return {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) RAB9/1.0"}


def _best_pair(pairs: list[Any]) -> dict[str, Any] | None:
    """Пара с максимальной ликвидностью из списка DexScreener pairs."""
    valid = [p for p in pairs if isinstance(p, dict)]
    if not valid:
        return None
    return sorted(
        valid,
        key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0),
        reverse=True,
    )[0]


def fetch_dex_metrics(mint: str | None = None) -> dict[str, Any]:
    """Fetch token market data from DexScreener (free, no X credits).

    mint=None → BURNIE. Возвращает price/mc/vol/change/buy_ratio.
    """
    out: dict[str, Any] = {"ok": False}
    token = mint or BURNIE_MINT
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token}"
        req = urllib.request.Request(url, headers=_dex_headers())
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pairs = data.get("pairs") or []
        best = _best_pair(pairs)
        if not best:
            return out
        price_usd = best.get("priceUsd")
        txns_h24 = best.get("txns", {}).get("h24") or {}
        buy_24h = txns_h24.get("buys")
        sell_24h = txns_h24.get("sells")
        buy_ratio = None
        if buy_24h is not None and sell_24h is not None:
            try:
                b, s = int(buy_24h), int(sell_24h)
                buy_ratio = round(b / s, 2) if s > 0 else None
            except (TypeError, ValueError):
                pass
        out.update(
            {
                "ok": True,
                "price_usd": float(price_usd) if price_usd else None,
                "market_cap": best.get("marketCap"),
                "volume_24h": best.get("volume", {}).get("h24"),
                "liquidity_usd": best.get("liquidity", {}).get("usd"),
                "change_24h": best.get("priceChange", {}).get("h24"),
                "buys_24h": buy_24h,
                "sells_24h": sell_24h,
                "buy_ratio": buy_ratio,
                "txns_24h": best.get("txns", {}).get("h24"),
                "pair_url": best.get("url"),
                "symbol": (best.get("baseToken") or {}).get("symbol"),
            }
        )
    except Exception:
        pass
    return out


def fetch_competitors() -> dict[str, Any]:
    """PolitiFi-соседи BURNIE через DexScreener (batch tokens API, без X).

    Возвращает список {symbol, price, change_24h, mc, vol} + сравнение с BURNIE.
    """
    out: dict[str, Any] = {"ok": False, "tokens": [], "attention_flow": None}
    try:
        addrs = [t["address"] for t in COMPETITOR_TOKENS if t.get("address")]
        if not addrs:
            return out
        # DexScreener: несколько mint через запятую
        url = "https://api.dexscreener.com/latest/dex/tokens/" + ",".join(addrs)
        req = urllib.request.Request(url, headers=_dex_headers())
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pairs = data.get("pairs") or []
        # best pair per base address
        by_addr: dict[str, dict[str, Any]] = {}
        for p in pairs:
            if not isinstance(p, dict):
                continue
            addr = ((p.get("baseToken") or {}).get("address") or "").strip()
            if not addr:
                continue
            prev = by_addr.get(addr)
            liq = float((p.get("liquidity") or {}).get("usd") or 0)
            if prev is None or liq > float((prev.get("liquidity") or {}).get("usd") or 0):
                by_addr[addr] = p
        # map address → meta from COMPETITOR_TOKENS
        meta = {t["address"]: t for t in COMPETITOR_TOKENS}
        tokens: list[dict[str, Any]] = []
        for addr, conf in meta.items():
            p = by_addr.get(addr)
            if not p:
                tokens.append(
                    {
                        "symbol": conf.get("symbol"),
                        "name": conf.get("name"),
                        "address": addr,
                        "ok": False,
                    }
                )
                continue
            price = p.get("priceUsd")
            tokens.append(
                {
                    "symbol": conf.get("symbol") or (p.get("baseToken") or {}).get("symbol"),
                    "name": conf.get("name"),
                    "address": addr,
                    "ok": True,
                    "price_usd": float(price) if price else None,
                    "market_cap": p.get("marketCap"),
                    "volume_24h": (p.get("volume") or {}).get("h24"),
                    "change_24h": (p.get("priceChange") or {}).get("h24"),
                }
            )
        # «внимание перетекает»: кто растёт быстрее BURNIE (change_24h)
        out.update({"ok": True, "tokens": tokens})
    except Exception:
        pass
    return out


def competitors_attention_note(
    burnie_chg: float | None,
    competitors: dict[str, Any],
) -> str | None:
    """Кто растёт быстрее BURNIE → внимание перетекает к ним."""
    if not competitors.get("ok"):
        return None
    try:
        b = float(burnie_chg) if burnie_chg is not None else None
    except (TypeError, ValueError):
        b = None
    faster: list[str] = []
    slower: list[str] = []
    for t in competitors.get("tokens") or []:
        if not t.get("ok") or t.get("change_24h") is None:
            continue
        try:
            c = float(t["change_24h"])
        except (TypeError, ValueError):
            continue
        sym = t.get("symbol") or "?"
        if b is None:
            if c >= 5:
                faster.append(f"{sym} ({c:+.1f}%)")
            continue
        if c > b + 3:
            faster.append(f"{sym} ({c:+.1f}% vs BURNIE {b:+.1f}%)")
        elif b > c + 3:
            slower.append(sym)
    if faster:
        return "внимание перетекает → " + ", ".join(faster[:4])
    if b is not None and b >= 5 and slower:
        return f"BURNIE лидирует vs {', '.join(slower[:3])}"
    return None


def calendar_boost(now: datetime | None = None) -> dict[str, Any]:
    """Календарный бонус: если сегодня ±3д от события POLITICAL_CALENDAR.

    Returns: {active, bonus, event, date, days_to}
    """
    now = now or datetime.now(timezone.utc)
    today = now.date()
    best: dict[str, Any] | None = None
    for item in POLITICAL_CALENDAR:
        try:
            d = datetime.strptime(item["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        delta = (d - today).days
        # Бонус только для событий ВПЕРЕДИ (или сегодня): days_to >= 0.
        # Событие в прошлом не даёт очков — рынок уже отыграл или не отыграл.
        if 0 <= delta <= CALENDAR_WINDOW_DAYS:
            cand = {
                "active": True,
                "bonus": CALENDAR_VIRALITY_BONUS,
                "event": item.get("event", ""),
                "date": item["date"],
                "days_to": (d - today).days,
            }
            if best is None or abs(cand["days_to"]) < abs(best["days_to"]):
                best = cand
    if best:
        return best
    return {"active": False, "bonus": 0, "event": None, "date": None, "days_to": None}


def _seen_catalyst_ids(path: Path = OUTFILE, max_lines: int = 40) -> set[str]:
    """Id катализаторов, уже виденных в последних снимках JSONL (для first-seen cooldown).

    hard_alert должен срабатывать только при ПЕРВОМ появлении catalyst id,
    иначе один large RT пушится каждый прогон, пока пост в окне свежести.
    """
    seen: set[str] = set()
    if not path.exists():
        return seen
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return seen
    for line in lines[-max_lines:]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        for c in row.get("catalysts") or []:
            if isinstance(c, dict):
                seen.add(_catalyst_attr_id(c))
    return seen


def compute_hard_alert(
    catalysts: list[dict[str, Any]],
    seen_ids: set[str] | None = None,
) -> bool:
    """Event-first: hard-push только RT/quote/reply офиц. от large/mega/known/politician.

    Обычные KOL (bare BURNIE, ticker, mention) идут в score, но НЕ в пуш.
    first-seen: catalyst, уже виденный в прошлых снимках, не пушится повторно.
    """
    seen = seen_ids if seen_ids is not None else _seen_catalyst_ids()
    for c in catalysts or []:
        if c.get("type") in OFFICIAL_TOUCH_TYPES and c.get("tier") in HARD_ALERT_TIERS:
            if _catalyst_attr_id(c) in seen:
                continue  # уже пушили — не спамим
            return True
    return False


def _catalyst_attr_id(c: dict[str, Any]) -> str:
    """Стабильный id катализатора для attribution loop."""
    uid = str(c.get("id") or c.get("post_id") or "")
    user = (c.get("user") or "").lower()
    ctype = c.get("type") or "other"
    if uid:
        return f"{user}:{ctype}:{uid}"
    return f"{user}:{ctype}:{c.get('text', '')[:40]}"


def _price_snapshot(price: Any, mc: Any, vol: Any) -> dict[str, Any]:
    return {
        "price": float(price) if price is not None else None,
        "mc": float(mc) if mc is not None else None,
        "vol": float(vol) if vol is not None else None,
    }


def _pct_delta(t0_price: Any, now_price: Any) -> float | None:
    try:
        a = float(t0_price)
        b = float(now_price)
        if a == 0:
            return None
        return round((b - a) / a * 100.0, 2)
    except (TypeError, ValueError):
        return None


def load_attribution_events(path: Path = OUTFILE, max_lines: int = 80) -> list[dict[str, Any]]:
    """Собрать attribution-события из JSONL (последние max_lines), dedupe по id.

    Более поздняя запись побеждает (дозаполнение h1/h6/h24).
    JSONL-совместимо: старые строки без attribution просто пропускаются.
    """
    by_id: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return []
    for line in lines[-max_lines:]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        attr = row.get("attribution")
        if not isinstance(attr, dict):
            continue
        for ev in attr.get("events") or []:
            if not isinstance(ev, dict) or not ev.get("id"):
                continue
            by_id[str(ev["id"])] = ev
    return list(by_id.values())


def build_attribution(
    catalysts: list[dict[str, Any]],
    price: Any,
    mc: Any,
    vol: Any,
    now: datetime | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Attribution loop: T0 для новых катализаторов + дозаполнение 1h/6h/24h.

    Секция snapshot['attribution']:
      events: [{id, type, user, tier, ts_t0, t0:{price,mc,vol}, h1?, h6?, h24?}]
      summary: {n_events, avg_h24_pct, best_type}
    """
    now = now or datetime.now(timezone.utc)
    now_ts = now.timestamp()
    snap = _price_snapshot(price, mc, vol)
    events: dict[str, dict[str, Any]] = {}
    for ev in history or []:
        if isinstance(ev, dict) and ev.get("id"):
            events[str(ev["id"])] = dict(ev)

    # Дозаполнить окна для старых катализаторов
    for eid, ev in list(events.items()):
        try:
            t0_dt = datetime.fromisoformat(str(ev.get("ts_t0") or "").replace("Z", "+00:00"))
            if t0_dt.tzinfo is None:
                t0_dt = t0_dt.replace(tzinfo=timezone.utc)
            age = now_ts - t0_dt.timestamp()
        except (TypeError, ValueError):
            continue
        t0_px = (ev.get("t0") or {}).get("price")
        for win_name, win_sec in ATTRIBUTION_WINDOWS:
            if ev.get(win_name):
                continue
            if age < win_sec * ATTRIBUTION_WINDOW_TOLERANCE:
                continue
            # Окно созрело — снять текущую цену и дельту
            d_pct = _pct_delta(t0_px, snap.get("price"))
            ev[win_name] = {
                "ts": now.isoformat(),
                **snap,
                "price_delta_pct": d_pct,
            }
        events[eid] = ev

    # Новые катализаторы → T0 (если id ещё не видели)
    for c in catalysts or []:
        eid = _catalyst_attr_id(c)
        if eid in events:
            continue
        events[eid] = {
            "id": eid,
            "type": c.get("type"),
            "user": c.get("user"),
            "tier": c.get("tier"),
            "ts_t0": now.isoformat(),
            "t0": snap,
            "h1": None,
            "h6": None,
            "h24": None,
        }

    # Summary: события с заполненным h24
    h24_pcts: list[float] = []
    type_avg: dict[str, list[float]] = {}
    for ev in events.values():
        h24 = ev.get("h24") or {}
        pct = h24.get("price_delta_pct")
        if pct is None:
            continue
        try:
            p = float(pct)
        except (TypeError, ValueError):
            continue
        h24_pcts.append(p)
        t = str(ev.get("type") or "other")
        type_avg.setdefault(t, []).append(p)

    avg_h24 = round(sum(h24_pcts) / len(h24_pcts), 2) if h24_pcts else None
    best_type = None
    if type_avg:
        best_type = max(
            type_avg.items(),
            key=lambda kv: sum(kv[1]) / len(kv[1]),
        )[0]

    # Храним не бесконечно: активные (нет h24) + завершённые за 7 суток
    kept: list[dict[str, Any]] = []
    for ev in events.values():
        try:
            t0_dt = datetime.fromisoformat(str(ev.get("ts_t0") or "").replace("Z", "+00:00"))
            if t0_dt.tzinfo is None:
                t0_dt = t0_dt.replace(tzinfo=timezone.utc)
            age_days = (now_ts - t0_dt.timestamp()) / 86400
        except (TypeError, ValueError):
            age_days = 0
        if ev.get("h24") is None or age_days <= 7:
            kept.append(ev)
    kept.sort(key=lambda e: str(e.get("ts_t0") or ""), reverse=True)

    return {
        "events": kept[:60],
        "summary": {
            "n_events": len(h24_pcts),
            "n_tracked": len(kept),
            "avg_h24_pct": avg_h24,
            "best_type": best_type,
        },
    }


def format_attribution_line(attr: dict[str, Any] | None) -> str | None:
    """Строка отчёта: «Атрибуция: N событий, средний +X% за 24ч, лучший тип: Y»."""
    if not attr or not isinstance(attr, dict):
        return None
    s = attr.get("summary") or {}
    n = s.get("n_events") or 0
    tracked = s.get("n_tracked") or 0
    avg = s.get("avg_h24_pct")
    best = s.get("best_type")
    if n == 0 and tracked == 0:
        return None
    if n == 0:
        return f"📈 Атрибуция: 0 завершённых / {tracked} в трекинге (ждём 1h/6h/24h)"
    avg_s = f"{float(avg):+.1f}%" if avg is not None else "n/a"
    best_s = best or "?"
    return f"📈 Атрибуция: {n} событий, средний {avg_s} за 24ч, лучший тип: {best_s}"


def send_telegram(text: str) -> bool:
    """Send alert to configured Telegram chat via Bot API (no extra deps)."""
    try:
        env_path = RAB9_DIR / ".env"
        token = ""
        chat_id = ""
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip("\"'")
                elif line.startswith("TELEGRAM_GROUP_ID="):
                    chat_id = line.split("=", 1)[1].strip().strip("\"'")
        if not token or not chat_id:
            return False
        destination = check_destination(chat_id)
        if destination.verdict != Verdict.ALLOW:
            print(f"[telegram] destination blocked: {chat_id} ({destination.reason})", file=sys.stderr)
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": text[:3500]}
        ).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


RISK_TERMS_RU = {
    "rug": "обвинение в скаме (rug pull)",
    "rugpull": "обвинение в скаме (rug pull)",
    "rug pull": "обвинение в скаме (rug pull)",
    "dumped": "кто-то слил токен",
    "dump warning": "предупреждение о сливе",
    "exit liquidity": "«выходная ликвидность» — покупателей разводят",
    "dev sold": "разработчик продал",
    "honeypot": "ловушка (нельзя продать)",
    "scam": "скам",
    "abandoned": "токен заброшен",
    "dead": "токен мёртв",
}

DRIVER_TERMS_RU = {
    "moonshot": "голосование за листинг на Moonshot",
    "listing": "листинг",
    "vote": "голосование за листинг",
    "toly": "упоминание Toly (основателя Solana)",
    "anatoly": "упоминание Toly (основателя Solana)",
    "buy signal": "сигнал на покупку",
    "strong buy": "сигнал на покупку",
    "accumulation": "накопление",
    "primed": "«взведён» — готов к росту",
    "breakout": "пробой уровня",
    "pump": "памп",
    "100x": "ожидание 100x",
    "700x": "история успеха сигнальщика (700x)",
    "2000x": "история успеха сигнальщика (2000x)",
    "1000x": "история успеха сигнальщика (1000x)",
    "500x": "история успеха сигнальщика (500x)",
    "begged": "призыв сигнальщика «я говорил покупать»",
    "bought": "призыв сигнальщика «я покупал»",
}


def explain_terms(text: str, terms_ru: dict[str, str], limit: int = 3) -> str:
    """Map English meme-coins terms found in a post to plain Russian."""
    low = text.lower()
    found = []
    for term, ru in terms_ru.items():
        if term in low and ru not in found:
            found.append(ru)
        if len(found) >= limit:
            break
    return ", ".join(found) if found else "нет ключевых слов"


KOL_FOLLOWER_THRESHOLD = CATALYST_MIN_FOLLOWERS  # алиас: 5k = порог KOL
KNOWN_INFLUENCERS = (
    "aeyakovenko",  # Toly
    "toly",
    "elonmusk",
    "realDonaldTrump",
    "ansem",
    "blknoiz06",
    "0xmert_",
    "rajgokal",
    "alphaagentcall",
    "alphaagentcallz",
)


def fetch_kol_mentions() -> dict[str, Any]:
    """Fallback KOL-скан (radar_x OAuth1), если catalyst scan в build_snapshot пуст.

    Основной путь: extract_catalysts() внутри build_snapshot (3-й X-вызов, raw).
    Этот fallback — fail-open, НЕ тратит слот если catalysts уже есть.
    """
    out: dict[str, Any] = {"ok": False, "mentions": []}
    try:
        import sys as _sys

        _sys.path.insert(0, str(RAB9_DIR))
        from radar_x import search_x

        res = search_x("burnie")
        if not res.get("ok"):
            return out
        posts = res.get("posts") or []
        mentions: list[dict[str, Any]] = []
        for p in posts:
            m = re.match(r"@(\w+)\s*\(([\d,]+)\)", p or "")
            if not m:
                continue
            username, fol_s = m.groups()
            fol = int(fol_s.replace(",", ""))
            if fol >= KOL_FOLLOWER_THRESHOLD or username.lower() in {
                h.lower() for h in KNOWN_INFLUENCERS
            }:
                mentions.append({"user": username, "followers": fol, "text": p[:120]})
        out.update(
            {
                "ok": True,
                "mentions": mentions,
                "engagement": res.get("engagement") or {},
            }
        )
    except Exception:
        pass
    return out


def fetch_holder_risk() -> dict[str, Any]:
    """Fetch holder distribution + security from GMGN enrich (free, no X credits).

    Returns top-10 holders with % and tags (bundler/sniper/creator/dev_team),
    holder count, smart money score, and security flags.
    """
    out: dict[str, Any] = {"ok": False}
    try:
        import sys as _sys

        _sys.path.insert(0, str(RAB9_DIR))
        from gmgn_client import enrich_token

        r = enrich_token(BURNIE_MINT)
        if not r.get("ok"):
            return out
        holders = []
        for h in (r.get("top_holders") or [])[:10]:
            tags = h.get("tags") or []
            holders.append(
                {
                    "addr": (h.get("address") or "")[:10],
                    "pct": h.get("pct"),
                    "usd": h.get("usd"),
                    "tags": [t for t in tags if t not in ("top_holder",)],
                }
            )
        sec = r.get("security") or {}
        out.update(
            {
                "ok": True,
                "holder_count": r.get("holder_count"),
                "top_holders": holders,
                "smart_money_score": r.get("smart_money_score"),
                "security": {
                    "honeypot": sec.get("honeypot"),
                    "renounced_mint": sec.get("renounced_mint"),
                    "renounced_freeze": sec.get("renounced_freeze"),
                    "locked": sec.get("locked"),
                    "buy_tax": sec.get("buy_tax"),
                    "sell_tax": sec.get("sell_tax"),
                },
            }
        )
    except Exception:
        pass
    return out


def fetch_rugcheck() -> dict[str, Any]:
    """Fetch RugCheck.xyz risk level (free public API)."""
    out: dict[str, Any] = {"ok": False}
    try:
        import sys as _sys

        _sys.path.insert(0, str(RAB9_DIR))
        from rugcheck_client import check_token

        rep = check_token(BURNIE_MINT)
        if not rep.get("ok"):
            return out
        out.update(
            {
                "ok": True,
                "level": rep.get("level"),
                "score": rep.get("score"),
                "rugged": rep.get("rugged"),
            }
        )
    except Exception:
        pass
    return out


def fetch_smart_money_flow() -> dict[str, Any]:
    """Detect wallet accumulation: smart money / KOL buys vs sells on BURNIE.

    Uses GMGN track feed (read-only, free). Fail-open.
    """
    out: dict[str, Any] = {"ok": False, "signal": "none"}
    try:
        import sys as _sys

        _sys.path.insert(0, str(RAB9_DIR))
        from gmgn_client import track_token_flow

        flow = track_token_flow(BURNIE_MINT, limit=100)
        if not flow.get("ok"):
            return out
        sm = flow.get("smartmoney") or {}
        kol = flow.get("kol") or {}
        out.update(
            {
                "ok": True,
                "signal": flow.get("signal", "none"),
                "sm_buys": sm.get("buys", 0),
                "sm_sells": sm.get("sells", 0),
                "sm_usd_buy": sm.get("usd_buy", 0.0),
                "sm_usd_sell": sm.get("usd_sell", 0.0),
                "kol_buys": kol.get("buys", 0),
                "kol_sells": kol.get("sells", 0),
                "kol_usd_buy": kol.get("usd_buy", 0.0),
                "kol_usd_sell": kol.get("usd_sell", 0.0),
            }
        )
    except Exception:
        pass
    return out


def fetch_chart_ta() -> dict[str, Any]:
    """Fetch real TA indicators via chart_analysis (GMGN OHLCV, free). Fail-open."""
    out: dict[str, Any] = {"ok": False}
    try:
        import sys as _sys

        _sys.path.insert(0, str(RAB9_DIR))
        from chart_analysis import analyze

        res = analyze(BURNIE_MINT)
        if not res.get("ok"):
            return out
        out.update(
            {
                "ok": True,
                "phase": res.get("phase"),
                "phase_confidence": res.get("phase_confidence"),
                "rsi": res.get("rsi"),
                "macd_crossover": res.get("macd_crossover"),
                "volume_divergence": res.get("volume_divergence"),
                "sma20": res.get("sma20"),
                "sma50": res.get("sma50"),
                "price": res.get("price"),
                "support": (res.get("support") or {}).get("price"),
                "resistance": (res.get("resistance") or {}).get("price"),
                "ath_drawdown": res.get("ath_drawdown"),
                "accumulation_score": res.get("accumulation_score"),
                "distribution_score": res.get("distribution_score"),
            }
        )
    except Exception:
        pass
    return out


def compute_weighted_score(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compute a weighted composite score — sum of all parameters with weights.

    Final verdict is based on the TOTAL, not any single metric.
    Weights (sum = 100):
      1. Sentiment (X)            — 20
      2. Virality (KOL/catalyst)  — 20  (было 15; +5 с TA)
      3. TA phase (chart)         — 15  (было 20; −5 в virality)
      4. Smart money flow         — 15
      5. Market momentum          — 10
      6. Holder risk (bundlers)   — 10
      7. Security / RugCheck      — 10
    Календарный бонус (POLITICAL_CALENDAR ±3д) добавляется к virality.
    Each component contributes points; verdict derives from total.
    """
    S = {k: 0 for k in ("sentiment", "ta", "virality", "smart_money", "market", "holders", "security")}

    # 1. Sentiment (X) — max 20
    pos = snapshot.get("pos_hits", 0)
    neg = snapshot.get("neg_hits", 0)
    if neg > 0:
        S["sentiment"] = max(0, min(20, pos * 3 - neg * 8))
    else:
        S["sentiment"] = min(20, pos * 2)
    if snapshot.get("toly_hits", 0) > 0:
        S["sentiment"] = min(20, S["sentiment"] + 4)  # Toly = strong multiplier

    # 2. TA phase — max 15 (было 20; 5 пунктов → virality)
    ta = snapshot.get("chart_ta") or {}
    if ta.get("ok"):
        phase = ta.get("phase")
        if phase == "accumulation":
            S["ta"] = 15
        elif phase == "decay":
            S["ta"] = 6  # post-pump base — pre-catalyst zone
        elif phase == "markup":
            S["ta"] = 9  # running but late
        elif phase == "distribution":
            S["ta"] = 2
        vd = ta.get("volume_divergence")
        if vd == "bullish_divergence":
            S["ta"] = min(15, S["ta"] + 4)
        elif vd == "bearish_divergence":
            S["ta"] = max(0, S["ta"] - 5)
        rsi = ta.get("rsi")
        if rsi is not None:
            if rsi < 35:
                S["ta"] = min(15, S["ta"] + 2)  # oversold → upside room
            elif rsi > 70:
                S["ta"] = max(0, S["ta"] - 3)  # overbought → distribution risk

    # 3. Virality / катализатор — max 20 (было 15; +5 с TA)
    # Катализатор важнее «просто KOL упомянул $BURNIE»: RT Маска/политика = лесной пожар.
    catalysts = snapshot.get("catalysts") or []
    kol = snapshot.get("kol_mentions") or []
    eng = snapshot.get("kol_engagement") or {}
    if catalysts:
        # База: число сигналов, capped
        S["virality"] = min(12, len(catalysts) * 3)
        tiers = {c.get("tier") for c in catalysts}
        types = {c.get("type") for c in catalysts}
        if "politician" in tiers:
            S["virality"] = min(20, S["virality"] + 10)  # политик = высший приоритет
        elif "known" in tiers or "mega" in tiers:
            S["virality"] = min(20, S["virality"] + 8)  # Маск/Трамп/Toly-уровень
        elif "large" in tiers:
            S["virality"] = min(20, S["virality"] + 5)  # ≥50k fol
        elif "kol" in tiers:
            S["virality"] = min(20, S["virality"] + 3)
        # Тип взаимодействия: RT офиц. сильнее bare-упоминания
        if "rt_fresh" in types:
            S["virality"] = min(20, S["virality"] + 4)  # свежий RT = самый ранний сигнал
        elif "rt_official" in types:
            S["virality"] = min(20, S["virality"] + 3)
        elif "quote_fresh" in types or "quote_official" in types or "reply_official" in types:
            S["virality"] = min(20, S["virality"] + 2)
        elif "bare_burnie" in types:
            S["virality"] = min(20, S["virality"] + 2)  # двусмысленное слово BURNIE
        if "like_spike" in types:
            S["virality"] = min(20, S["virality"] + 3)  # аномальный всплеск лайков
        likes = eng.get("likes", 0)
        if likes >= 50:
            S["virality"] = min(20, S["virality"] + 2)
    elif kol:
        # fallback: старый kol_mentions без типизации
        S["virality"] = min(20, len(kol) * 4)
        likes = eng.get("likes", 0)
        if likes >= 50:
            S["virality"] = min(20, S["virality"] + 5)
        elif likes >= 10:
            S["virality"] = min(20, S["virality"] + 2)

    # Календарный бонус: ±3 дня от дебатов/праймериз/Election Day
    cal = snapshot.get("calendar") or calendar_boost()
    if cal.get("active") and cal.get("bonus"):
        S["virality"] = min(20, S["virality"] + int(cal["bonus"]))

    # 4. Smart money flow — max 15
    sm = snapshot.get("smart_money") or {}
    if sm.get("ok"):
        sig = sm.get("signal")
        if sig == "accumulation":
            S["smart_money"] = 15
        elif sig == "mixed":
            S["smart_money"] = 8
        elif sig == "distribution":
            S["smart_money"] = 2
        else:
            S["smart_money"] = 5  # no data / neutral

    # 5. Market momentum — max 10
    chg = snapshot.get("change_24h")
    buy_r = snapshot.get("buy_ratio")
    if chg is not None:
        try:
            c = float(chg)
            if c >= 10:
                S["market"] = 10
            elif c >= 3:
                S["market"] = 7
            elif c >= -3:
                S["market"] = 5  # flat — neutral
            elif c >= -10:
                S["market"] = 3
            else:
                S["market"] = 1
        except (TypeError, ValueError):
            S["market"] = 5
    if buy_r is not None:
        try:
            br = float(buy_r)
            if br >= 1.3:
                S["market"] = min(10, S["market"] + 3)
            elif br < 0.7:
                S["market"] = max(0, S["market"] - 3)
        except (TypeError, ValueError):
            pass

    # 6. Holder risk — max 10 (bundlers = risk)
    hr = snapshot.get("holder_risk") or {}
    if hr.get("ok"):
        S["holders"] = 8  # base
        top = hr.get("top_holders") or []
        bundlers = sum(1 for h in top if "bundler" in (h.get("tags") or []))
        if bundlers == 0:
            S["holders"] = 10
        elif bundlers <= 2:
            S["holders"] = 7
        elif bundlers <= 4:
            S["holders"] = 4  # BURNIE: 4 bundlers in top-5 → risk
        else:
            S["holders"] = 2
        top10_pct = sum(float(h.get("pct") or 0) for h in top)
        if top10_pct > 50:
            S["holders"] = max(0, S["holders"] - 3)

    # 7. Security / RugCheck — max 10
    sec = hr.get("security") or {}
    if hr.get("ok"):
        if sec.get("honeypot"):
            S["security"] = 0
        elif sec.get("renounced_mint") and sec.get("renounced_freeze") and sec.get("locked"):
            S["security"] = 10
        elif sec.get("renounced_mint"):
            S["security"] = 7
        else:
            S["security"] = 4
    rc = snapshot.get("rugcheck") or {}
    if rc.get("ok"):
        lvl = rc.get("level")
        if lvl == "low":
            S["security"] = max(0, S["security"] + 2)
        elif lvl == "high":
            S["security"] = max(0, S["security"] - 8)
        elif lvl == "medium":
            S["security"] = max(0, S["security"] - 3)
    # cap: security не может превышать max 10 (base 10 + rugcheck low = 12 — баг)
    S["security"] = min(10, S["security"])

    total = sum(S.values())
    if total >= 75:
        verdict = "СЛЕДИТЬ ВНИМАТЕЛЬНО"
    elif total >= 55:
        verdict = "СЛЕДИТЬ"
    elif total >= 35:
        verdict = "НАБЛЮДАТЬ"
    else:
        verdict = "НЕ СЛЕДИТЬ"
    return {"total": total, "components": S, "verdict": verdict}


def detect_warmup(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Detect if pre-election warmup is starting via TA confluence + catalysts.

    Warmup signals (meme-coin TA, not stock-style % thresholds):
      - volume divergence BULLISH (price flat + volume rising = accumulation)
      - MACD bullish crossover
      - price broke above 14-day range with volume (range breakout, not %)
      - KOL mentions appeared (virality)
      - smart money signal == accumulation
      - RSI oversold → recovering (<35 with bullish MACD)
    Returns dict with 'warming' bool and readable 'signals' list.
    """
    signals: list[str] = []
    ta = snapshot.get("chart_ta") or {}

    # TA-based signals (from real OHLCV, GMGN)
    if ta.get("ok"):
        vd = ta.get("volume_divergence")
        if vd == "bullish_divergence":
            signals.append("объёмная дивергенция (накопление)")
        mc = ta.get("macd_crossover")
        if mc == "bullish":
            signals.append("MACD бычий кроссовер")
        rsi = ta.get("rsi")
        if rsi is not None and rsi < 35 and mc == "bullish":
            signals.append(f"RSI {rsi} разворот от перепроданности")
        price = ta.get("price")
        resist = ta.get("resistance")
        if price and resist and float(price) > float(resist):
            signals.append(f"пробой сопротивления (${float(resist):.6f})")
        sma20 = ta.get("sma20")
        if price and sma20 and float(price) > float(sma20) and vd == "bullish_divergence":
            signals.append("цена выше SMA20 + накопление")

    # Volume jump (catalyst confirmation)
    vol = snapshot.get("volume_24h")
    prev_vol = snapshot.get("prev_volume_24h")
    if vol and prev_vol and float(prev_vol) > 0:
        ratio = float(vol) / float(prev_vol)
        if ratio >= 2.0:
            signals.append(f"объём ×{ratio:.1f} за замер")

    # KOL / catalyst / smart money
    catalysts = snapshot.get("catalysts") or []
    if catalysts:
        top = catalysts[0]
        type_ru = {
            "rt_official": "ретвит офиц. аккаунта",
            "reply_official": "ответ офиц. аккаунту",
            "quote_official": "цитата офиц. аккаунта",
            "mention_official": "упоминание офиц. аккаунта",
            "bare_burnie": "голое слово BURNIE",
            "ticker_mention": "тикер $BURNIE",
        }.get(top.get("type") or "", top.get("type") or "взаимодействие")
        signals.append(
            f"катализатор: @{top.get('user')} ({int(top.get('followers') or 0):,} fol) — {type_ru}"
        )
        if any(c.get("tier") == "politician" for c in catalysts):
            signals.append("ПОЛИТИК / watchlist затронул BURNIE")
        elif any(c.get("tier") in ("mega", "known") for c in catalysts):
            signals.append("MEGA/known аккаунт затронул BURNIE")
    else:
        kol = snapshot.get("kol_mentions") or []
        if kol:
            signals.append(f"{len(kol)} упоминаний от крупных аккаунтов")
    sm = snapshot.get("smart_money") or {}
    if sm.get("ok") and sm.get("signal") == "accumulation":
        signals.append("smart money накапливает")

    return {"warming": bool(signals), "signals": signals}


def translate_post(text: str) -> str:
    """Translate an X post to Russian via DeepSeek (cheap, fail-open to original)."""
    try:
        import sys as _sys

        _sys.path.insert(0, str(RAB9_DIR))
        from token_intel import ask_deepseek

        prompt = (
            "Ты переводишь посты из X/Twitter о крипто-мемкоине BURNIE (политическая сатира "
            "про Берни Сандерса). Пост может быть неформальным, с мемами и сарказмом.\n"
            "Переведи на русский, сохрани смысл и тон. Верни ТОЛЬКО перевод, "
            "одним-двумя предложениями, без кавычек. НЕ пиши 'спам/шум' — переводи даже "
            "непонятный текст, если он не является откровенной рекламой голосования за листинг.\n\n"
            f"Пост: {text[:280]}"
        )
        res = ask_deepseek(prompt)
        if res and not res.startswith(("DeepSeek", "OpenRouter")):
            # keep only first paragraph — models sometimes append commentary
            first_line = res.strip().splitlines()[0].strip()
            return first_line[:220]
    except Exception:
        pass
    return text


def post_url(username: str, post_id: str) -> str:
    if username and post_id:
        return f"https://x.com/{username}/status/{post_id}"
    return ""


def format_alert(snapshot: dict[str, Any]) -> str:
    """Build a human-readable BURNIE report with verdict (plain Russian)."""
    senti = snapshot["sentiment"]
    if senti == "neg":
        header = "🔴 BURNIE — негативный сентимент"
    elif senti == "pos":
        header = "🟢 BURNIE — позитивный сентимент"
    else:
        header = "⚪ BURNIE — нейтральный сентимент"

    delta = snapshot.get("followers_delta", 0)
    delta_s = f"+{delta}" if delta > 0 else str(delta)
    neg_h = snapshot.get("neg_hits", 0)
    pos_h = snapshot.get("pos_hits", 0)
    toly = snapshot.get("toly_hits", 0)
    ai = snapshot.get("ai_buy_hits", 0)

    mc = snapshot.get("market_cap")
    price = snapshot.get("price_usd")
    chg = snapshot.get("change_24h")
    vol = snapshot.get("volume_24h")

    if mc is not None:
        mc_s = f"${float(mc)/1e6:.1f}M" if float(mc) >= 1e6 else f"${float(mc):,.0f}"
    else:
        mc_s = "N/A"
    price_s = f"${float(price):.6f}" if price is not None else "N/A"
    chg_s = f"{float(chg):+.1f}%" if chg is not None else "?"
    vol_s = f"${float(vol)/1e3:.0f}K" if vol is not None else "N/A"

    lines = [
        header,
        "",
        f"📊 Сентимент: {pos_h} позитивных / {neg_h} негативных постов",
    ]
    if toly:
        lines.append(f"👤 Toly (основатель Solana) упомянут в {toly} постах — это ключевой сигнал.")
    if ai:
        lines.append(f"🤖 AI-боты дают сигнал на покупку: {ai} постов.")
    spam = snapshot.get("vote_spam_hits", 0)
    if spam:
        lines.append(f"🗳️ Голосование за листинг: {spam} постов — фарм-кампания, не сигнал.")
    lines.append(f"👥 Фолловеры: {snapshot.get('followers', 0):,} ({delta_s} за период) | Капитализация: {mc_s}")
    lines.append(f"💵 Цена: {price_s} | За 24ч: {chg_s} | Объём: {vol_s}")

    # Market read + TA (real indicators from OHLCV)
    if chg is not None and mc is not None:
        if float(chg) < -10:
            lines.append("📉 Цена заметно падает — возможен слив, осторожно.")
        elif float(chg) > 10:
            lines.append("📈 Цена растёт — идёт разогрев.")
        else:
            lines.append("➡️ Цена в боковике — рынок ждёт, накопление.")
    ta = snapshot.get("chart_ta") or {}
    if ta.get("ok"):
        phase = ta.get("phase")
        phase_ru = {
            "accumulation": "накопление",
            "distribution": "раздача",
            "markup": "разгон",
            "decay": "затухание (дно после пампа)",
        }.get(phase, phase or "?")
        ta_bits = [f"фаза: {phase_ru}"]
        if phase == "decay":
            ta_bits.append("для PolitiFi это зона накопления до катализатора")
        if ta.get("rsi") is not None:
            ta_bits.append(f"RSI {ta['rsi']}")
        mc_ta = ta.get("macd_crossover")
        if mc_ta and mc_ta != "none":
            ta_bits.append(f"MACD: {mc_ta}")
        vd = ta.get("volume_divergence")
        if vd and vd != "none":
            ta_bits.append(f"дивергенция: {vd}")
        lines.append("📐 TA: " + " | ".join(ta_bits))

    neg = snapshot.get("strong_negative") or []
    bull = snapshot.get("strong_bullish") or []
    catalysts = snapshot.get("catalysts") or []
    if neg:
        first = neg[0]
        risk_ru = explain_terms(first.get("text", ""), RISK_TERMS_RU)
        lines.append("⚠️ Риск: " + risk_ru)
        trans = translate_post(first.get("text", ""))
        lines.append("   💬 " + trans)
        url = post_url(first.get("username", ""), first.get("id", ""))
        if url:
            lines.append("   🔗 " + url)
    elif senti == "pos":
        lines.append("✅ Серьёзных обвинений (скам/слив) не обнаружено.")
    if catalysts:
        # Драйвер = самый весомый катализатор (крупный аккаунт × BURNIE), не random post
        c = catalysts[0]
        trans = translate_post(c.get("text", ""))
        url = c.get("url") or post_url(c.get("user", ""), c.get("id", ""))
        driver_ru = explain_terms(c.get("text", ""), DRIVER_TERMS_RU)
        if c.get("type") == "rt_fresh":
            driver_ru = f"свежий ретвит поста офиц. аккаунта @{ACCOUNT} — крупный аккаунт взаимодействует"
        elif c.get("type") == "quote_fresh":
            driver_ru = f"свежая цитата поста офиц. аккаунта @{ACCOUNT} — крупный аккаунт комментирует"
        elif c.get("type") == "like_spike":
            driver_ru = "аномальный всплеск лайков на свежем посте — сообщество отреагировало"
        elif driver_ru == "нет ключевых слов":
            driver_ru = {
                "rt_official": "ретвит поста офиц. аккаунта",
                "reply_official": "ответ посту офиц. аккаунта",
                "quote_official": "цитата поста офиц. аккаунта",
                "mention_official": "упоминание офиц. аккаунта",
                "bare_burnie": "двусмысленное упоминание BURNIE (без тикера)",
            }.get(c.get("type"), "взаимодействие с BURNIE")
        lines.append("🔥 Драйвер: " + driver_ru)
        lines.append("   💬 " + trans)
        if url:
            lines.append("   🔗 " + url)
    elif bull:
        first = next(
            (b for b in bull if explain_terms(b["text"], DRIVER_TERMS_RU) != "нет ключевых слов"),
            bull[0],
        )
        trans = translate_post(first["text"])
        url = post_url(first.get("username", ""), first.get("id", ""))
        lines.append("🔥 Драйвер: " + explain_terms(first["text"], DRIVER_TERMS_RU))
        lines.append("   💬 " + trans)
        if url:
            lines.append("   🔗 " + url)

    # Катализатор / виральность (factor #1: large-account touch = лесной пожар)
    catalysts = snapshot.get("catalysts") or []
    type_ru_map = {
        "rt_official": "RT поста офиц.",
        "reply_official": "ответ офиц.",
        "quote_official": "цитата поста офиц.",
        "mention_official": "упоминание офиц.",
        "bare_burnie": "слово BURNIE без $/#",
        "ticker_mention": "$BURNIE",
        "rt_fresh": "RT свежего поста офиц.",
        "quote_fresh": "цитата свежего поста офиц.",
        "like_spike": "⚡ всплеск лайков",
    }
    # politician — высший приоритет
    tier_rank = {
        "politician": 0,
        "mega": 1,
        "known": 1,
        "large": 2,
        "kol": 3,
        "spike": 4,
        "micro": 5,
        "junk": 6,
    }
    if catalysts:
        shown = catalysts[1:5]  # catalysts[0] уже показан в 🔥 Драйвер — не дублируем
        # Группировка: politician → mega/known → large → KOL
        shown.sort(key=lambda c: tier_rank.get(c.get("tier") or "", 9))
        big_n = sum(
            1 for c in catalysts if c.get("tier") in ("politician", "mega", "known", "large")
        )
        pol_n = sum(1 for c in catalysts if c.get("tier") == "politician")
        head = (
            f"⚡ Катализатор: {len(catalysts)} сигнал(ов), "
            f"из них {big_n} от крупных/политиков"
        )
        if pol_n:
            head += f" (🏛 {pol_n} politician)"
        lines.append(head)
        for c in shown[:4]:
            fol = int(c.get("followers") or 0)
            tr = type_ru_map.get(c.get("type") or "", c.get("type") or "?")
            v_mark = "✓" if c.get("verified") else ""
            tier_s = c.get("tier") or ""
            pol_mark = " 🏛" if tier_s == "politician" else ""
            user_s = c.get("user") or "аккаунт-аноним (всплеск)"
            if c.get("type") == "like_spike":
                lines.append(f"   ⚡ {c.get('text','')[:100]}")
            else:
                lines.append(f"   @{user_s} ({fol:,} fol{v_mark}{pol_mark}) — {tr}")
            if c.get("url"):
                lines.append(f"   🔗 {c['url']}")
    else:
        kol = snapshot.get("kol_mentions") or []
        if kol:
            top = sorted(kol, key=lambda x: x.get("followers", 0), reverse=True)[:3]
            top_s = ", ".join(f"@{m['user']} ({m['followers']:,})" for m in top)
            lines.append(f"📣 Виральность: {len(kol)} упоминаний от крупных аккаунтов: {top_s}")
        else:
            lines.append(
                "📣 Катализатор: тишина — крупные аккаунты не трогали "
                f"@{ACCOUNT} / слово BURNIE."
            )

    # Атрибуция: дельты цены после прошлых катализаторов
    attr_line = format_attribution_line(snapshot.get("attribution"))
    if attr_line:
        lines.append(attr_line)

    # Календарь выборов
    cal = snapshot.get("calendar") or {}
    if cal.get("active"):
        days = cal.get("days_to")
        days_s = "сегодня" if days == 0 else (f"через {days}д" if days and days > 0 else f"{abs(days or 0)}д назад")
        lines.append(
            f"🗓 Календарь: {cal.get('event')} ({cal.get('date')}, {days_s}) "
            f"— бонус +{cal.get('bonus', 0)} к виральности"
        )

    # Wallet accumulation factor (factor #2: smart money accumulation)
    sm = snapshot.get("smart_money") or {}
    if sm.get("ok"):
        sm_b = int(sm.get("sm_buys", 0) or 0)
        sm_s = int(sm.get("sm_sells", 0) or 0)
        kol_b = int(sm.get("kol_buys", 0) or 0)
        kol_s = int(sm.get("kol_sells", 0) or 0)
        tot_b = sm_b + kol_b
        tot_s = sm_s + kol_s
        sig = sm.get("signal", "none")
        if sig == "accumulation":
            lines.append(f"🐋 Накопление: smart money покупает ({tot_b} покупок / {tot_s} продаж) — сигнал накопления.")
        elif sig == "distribution":
            lines.append(f"🐋 Распределение: smart money продаёт ({tot_b} покупок / {tot_s} продаж) — осторожно.")
        elif tot_b == 0 and tot_s == 0:
            lines.append("🐋 Накопление: smart money пока не зашёл — наблюдает.")
        else:
            lines.append(f"🐋 Накопление: смешанно ({tot_b} покупок / {tot_s} продаж).")

    # Market structure: buy/sell ratio + holders + security (weighted model)
    buy_r = snapshot.get("buy_ratio")
    if buy_r is not None:
        br = float(buy_r)
        if br >= 1.3:
            lines.append(f"🛒 Покупки/продажи: {br:.1f} — покупают больше, чем продают.")
        elif br < 0.7:
            lines.append(f"🛒 Покупки/продажи: {br:.1f} — продажи доминируют, осторожно.")
        else:
            lines.append(f"🛒 Покупки/продажи: {br:.1f} — примерно поровну.")
    hr = snapshot.get("holder_risk") or {}
    if hr.get("ok"):
        top = hr.get("top_holders") or []
        bundlers = [h for h in top if "bundler" in (h.get("tags") or [])]
        hcount = hr.get("holder_count")
        h_s = f" | Холдеры: {hcount:,}" if hcount else ""
        if bundlers:
            b_pct = sum(float(b.get("pct") or 0) for b in bundlers)
            lines.append(f"👥 Держатели: топ-10 = {len(top)} | bundler'ы: {len(bundlers)} ({b_pct:.1f}%){h_s}")
        else:
            lines.append(f"👥 Держатели: bundler'ов в топе нет — чисто{h_s}")
    rc = snapshot.get("rugcheck") or {}
    if rc.get("ok"):
        lvl_ru = {"low": "низкий", "medium": "средний", "high": "высокий"}.get(rc.get("level"), rc.get("level"))
        lines.append(f"🛡️ Риск скама (RugCheck): {lvl_ru}")

    # Warmup detector (pre-election catalyst)
    warmup = detect_warmup(snapshot)
    if warmup["warming"]:
        lines.append(f"🔥 Разогрев: начинается — {', '.join(warmup['signals'])}")

    # Weighted composite verdict — total of ALL parameters
    score = snapshot.get("weighted_score") or compute_weighted_score(snapshot)
    total = score.get("total", 0)
    comp = score.get("components", {})
    comp_ru = {
        "sentiment": "сентимент",
        "ta": "TA",
        "virality": "виральность",
        "smart_money": "smart money",
        "market": "рынок",
        "holders": "держатели",
        "security": "безопасность",
    }
    comp_s = " | ".join(f"{comp_ru[k]}:{v}" for k, v in comp.items() if v)
    lines.append("")
    if senti == "neg" and total < 30:
        lines.append(f"📌 Вердикт: НЕ СЛЕДИТЬ ({total}/100) — негатив растёт, риск слива.")
    else:
        lines.append(f"📌 Вердикт: {score.get('verdict')} ({total}/100)")
        lines.append(f"⚖️ Веса: {comp_s}")
    return "\n".join(lines)


def format_degraded(snapshot: dict[str, Any]) -> str:
    """Отчёт при сбое X API: не молчим, показываем, что трекер жив, но данных X нет.

    Event-first остаётся: без hard_alert полный отчёт не шлём, но при ошибке
    X-вызовов печатаем короткий деградированный отчёт с доступными DEX-метриками.
    """
    errors = snapshot.get("x_api_errors") or []
    lines = [
        "⚠️ BURNIE — трекер жив, но X API недоступен",
        "",
        "Не удалось получить данные X (сентимент/фолловеры/катализаторы):",
    ]
    for e in errors[:3]:
        lines.append(f"  • {e}")
    if len(errors) > 3:
        lines.append(f"  • …и ещё {len(errors) - 3} ошибок")
    lines.append("")
    mc = snapshot.get("market_cap")
    price = snapshot.get("price_usd")
    chg = snapshot.get("change_24h")
    vol = snapshot.get("volume_24h")
    if mc is not None:
        mc_s = f"${float(mc)/1e6:.1f}M" if float(mc) >= 1e6 else f"${float(mc):,.0f}"
    else:
        mc_s = "N/A"
    price_s = f"${float(price):.6f}" if price is not None else "N/A"
    chg_s = f"{float(chg):+.1f}%" if chg is not None else "?"
    vol_s = f"${float(vol)/1e3:.0f}K" if vol is not None else "N/A"
    lines.append(f"💵 Рынок (DexScreener, без X): MC {mc_s} | Цена {price_s} | 24ч {chg_s} | Объём {vol_s}")
    lines.append("")
    lines.append("📌 Вердикт: данных X нет — сентимент/катализаторы неизвестны. Следующий прогон 18:00.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print snapshot without writing JSONL")
    args = parser.parse_args()

    snapshot, strong_negative = build_snapshot()
    dex = fetch_dex_metrics()
    if dex.get("ok"):
        snapshot["market_cap"] = dex.get("market_cap")
        snapshot["price_usd"] = dex.get("price_usd")
        snapshot["volume_24h"] = dex.get("volume_24h")
        snapshot["liquidity_usd"] = dex.get("liquidity_usd")
        snapshot["change_24h"] = dex.get("change_24h")
        snapshot["buys_24h"] = dex.get("buys_24h")
        snapshot["sells_24h"] = dex.get("sells_24h")
        snapshot["buy_ratio"] = dex.get("buy_ratio")
    # prev volume from history for warmup comparison
    prev_vol = None
    if OUTFILE.exists():
        try:
            lines = OUTFILE.read_text().strip().splitlines()
            if lines:
                prev_vol = json.loads(lines[-1]).get("volume_24h")
        except (json.JSONDecodeError, OSError):
            pass
    snapshot["prev_volume_24h"] = prev_vol
    ta = fetch_chart_ta()
    if ta.get("ok"):
        snapshot["chart_ta"] = ta
    # Катализаторы уже в snapshot из build_snapshot (3-й X-вызов).
    # Fallback radar_x — только если catalyst scan пуст/упал (не дублируем X-бюджет в норме).
    if not snapshot.get("catalysts") and not snapshot.get("kol_mentions"):
        kol = fetch_kol_mentions()
        if kol.get("ok"):
            snapshot["kol_mentions"] = kol.get("mentions", [])
            snapshot["kol_engagement"] = kol.get("engagement", {})

    # Календарь политических событий (±3д → бонус к virality)
    cal = calendar_boost()
    snapshot["calendar"] = cal

    # Attribution loop: T0 для новых + дозаполнение h1/h6/h24 старых
    hist_attr = load_attribution_events()
    snapshot["attribution"] = build_attribution(
        catalysts=snapshot.get("catalysts") or [],
        price=snapshot.get("price_usd"),
        mc=snapshot.get("market_cap"),
        vol=snapshot.get("volume_24h"),
        history=hist_attr,
    )

    sm = fetch_smart_money_flow()
    if sm.get("ok"):
        snapshot["smart_money"] = sm
    hr = fetch_holder_risk()
    if hr.get("ok"):
        snapshot["holder_risk"] = hr
    rc = fetch_rugcheck()
    if rc.get("ok"):
        snapshot["rugcheck"] = rc

    # Event-first hard_alert: только RT/quote/reply офиц. от large+/known/politician,
    # и только при ПЕРВОМ появлении catalyst id (first-seen cooldown).
    snapshot["hard_alert"] = compute_hard_alert(
        snapshot.get("catalysts") or [],
        seen_ids=_seen_catalyst_ids(),
    )

    score = compute_weighted_score(snapshot)
    snapshot["weighted_score"] = score
    if args.dry_run:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0

    append_jsonl(OUTFILE, snapshot)
    # Отчёт приходит ВСЕГДА в штатных прогонах (06:00/18:00), даже без hard_alert.
    # send_telegram() не вызываем из main — крон доставляет stdout сам.
    if snapshot.get("x_api_errors"):
        # X API упал/rate-limit — не молчим и не врём: деградированный отчёт.
        print(format_degraded(snapshot))
    else:
        print(format_alert(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
