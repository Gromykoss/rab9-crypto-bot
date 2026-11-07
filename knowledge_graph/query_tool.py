"""Query tool for Knowledge Graph — Steps 10-12.
Loads graph.json, serializes subgraph, queries DeepSeek for reasoning.
Every answer cites specific edges.
"""
import json, os, sys
from pathlib import Path
from typing import Optional

import networkx as nx

GRAPH_DIR = Path(__file__).parent
GRAPH_FILE = GRAPH_DIR / "graph.json"

# ─── Load ────────────────────────────────────────────────
def _load_graph() -> nx.DiGraph:
    """Load NetworkX graph from graph.json."""
    if not GRAPH_FILE.exists():
        raise FileNotFoundError(f"No graph.json at {GRAPH_FILE}. Run knowledge_graph.py first.")
    
    with open(GRAPH_FILE) as f:
        data = json.load(f)
    
    G = nx.DiGraph()
    for node_id, attrs in data.get("nodes", []):
        G.add_node(node_id, **attrs)
    for edge in data.get("edges", []):
        G.add_edge(
            edge["source"], edge["target"],
            predicate=edge.get("predicate", "?"),
            source_file=edge.get("source_file", "?"),
            confidence=edge.get("confidence", 0.5),
        )
    return G


# ─── Serialize ───────────────────────────────────────────
def serialize_subgraph(center: str, hops: int = 2) -> str:
    """Serialize subgraph around center as triple lines with edge citations."""
    G = _load_graph()
    
    if center not in G:
        return f"(no entity found: '{center}')"
    
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
    if len(existing) <= 1:
        return f"(entity '{center}' has no connections)"
    
    sub = G.subgraph(existing)
    lines = []
    for s, t, data in sub.edges(data=True):
        pred = data.get("predicate", "?")
        src = Path(data.get("source_file", "?")).name
        conf = data.get("confidence", 0.5)
        lines.append(f"{s}  --[{pred}]-->  {t}  [src: {src}, conf: {conf:.0%}]")
    
    # Stats
    lines.append(f"\n({len(existing)} nodes, {len(lines)-1} edges in subgraph)")
    return "\n".join(sorted(set(lines)))


# ─── Query with DeepSeek ─────────────────────────────────
def query_knowledge_graph(
    question: str,
    center_entity: Optional[str] = None,
    max_hops: int = 2,
) -> str:
    """Query the knowledge graph. Uses DeepSeek for reasoning if question provided.
    Returns answer with cited edges (Step 11: every answer cites edges).
    """
    G = _load_graph()
    now = data = None
    with open(GRAPH_FILE) as f:
        data = json.load(f)
        now = data.get("built_at", "unknown")
    
    # If center entity given, serialize subgraph
    if center_entity:
        context = serialize_subgraph(center_entity, hops=max_hops)
    else:
        # Auto-center on most recent event for temporal questions
        events = [n for n in G.nodes if n.startswith("event/")]
        if events:
            events_sorted = sorted(events, reverse=True)
            center_entity = events_sorted[0]
            context = serialize_subgraph(center_entity, hops=max_hops)
        else:
            # No events — serialize recent edges as before
            all_edges = data.get("edges", [])
            sample = all_edges[-50:]
            lines = []
            for e in sample:
                lines.append(f"{e['source']}  --[{e.get('predicate','?')}]-->  {e['target']}  [src: {Path(e.get('source_file','?')).name}]")
            stats = data.get("stats", {})
            context = f"Graph ({stats.get('nodes','?')} nodes):\n" + "\n".join(sorted(set(lines)))
            if len(all_edges) > 50:
                context += f"\n({len(all_edges)-50} more edges omitted)"
    
    # If no question, just return context
    if not question:
        return f"Graph snapshot ({now}):\n{context}"
    
    # Query DeepSeek
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        # Try .env
        env_file = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    if "DEEPSEEK_API_KEY" in line and "=" in line:
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    
    if not api_key:
        return f"(no DeepSeek key — raw graph data)\n{context}"
    
    import urllib.request
    
    prompt = f"""Answer using only the knowledge graph below. Cite the specific edges that support your answer.

<graph>
{context}
</graph>

Question: {question}

Answer format:
ANSWER: [your answer]
CITED EDGES: [list edge IDs or "none"]"""

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps({
            "model": "deepseek-v4-pro",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
            "temperature": 0.3,
        }).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        answer = result["choices"][0]["message"]["content"]
        return f"Knowledge Graph ({now}):\n{answer}"
    except Exception as e:
        return f"(DeepSeek error: {e})\nRaw graph:\n{context}"


