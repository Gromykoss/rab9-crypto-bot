#!/usr/bin/env python3
"""Knowledge Graph for RAB9 — Anthropic Graph Engineering Playbook.
Extract → Resolve → Assemble → Query → Grounded Answer → Maintain.
No external NLP, no graph DB. Just prompts + schema + NetworkX.
"""
import os, re, json, sys
from datetime import datetime, timezone
from pathlib import Path
import networkx as nx

RAB9 = os.path.expanduser("~/rab9")
GRAPH_DIR = os.path.join(RAB9, "knowledge_graph")
GRAPH_FILE = os.path.join(GRAPH_DIR, "graph.json")
os.makedirs(GRAPH_DIR, exist_ok=True)

# ─── Stage 1: EXTRACT ───────────────────────────────────────
CHRONOLOGY_HEADING_RE = re.compile(
    r"^##\s+(?P<date>"
    r"\d{2}\.\d{2}\.\d{4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|\d{2}\.\d{2}[–-]\d{2}\.\d{2}\.\d{4}"
    r")(?:\s+(?P<rest>.*))?$"
)


def _parse_chronology_heading(line: str):
    """Вернуть (date_key, event_date, title) для всех форматов хроники RAB9."""
    match = CHRONOLOGY_HEADING_RE.match(line)
    if not match:
        return None

    raw_date = match.group("date")
    rest = (match.group("rest") or "").strip()
    title = re.sub(r"^[-—]\s*", "", rest).strip() or "(без заголовка)"

    try:
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", raw_date):
            event_date = datetime.strptime(raw_date, "%d.%m.%Y").replace(tzinfo=timezone.utc)
            date_key = event_date.strftime("%Y-%m-%d")
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
            event_date = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            date_key = raw_date
        else:
            start_day, start_month, end_day, end_month, year = map(
                int, re.fullmatch(r"(\d{2})\.(\d{2})[–-](\d{2})\.(\d{2})\.(\d{4})", raw_date).groups()
            )
            start = datetime(year, start_month, start_day, tzinfo=timezone.utc)
            event_date = datetime(year, end_month, end_day, tzinfo=timezone.utc)
            date_key = f"{start:%Y-%m-%d}..{event_date:%Y-%m-%d}"
    except (TypeError, ValueError):
        return None

    return date_key, event_date, title


def extract_entities_from_file(filepath: str, days: int = None) -> list[dict]:
    """Extract entities and S-P-O triples from a markdown file.
    If days is set, only extract events from the last N days."""
    triples = []
    with open(filepath) as f:
        content = f.read()
    
    cutoff = None
    if days:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    # RAB9: основной формат ## DD.MM.YYYY — title; legacy ISO/ranges тоже читаем.
    # splitlines() намеренно проходит весь файл, а не только недавний хвост.
    for line in content.splitlines():
        parsed = _parse_chronology_heading(line)
        if not parsed:
            continue
        date_str, event_date, title = parsed
        
        # Skip old events if filtering
        if cutoff and event_date < cutoff:
            continue
        
        entity_id = f"event/{date_str}/{title[:40].strip()}"
        triples.append({
            "subject": entity_id,
            "predicate": "occurred_on",
            "object": date_str,
            "source": filepath,
            "confidence": 0.95
        })
        triples.append({
            "subject": entity_id,
            "predicate": "described_as",
            "object": title.strip(),
            "source": filepath,
            "confidence": 0.90
        })
    
    # Extract people/handles
    for handle in re.finditer(r'@(\w+)', content):
        triples.append({
            "subject": f"person/@{handle.group(1)}",
            "predicate": "mentioned_in",
            "object": os.path.basename(filepath),
            "source": filepath,
            "confidence": 0.85
        })
    
    # Extract project references
    for proj in re.finditer(r'\b(GULAG|gooolag|Alikhan|RAB9|rab9)\b', content, re.I):
        triples.append({
            "subject": f"project/{proj.group(1).lower()}",
            "predicate": "referenced_in",
            "object": os.path.basename(filepath),
            "source": filepath,
            "confidence": 0.85
        })
    
    # Extract task references (T-XXX)
    for task in re.finditer(r'(T-\d+)', content):
        triples.append({
            "subject": f"task/{task.group(1)}",
            "predicate": "mentioned_in",
            "object": os.path.basename(filepath),
            "source": filepath,
            "confidence": 0.90
        })
    
    return triples

# ─── Stage 2: RESOLVE ────────────────────────────────────────
def resolve_entities(triples: list[dict]) -> list[dict]:
    """Cluster equivalent entities. Pilot: simple normalization."""
    aliases = {
        "project/gooolag": "project/gulag",
        "project/rab9": "project/rab9",
        "project/alikhan": "project/alikhan",
    }
    
    resolved = []
    for t in triples:
        t = dict(t)
        t["subject"] = aliases.get(t["subject"], t["subject"])
        t["object"] = aliases.get(t["object"], t["object"])
        resolved.append(t)
    return resolved

