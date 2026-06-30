#!/usr/bin/env python3
"""BURNIE community sentiment tracker.

Runs read-only X checks through the configured xurl CLI, appends one JSONL
snapshot, and prints an alert only for strong negative community signals.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUTFILE = ROOT / "community_sentiment.jsonl"
ACCOUNT = "BurnieSendersX"
COMMUNITY_QUERY = "BURNIE solana token sentiment"
NEGATIVE_QUERY = (
    'BURNIE (rug OR scam OR dump OR dumped OR warning OR abandoned OR dead '
    'OR "exit liquidity") -is:retweet'
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
POSITIVE_TERMS = (
    "bullish",
    "send",
    "sending",
    "moon",
    "100x",
    "based",
    "solid",
    "accumulation",
)


def run_xurl(args: list[str], timeout: int = 45) -> tuple[int, dict[str, Any] | None, str]:
    proc = subprocess.run(
        ["xurl", *args],
        cwd=str(ROOT),
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


def items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


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
    errors: list[str] = []

    user_code, user_payload, user_raw = run_xurl(["user", ACCOUNT])
    search_code, search_payload, search_raw = run_xurl(["search", COMMUNITY_QUERY, "-n", "10"])
    posts_code, posts_payload, posts_raw = run_xurl(["search", f"from:{ACCOUNT}", "-n", "10"])
    neg_code, neg_payload, neg_raw = run_xurl(["search", NEGATIVE_QUERY, "-n", "10"])

    for label, code, payload, raw in (
        (f"@{ACCOUNT} API", user_code, user_payload, user_raw),
        (f'X search "{COMMUNITY_QUERY}"', search_code, search_payload, search_raw),
        ("negative scan", neg_code, neg_payload, neg_raw),
        (f"@{ACCOUNT} recent posts", posts_code, posts_payload, posts_raw),
    ):
        err = first_error(label, code, payload, raw)
        if err:
            errors.append(err)

    user_data = user_payload.get("data") if isinstance(user_payload, dict) else {}
    user_metrics = user_data.get("public_metrics") if isinstance(user_data, dict) else {}
    followers = int(user_metrics.get("followers_count") or 0)
    tweet_count = int(user_metrics.get("tweet_count") or 0)

    community_posts = items(search_payload)
    recent_posts = items(posts_payload)
    negative_posts = items(neg_payload)
    community_texts = [str(post.get("text") or "") for post in community_posts]
    negative_texts = [str(post.get("text") or "") for post in negative_posts]
    all_scan_texts = community_texts + negative_texts

    neg_hits = term_count(all_scan_texts, NEGATIVE_TERMS) + term_count(
        all_scan_texts, SCAM_PATTERNS
    )
    pos_hits = term_count(community_texts, POSITIVE_TERMS)
    strong_negative = [
        compact_text(text, 100)
        for text in all_scan_texts
        if any(term in text.lower() for term in NEGATIVE_TERMS + SCAM_PATTERNS)
    ][:3]

    if strong_negative or neg_hits >= 2:
        sentiment = "neg"
    elif pos_hits > neg_hits and community_posts:
        sentiment = "pos"
    else:
        sentiment = "neutral"

    recent_totals = totals(recent_posts)
    latest = [
        f"{compact_text(str(post.get('text') or ''), 70)} "
        f"({(post.get('public_metrics') or {}).get('like_count', 0)}h/"
        f"{(post.get('public_metrics') or {}).get('retweet_count', 0)}rt/"
        f"{(post.get('public_metrics') or {}).get('reply_count', 0)}r)"
        for post in recent_posts[:3]
    ]

    notes = [
        f'X search "{COMMUNITY_QUERY}": {len(community_posts)} posts',
        f"negative scan: {len(negative_posts)} hits, strong_hits={len(strong_negative)}",
        f"sentiment_terms neg={neg_hits} pos={pos_hits}",
    ]
    if followers:
        notes.append(f"@{ACCOUNT}: {followers} followers, {tweet_count} tweets")
    if recent_posts:
        notes.append(
            f"recent {len(recent_posts)} posts: {recent_totals['likes']} likes, "
            f"{recent_totals['rt']} RT, {recent_totals['replies']} replies, "
            f"{recent_totals['views']} views"
        )
        notes.append("latest: " + " | ".join(latest))
    if strong_negative:
        notes.append("strong_negative: " + " | ".join(strong_negative))
    elif not errors:
        notes.append("no rug-pull accusations or dump warnings detected")
    if errors:
        notes.extend(errors)

    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "followers": followers,
        "sentiment": sentiment,
        "notes": "; ".join(notes),
    }
    return snapshot, strong_negative


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print snapshot without writing JSONL")
    args = parser.parse_args()

    snapshot, strong_negative = build_snapshot()
    if args.dry_run:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0

    append_jsonl(OUTFILE, snapshot)
    if snapshot["sentiment"] == "neg":
        print(
            "ALERT: BURNIE negative community signal\n"
            f"followers={snapshot['followers']} sentiment={snapshot['sentiment']}\n"
            f"notes={snapshot['notes']}"
        )
    else:
        print("[SILENT]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
