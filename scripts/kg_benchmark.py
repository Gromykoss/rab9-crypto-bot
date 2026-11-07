#!/usr/bin/env python3
"""Benchmark harness: Knowledge Graph (grounded_answer) vs CHRONOLOGY grep baseline.

Usage:
  python3 scripts/kg_benchmark.py --questions questions.txt \\
      [--graph knowledge_graph/graph.json] [--chronology CHRONOLOGY.md] \\
      [--out results.md]

stdlib only. Does not modify the graph or chronology.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent

# Lightweight stop-words for keyword extraction (RU + EN).
_STOP = frozenset(
    """
    a an the and or of to in on for with from by as is are was were be been
    what which who when where why how do does did can could should would
    this that these those it its their our your my me we you they he she
    not no yes if then than so such into about over under after before
    что кто как где когда почему зачем какой какая какое какие чем кому
    это тот та те для при без над под после перед или либо же ли бы
    есть был была были будет будут быть может можно нужно надо
    а и о об от до из у на во со по не ни да нет
    """.split()
)

_NUM_PREFIX = re.compile(r"^\s*(?:\d+[.)]\s*|#\d+\s*|Q\d+[:.)]\s*)", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-zА-Яа-яЁё0-9_/.-]{2,}")


def _repo_path(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def parse_questions(path: Path) -> List[str]:
    questions: List[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Strip numbering first so "#1 question" is kept; plain "# comment" is skipped.
        line = _NUM_PREFIX.sub("", line).strip()
        if not line or line.startswith("#"):
            continue
        questions.append(line)
    return questions


def extract_keywords(question: str) -> List[str]:
    words = _WORD.findall(question.lower())

    def _useful(w: str) -> bool:
        if w in _STOP or w.isdigit():
            return False
        # Drop numbering leftovers like "1." / "2)" / "#3".
        if not any(ch.isalpha() for ch in w):
            return False
        return True

    kws = [w for w in words if _useful(w)]
    # Prefer longer / more specific tokens first for scoring ties.
    kws.sort(key=lambda w: (-len(w), w))
    # Deduplicate preserving order.
    seen = set()
    out: List[str] = []
    for w in kws:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out or [w for w in words if any(ch.isalpha() for ch in w)][:5]


def chronology_grep(question: str, chronology_text: str, top_k: int = 5) -> str:
    """Keyword search over CHRONOLOGY.md; return top-k matching lines with light context."""
    keywords = extract_keywords(question)
    if not keywords:
        return "(no keywords)"

    lines = chronology_text.splitlines()
    scored: List[Tuple[int, int, str]] = []  # (score, line_no, snippet)

    for i, line in enumerate(lines):
        low = line.lower()
        score = sum(1 for kw in keywords if kw in low)
        if score <= 0:
            continue
        # Context: prev non-empty + match + next non-empty (compact).
        prev = ""
        for j in range(i - 1, max(-1, i - 4), -1):
            if lines[j].strip():
                prev = lines[j].strip()
                break
        nxt = ""
        for j in range(i + 1, min(len(lines), i + 4)):
            if lines[j].strip():
                nxt = lines[j].strip()
                break
        parts = [p for p in (prev, line.strip(), nxt) if p]
        snippet = " | ".join(parts)
        scored.append((score, i, snippet))

    if not scored:
        return "(no matches)"

    scored.sort(key=lambda t: (-t[0], t[1]))
    top = scored[:top_k]
    # Compact: one finding per numbered slot, joined for ≤2 display lines later.
    return "; ".join(f"#{n+1}({s}): {snip}" for n, (s, _, snip) in enumerate(top))


def _load_grounded_answer(graph_path: Path):
    """Import grounded_answer from knowledge_graph/query_tool.py next to the graph."""
    kg_dir = graph_path.parent
    query_tool_path = kg_dir / "query_tool.py"
    if not query_tool_path.is_file():
        # Fallback: conventional repo path.
        query_tool_path = REPO_ROOT / "knowledge_graph" / "query_tool.py"
    if not query_tool_path.is_file():
        raise FileNotFoundError(
            f"query_tool.py not found near {graph_path} "
            f"(expected {kg_dir / 'query_tool.py'})"
        )

    # Ensure package-less import works and GRAPH_FILE points at --graph.
    sys.path.insert(0, str(query_tool_path.parent.parent))
    sys.path.insert(0, str(query_tool_path.parent))

    spec = importlib.util.spec_from_file_location(
        "kg_query_tool_benchmark", query_tool_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {query_tool_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    if not hasattr(mod, "grounded_answer"):
        raise AttributeError(f"{query_tool_path} has no grounded_answer")

    # Honour --graph even if module hardcodes its own GRAPH_FILE.
    if hasattr(mod, "GRAPH_FILE"):
        mod.GRAPH_FILE = graph_path

    return mod.grounded_answer


def kg_answer(question: str, grounded_fn) -> str:
    try:
        result = grounded_fn(question)
    except Exception as exc:  # noqa: BLE001 — benchmark must not crash the table
        return f"(KG error: {exc})"
    if result is None:
        return "(empty)"
    return str(result)


def _cell(text: str, max_lines: int = 2, max_chars: int = 240) -> str:
    """Collapse answer/findings into a markdown-table-safe ≤max_lines cell."""
    flat = " ".join(str(text).split())
    if len(flat) > max_chars:
        flat = flat[: max_chars - 1] + "…"
    # Soft wrap into at most max_lines via <br> for readability in MD viewers.
    if max_lines <= 1 or len(flat) <= max_chars // 2:
        body = flat
    else:
        mid = len(flat) // 2
        split_at = flat.rfind(" ", 0, mid + 40)
        if split_at < mid // 2:
            split_at = mid
        body = flat[:split_at].rstrip() + "<br>" + flat[split_at:].lstrip()
    return body.replace("|", "\\|")


def run_benchmark(
    questions: List[str],
    grounded_fn,
    chronology_text: str,
) -> Tuple[List[dict], float, float]:
    rows: List[dict] = []
    sum_kg = 0.0
    sum_grep = 0.0

    for q in questions:
        t0 = time.perf_counter()
        ans_kg = kg_answer(q, grounded_fn)
        t_kg = time.perf_counter() - t0

        t1 = time.perf_counter()
        ans_grep = chronology_grep(q, chronology_text)
        t_grep = time.perf_counter() - t1

        sum_kg += t_kg
        sum_grep += t_grep
        rows.append(
            {
                "question": q,
                "kg": ans_kg,
                "t_kg": t_kg,
                "grep": ans_grep,
                "t_grep": t_grep,
            }
        )
    return rows, sum_kg, sum_grep


def render_markdown(
    rows: List[dict], sum_kg: float, sum_grep: float
) -> str:
    n = len(rows) or 1
    lines = [
        "# KG vs grep — benchmark",
        "",
        "| вопрос | ответ KG (≤2 строки) | t_KG | находки grep (≤2 строки) | t_grep |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    for r in rows:
        q = _cell(r["question"], max_lines=1, max_chars=120)
        kg = _cell(r["kg"], max_lines=2)
        grep = _cell(r["grep"], max_lines=2)
        lines.append(
            f"| {q} | {kg} | {r['t_kg']:.4f}s | {grep} | {r['t_grep']:.4f}s |"
        )

    lines.extend(
        [
            "",
            "## Итог",
            "",
            f"- вопросов: **{len(rows)}**",
            f"- суммарное t_KG: **{sum_kg:.4f}s** · среднее: **{sum_kg / n:.4f}s**",
            f"- суммарное t_grep: **{sum_grep:.4f}s** · среднее: **{sum_grep / n:.4f}s**",
            "",
        ]
    )
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Benchmark Knowledge Graph grounded_answer vs CHRONOLOGY grep."
    )
    p.add_argument(
        "--questions",
        required=True,
        help="File with numbered questions, one per line",
    )
    p.add_argument(
        "--graph",
        default="knowledge_graph/graph.json",
        help="Path to graph.json (default: knowledge_graph/graph.json)",
    )
    p.add_argument(
        "--chronology",
        default="CHRONOLOGY.md",
        help="Path to CHRONOLOGY.md (default: CHRONOLOGY.md)",
    )
    p.add_argument(
        "--out",
        default="results.md",
        help="Output markdown report (default: results.md)",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    graph_path = _repo_path(args.graph)
    if not graph_path.is_file():
        print("graph not built", file=sys.stderr)
        return 1

    questions_path = _repo_path(args.questions)
    chronology_path = _repo_path(args.chronology)
    out_path = _repo_path(args.out)

    if not questions_path.is_file():
        print(f"questions file not found: {questions_path}", file=sys.stderr)
        return 1
    if not chronology_path.is_file():
        print(f"chronology not found: {chronology_path}", file=sys.stderr)
        return 1

    questions = parse_questions(questions_path)
    if not questions:
        print("no questions parsed", file=sys.stderr)
        return 1

    try:
        grounded_fn = _load_grounded_answer(graph_path)
    except Exception as exc:  # noqa: BLE001
        print(f"failed to load grounded_answer: {exc}", file=sys.stderr)
        return 1

    chronology_text = chronology_path.read_text(encoding="utf-8", errors="replace")
    rows, sum_kg, sum_grep = run_benchmark(questions, grounded_fn, chronology_text)
    report = render_markdown(rows, sum_kg, sum_grep)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
