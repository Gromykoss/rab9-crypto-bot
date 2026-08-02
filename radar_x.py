"""X/Twitter radar with influencer tracking.

Real X API v2 via OAuth 1.0a + influencer knowledge base.

Usage: python3 radar_x.py "token_name"
"""
import json
import sys
import os
from requests_oauthlib import OAuth1
import requests

TIMEOUT = 10
MAX_RESULTS = 10

TRACKED_INFLUENCERS = [
    "aeyakovenko", "elonmusk", "Ansem", "blknoiz06", "0xMert_", "rajgokal",
]


def _load_oauth():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "x_oauth.json")
    if os.path.exists(path):
        with open(path) as f:
            creds = json.load(f)
        return OAuth1(creds["consumer_key"], creds["consumer_secret"],
                      creds["access_token"], creds["token_secret"])
    return None


def _load_kb():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "influencer_kb.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def search_x(query: str) -> dict:
    """Search X API v2 + check influencer knowledge base."""
    auth = _load_oauth()
    kb = _load_kb()

    # Check knowledge base for known influencer backing
    kb_influencers = []
    query_upper = query.upper()
    for token_name, data in kb.items():
        if token_name.upper() in query_upper:
            for inf in data.get("influencers", []):
                kb_influencers.append(
                    f"⚠️ KB-HISTORICAL (unverified): @{inf['handle']} ({inf['role']}) — {inf['evidence']} [CHECK: did they actually post?]"
                )

    if not auth:
        # Return KB data only
        return {
            "ok": True, "query": query,
            "posts": [], "influencers": kb_influencers,
            "engagement": {}, "count": 0,
        }

    clean_query = f"{query} -is:retweet"[:500]
    posts = []
    live_influencers = []
    total_likes = 0
    total_rt = 0
    spam_count = 0
    kabal_warnings = []

    SPAM_PATTERNS = [
        "voted YES for", "get listed on FOMO", "almost on moonshot",
        "only N more votes", "is about to get listed on moonshot",
        "is so close for moonshot", "just voted YES",
    ]

    try:
        # user.fields: public_metrics (followers) + verified — вес аккаунта для KOL/catalyst
        # tweet.fields: referenced_tweets — RT/quote/reply к офиц. аккаунту
        r = requests.get(
            "https://api.x.com/2/tweets/search/recent",
            params={
                "query": clean_query, "max_results": MAX_RESULTS,
                "tweet.fields": "created_at,author_id,public_metrics,referenced_tweets,in_reply_to_user_id",
                "expansions": "author_id,referenced_tweets.id",
                "user.fields": "username,public_metrics,verified,verified_type",
            },
            auth=auth, timeout=TIMEOUT,
        )

        if r.ok:
            data = r.json()
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
            for t in data.get("data", []):
                author_id = t.get("author_id", "")
                user = users.get(author_id, {})
                username = user.get("username", "?")
                followers = user.get("public_metrics", {}).get("followers_count", 0)
                text = t.get("text", "")[:200]
                text_lower = text.lower()
                if any(p.lower() in text_lower for p in SPAM_PATTERNS) or ("moonshot" in text_lower and ("vote" in text_lower or "voted" in text_lower)):
                    spam_count += 1
                    continue  # skip spam vote-begging
                metrics = t.get("public_metrics", {})
                likes = metrics.get("like_count", 0)
                rt = metrics.get("retweet_count", 0)
                total_likes += likes
                total_rt += rt
                post_str = f"@{username} ({followers:,}): {text}"
                if likes or rt:
                    post_str += f" [{likes}♥ {rt}↻]"
                posts.append(post_str)
                if username.lower() in [h.lower() for h in TRACKED_INFLUENCERS]:
                    live_influencers.append(
                        f"⭐ LIVE: @{username} ({followers:,} followers): {text[:120]}"
                    )
    except Exception:
        pass

    # Merge KB + live influencers
    all_influencers = kb_influencers + live_influencers

    # Build manipulation warnings
    if spam_count >= 5:
        kabal_warnings.append(f"⚠️ LISTING CAMPAIGN: {spam_count} vote-spam posts detected — standard memecoin Moonshot/FOMO listing campaign. This is NORMAL for meme coins, NOT proof of fake community. Check token's OWN X account for real engagement.")
    if kb_influencers and not live_influencers:
        kabal_warnings.append("⚠️ MANIPULATION: Influencer backing is KB-HISTORICAL only — NO live posts found. Community may be manufacturing narrative.")

    return {
        "ok": True, "query": clean_query,
        "posts": posts[:MAX_RESULTS],
        "influencers": all_influencers[:5],
        "engagement": {"likes": total_likes, "retweets": total_rt},
        "count": len(posts),
        "spam_detected": spam_count,
        "kabal_warnings": kabal_warnings,
    }


def lookup_account(username: str) -> dict | None:
    """Look up X account metrics by username."""
    auth = _load_oauth()
    if not auth:
        return None
    try:
        r = requests.get(
            f"https://api.x.com/2/users/by/username/{username.lstrip('@')}",
            params={"user.fields": "public_metrics,description"},
            auth=auth, timeout=10,
        )
        if r.ok:
            d = r.json()["data"]
            return {
                "username": d["username"],
                "name": d.get("name", ""),
                "followers": d.get("public_metrics", {}).get("followers_count", 0),
                "tweets": d.get("public_metrics", {}).get("tweet_count", 0),
                "desc": (d.get("description") or "")[:100],
            }
    except Exception:
        pass
    return None


def format_for_terminal(result: dict) -> str:
    if not result.get("ok"):
        return "X: нет данных."

    lines = ["X Radar:"]
    eng = result.get("engagement", {})
    count = result.get("count", 0)
    if eng or count:
        lines.append(f"  {count} tweets, {eng.get('likes',0)}♥ {eng.get('retweets',0)}↻")

    infs = result.get("influencers", [])
    if infs:
        lines.append(f"  ⭐ Influencers ({len(infs)}):")
        for inf in infs[:4]:
            lines.append(f"    {inf}")

    posts = result.get("posts", [])
    if posts:
        for p in posts[:2]:
            lines.append(f"  {p[:180]}")

    return "\n".join(lines)


def format_for_grok(result: dict) -> str:
    """Format X radar results for Grok prompt injection."""
    if not result.get("ok"):
        return "X: нет данных."

    lines = []
    eng = result.get("engagement", {})
    count = result.get("count", 0)
    spam = result.get("spam_detected", 0)
    if eng or count:
        lines.append(f"X: {count} упоминаний, {eng.get('likes',0)}♥ {eng.get('retweets',0)}↻, vote-spam filtered: {spam}")

    # Kabal warnings FIRST (before influencer list)
    warnings = result.get("kabal_warnings", [])
    for w in warnings:
        lines.append(w)

    infs = result.get("influencers", [])
    if infs:
        lines.append(f"Influencer backing: {len(infs)}")
        for inf in infs[:4]:
            lines.append(f"  {inf}")

    posts = result.get("posts", [])
    if posts:
        lines.append(f"Обсуждение:")
        for p in posts[:3]:
            lines.append(f"  {p[:200]}")

    return "\n".join(lines) if lines else "X: нет значимых упоминаний."


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: radar_x.py <query>"}))
        sys.exit(1)
    query = " ".join(sys.argv[1:])
    result = search_x(query)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
