#!/usr/bin/env python3
"""Self-improving trading theory: Grok reviews past analyses, suggests improvements."""

import json
import os
import shutil
import sys
from collections import deque


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from token_intel import ask_grok  # noqa: E402


ANALYSES_PATH = os.path.join(REPO_ROOT, "data", "grok_analyses.jsonl")
THEORY_PATH = os.path.join(REPO_ROOT, "trading_theory.md")
BACKUP_PATH = os.path.join(REPO_ROOT, "trading_theory.md.bak")


def read_last_analyses(limit: int = 20) -> list[dict]:
    entries = deque(maxlen=limit)

    try:
        with open(ANALYSES_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []

    return list(entries)


def build_prompt(analyses: list[dict]) -> str:
    analyses_json = json.dumps(analyses, ensure_ascii=False, indent=2)

    return (
        "You are reviewing your past meme coin analyses to improve trading theory rules. "
        "Here are the last 20 analyses:\n"
        f"{analyses_json}\n\n"
        "Identify patterns: which rules proved correct, which missed signals, "
        "what new rules should be added. Output ONLY the updated trading_theory.md "
        "content in markdown format."
    )


def write_updated_theory(updated_theory: str) -> bool:
    try:
        if os.path.exists(THEORY_PATH):
            shutil.copyfile(THEORY_PATH, BACKUP_PATH)

        with open(THEORY_PATH, "w", encoding="utf-8") as f:
            f.write(updated_theory.rstrip() + "\n")

        return True
    except Exception as error:
        print(f"Failed to write trading_theory.md: {error}", file=sys.stderr)
        return False


def main() -> int:
    analyses = read_last_analyses(20)
    if not analyses:
        print("No Grok analyses found.", file=sys.stderr)
        return 1

    prompt = build_prompt(analyses)
    updated_theory = ask_grok(prompt).strip()

    if not updated_theory:
        print("Grok returned empty trading theory.", file=sys.stderr)
        return 1

    if not write_updated_theory(updated_theory):
        return 1

    print(updated_theory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