# ─── Stage 3: ASSEMBLE ───────────────────────────────────────
VALID_TYPES = {"event", "person", "project", "task"}

def assemble_graph(triples: list[dict]) -> nx.DiGraph:
    """Build directed graph with all extracted triples (entities + literals).
    No co-occurrence inference — only direct extracted edges."""
    G = nx.DiGraph()

    for t in triples:
        s, p, o = t["subject"], t["predicate"], t["object"]
        src = t["source"]

        if not G.has_node(s):
            G.add_node(s)
        if not G.has_node(o):
            G.add_node(o)
        G.add_edge(s, o, predicate=p, source=src, confidence=t["confidence"])

    return G

# ─── Stage 4: QUERY ──────────────────────────────────────────
def query_graph(G: nx.DiGraph, center: str, hops: int = 2) -> str:
    """Serialize subgraph around center node as triple lines."""
    nodes = {center}
    frontier = {center}
    for _ in range(hops):
        nxt = set()
        for n in frontier:
            if n in G:
                nxt |= set(G.successors(n)) | set(G.predecessors(n))
        frontier = nxt - nodes
        nodes |= frontier
    
    existing = [n for n in nodes if n in G]
    if not existing:
        return f"(no nodes found for '{center}')"
    
    sub = G.subgraph(existing)
    lines = []
    for s, t, data in sub.edges(data=True):
        lines.append(f"({s}) --[{data.get('predicate','?')}]--> ({t}) [src: {Path(data.get('source','?')).name}]")
    return "\n".join(sorted(set(lines)))

def graph_stats(G: nx.DiGraph) -> dict:
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "projects": len([n for n in G.nodes if n.startswith("project/")]),
        "events": len([n for n in G.nodes if n.startswith("event/")]),
        "people": len([n for n in G.nodes if n.startswith("person/")]),
        "tasks": len([n for n in G.nodes if n.startswith("task/")]),
    }

# ─── Main ────────────────────────────────────────────────────
def build_graph():
    """Full pipeline: extract → resolve → assemble → save."""
    all_triples = []
    
    # Extract the complete RAB9 chronology (no rolling-window truncation).
    chron = os.path.join(RAB9, "CHRONOLOGY.md")
    if os.path.exists(chron):
        with open(chron) as f:
            chronology_content = f.read()
        chronology_lines = chronology_content.splitlines()
        dated_headings = [line for line in chronology_lines if CHRONOLOGY_HEADING_RE.match(line)]
        parsed_headings = [line for line in dated_headings if _parse_chronology_heading(line)]
        if len(parsed_headings) != len(dated_headings):
            raise ValueError(
                f"CHRONOLOGY date loss: parsed {len(parsed_headings)} of {len(dated_headings)} dated headings"
            )
        print(
            f"📖 CHRONOLOGY parsed: {len(chronology_lines)} lines, "
            f"{len(parsed_headings)} dated headings"
        )
        all_triples.extend(extract_entities_from_file(chron))
    
    # Extract from strategy
    strat = os.path.join(RAB9, "STRATEGY.md")
    if os.path.exists(strat):
        all_triples.extend(extract_entities_from_file(strat))
    
    # Resolve
    resolved = resolve_entities(all_triples)
    
    # Assemble
    G = assemble_graph(resolved)
    
    # Save
    data = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "stats": graph_stats(G),
        "nodes": list(G.nodes(data=True)),
        "edges": [
            {"source": s, "target": t, "predicate": d.get("predicate"), 
             "source_file": d.get("source"), "confidence": d.get("confidence")}
            for s, t, d in G.edges(data=True)
        ]
    }
    with open(GRAPH_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Stage 5: MAINTAIN — run checks after each rebuild
    try:
        sys.path.insert(0, GRAPH_DIR)
        import maintenance
        report = maintenance.run_report()
        summary = report.get("summary")
        if summary is None and isinstance(report.get("checks"), dict):
            summary = {k: len(v) for k, v in report["checks"].items()}
        if summary is None:
            summary = {
                k: len(v) if isinstance(v, list) else v
                for k, v in report.items()
                if k not in {"stats", "generated_at", "graph_built_at", "graph_stats"}
            }
        print(
            "🔧 Maintenance checks: "
            + ", ".join(f"{k}={v}" for k, v in (summary or {}).items())
        )
    except Exception as e:
        print(f"⚠️  Maintenance check failed (non-fatal): {e}", file=sys.stderr)

    return G

if __name__ == "__main__":
    G = build_graph()
    stats = graph_stats(G)
    print(f"📊 Knowledge Graph built: {stats['nodes']} nodes, {stats['edges']} edges")
    print(f"   📁 {stats['projects']} projects, 📅 {stats['events']} events, 👤 {stats['people']} people, 📋 {stats['tasks']} tasks")
    print(f"\n🔍 Sample queries:")
    print(f"   project/gulag (1 hop):")
    print(query_graph(G, "project/gulag", hops=1)[:300])