def _read_env_key(key: str) -> str:
    """Read a key from ~/.hermes/.env (fallback to environment)."""
    val = os.environ.get(key, "")
    if val:
        return val
    env_file = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.strip().startswith(key) and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ─── Step 4: GROUNDED ANSWER (Kimi K3 via Moonshot) ──────────
def grounded_answer(question: str, center_entity: Optional[str] = None, max_hops: int = 2) -> str:
    """Reason over the knowledge graph with Kimi K3 (Moonshot, 1M context).
    Every claim MUST cite a specific edge. Contradictions flagged explicitly.

    Output:
        ANSWER: <reasoned answer>
        EVIDENCE:
        - [node A] → [relation] → [node B] (confidence: X%, source: ...)
    """
    with open(GRAPH_FILE) as f:
        data = json.load(f)
    built_at = data.get("built_at", "unknown")

    # 1. Query graph for relevant subgraph
    if center_entity:
        subgraph = serialize_subgraph(center_entity, hops=max_hops)
    else:
        all_edges = data.get("edges", [])
        lines = []
        for e in all_edges:
            conf = e.get("confidence", 0.5)
            src = Path(e.get("source_file", "?")).name
            lines.append(
                f"[{e['source']}] → [{e.get('predicate','?')}] → [{e['target']}] "
                f"(confidence: {conf:.0%}, source: {src})"
            )
        subgraph = "\n".join(sorted(set(lines)))

    api_key = _read_env_key("DEEPSEEK_API_KEY")
    if not api_key:
        return f"(no DEEPSEEK_API_KEY — raw subgraph)\n{subgraph}"

    # 2-3. Pass subgraph + question to DeepSeek, which reasons and cites edges
    import urllib.request

    system = (
        "You reason over a knowledge graph. Every claim MUST cite a specific edge "
        "from the graph. If you find contradictions (two edges with same subject+relation "
        "but different objects), flag them explicitly under CONTRADICTIONS. "
        "Answer in this exact format:\n"
        "ANSWER: <reasoned answer>\n\n"
        "EVIDENCE:\n"
        "- [node A] → [relation] → [node B] (confidence: X%, source: <file>)\n\n"
        "CONTRADICTIONS: <list or 'none'>"
    )
    payload = {
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"GRAPH:\n{subgraph}\n\nQUESTION: {question}"},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    import time
    import urllib.error
    last_err = None
    for attempt in range(4):
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read())
            answer = result["choices"][0]["message"]["content"]
            return f"Knowledge Graph ({built_at}):\n{answer}"
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            last_err = f"HTTP {e.code}: {body}"
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            break
        except Exception as e:
            last_err = str(e)
            break
    return f"(DeepSeek error: {last_err})\nRaw subgraph:\n{subgraph}"


# ─── MCP-compatible tool function ─────────────────────────
def mcp_query_graph(question: str = "", entity: str = "", hops: int = 2) -> str:
    """MCP tool wrapper. Called by Hermes agents via terminal."""
    return query_knowledge_graph(
        question=question,
        center_entity=entity or None,
        max_hops=hops,
    )


# ─── CLI ──────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "grounded_answer":
        if len(args) < 2:
            print("Usage: query_tool.py grounded_answer \"<question>\" [center_entity]")
            sys.exit(1)
        question = args[1]
        center = args[2] if len(args) > 2 else None
        print(grounded_answer(question, center_entity=center))
    else:
        print("🧠 RAB9 Knowledge Graph Query")
        print(query_knowledge_graph("What happened in the last 3 days?"))
        print()
        if "project/gulag" in _load_graph():
            print(query_knowledge_graph("What is the GULAG project status?", center_entity="project/gulag"))

