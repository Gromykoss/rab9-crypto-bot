"""GitHub radar lookup for RAB9 token analysis.

Usage: python3 radar_gh.py "token_name"
Returns: JSON with relevant repos (dev activity signals).
"""
import json
import subprocess
import sys
import os

TIMEOUT = 12  # seconds
MAX_RESULTS = 4

GITHUB_API = "https://api.github.com"


def search_github(query: str) -> dict:
    """Search GitHub for token-related repos. Returns structured results."""
    safe_query = " ".join(query.split())[:80]

    try:
        import urllib.parse
        encoded_query = urllib.parse.quote(f"{safe_query} language:solana")
        url = f"{GITHUB_API}/search/repositories?q={encoded_query}&sort=updated&order=desc&per_page={MAX_RESULTS}"

        result = subprocess.run(
            [
                "curl", "-s", "-m", str(TIMEOUT),
                "-H", "Accept: application/vnd.github+json",
                "-H", "X-GitHub-Api-Version: 2022-11-28",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT + 2,
        )

        if result.returncode != 0:
            return {"ok": False, "error": f"curl exit {result.returncode}", "repos": []}

        data = json.loads(result.stdout) if result.stdout.strip() else {}
        items = data.get("items", [])

        if not items:
            return {"ok": True, "query": safe_query, "repos": [], "count": 0}

        repos = []
        for r in items[:MAX_RESULTS]:
            repos.append({
                "name": r.get("full_name", "?"),
                "desc": (r.get("description") or "")[:150],
                "stars": r.get("stargazers_count", 0),
                "updated": (r.get("updated_at") or "")[:10],
                "language": r.get("language", "?"),
                "topics": r.get("topics", [])[:5],
            })

        return {"ok": True, "query": safe_query, "repos": repos, "count": len(repos)}

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "repos": []}
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid GitHub response", "repos": []}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "repos": []}


def format_for_grok(result: dict) -> str:
    """Format radar results for Grok prompt injection."""
    if not result.get("ok") or not result.get("repos"):
        return "GitHub: нет релевантных репозиториев."

    lines = [f"GitHub Radar ({result['count']} репо):"]
    for i, r in enumerate(result["repos"], 1):
        stars = f"★{r['stars']}" if r['stars'] else ""
        lines.append(f"  {i}. {r['name']} {stars} — {r['desc']}")
        if r["topics"]:
            lines.append(f"     topics: {', '.join(r['topics'])}")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: radar_gh.py <query>"}))
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    result = search_github(query)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
