#!/usr/bin/env python3
"""Knowledge Graph Maintenance — Step 5: Maintain & Improve.

Runs after each graph rebuild (called from scripts/knowledge_graph.py or standalone).
Checks:
  1. Stale detection      — nodes with timestamp > 7 days and no edges → archive candidates
  2. Duplicate merge      — entities with similar names (fuzzy match) → merge suggestion
  3. Contradiction detect — edges with same (subject, relation) but different objects → flag
  4. Confidence decay     — edges with confidence < 20% and stale evidence → flag
Output: knowledge_graph/maintenance_report.json
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path

GRAPH_DIR = Path(__file__).parent
GRAPH_FILE = GRAPH_DIR / "graph.json"
REPORT_FILE = GRAPH_DIR / "maintenance_report.json"

STALE_DAYS = 7
DECAY_CONFIDENCE = 0.20
DECAY_DAYS = 14
DUPLICATE_THRESHOLD = 0.85  # SequenceMatcher ratio (report mode)
MERGE_THRESHOLD = 0.80      # SequenceMatcher ratio (--merge mode, per spec)


# ─── Load ──────────────────────────────────────────────────
def _load() -> dict:
    if not GRAPH_FILE.exists():
        raise FileNotFoundError(f"No graph.json at {GRAPH_FILE}. Run knowledge_graph.py first.")
    with open(GRAPH_FILE) as f:
        return json.load(f)


def _parse_date(s: str):
    """Parse ISO-ish date string → aware datetime, or None."""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def _node_timestamp(node_id: str, built_at: datetime) -> datetime:
    """Best-effort node timestamp: date embedded in event/YYYY-MM-DD/... IDs,
    otherwise the graph build time (conservative — never flags fresh rebuilds)."""
    m = re.match(r"event/(\d{4}-\d{2}-\d{2})/", node_id)
    if m:
        dt = _parse_date(m.group(1))
        if dt:
            return dt
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})", node_id)
    if m:
        dt = _parse_date(m.group(1))
        if dt:
            return dt
    return built_at


# ─── Check 1: Stale detection ──────────────────────────────
def check_stale(data: dict, now: datetime) -> list[dict]:
    built_at = _parse_date(data.get("built_at", "")) or now
    connected = set()
    for e in data.get("edges", []):
        connected.add(e["source"])
        connected.add(e["target"])

    cutoff = now - timedelta(days=STALE_DAYS)
    stale = []
    for node in data.get("nodes", []):
        node_id, attrs = node[0], (node[1] if len(node) > 1 else {})
        if node_id in connected:
            continue
        ts = _node_timestamp(node_id, built_at)
        if ts < cutoff:
            stale.append({
                "node": node_id,
                "type": attrs.get("type", "unknown"),
                "timestamp": ts.isoformat(),
                "reason": f"no edges and older than {STALE_DAYS} days",
                "action": "archive_candidate",
            })
    return stale


def _numbers_differ(a: str, b: str) -> bool:
    """Guard against false-positive fuzzy matches: entities whose numeric tokens
    differ (task/T-132 vs T-133, cron run 6th vs 7th, different dates) are
    DISTINCT entities, not duplicates — no matter how similar the strings."""
    na = sorted(re.findall(r"\d+", a))
    nb = sorted(re.findall(r"\d+", b))
    return na != nb


# ─── Check 2: Duplicate merge ──────────────────────────────
def check_duplicates(data: dict) -> list[dict]:
    node_ids = [n[0] for n in data.get("nodes", [])]
    dupes = []
    seen_pairs = set()
    for i, a in enumerate(node_ids):
        for b in node_ids[i + 1:]:
            # Only compare same-prefix (type) entities to cut noise
            pa, pb = a.split("/")[0], b.split("/")[0]
            if pa != pb:
                continue
            if _numbers_differ(a, b):
                continue
            ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
            if ratio >= DUPLICATE_THRESHOLD and (a, b) not in seen_pairs:
                seen_pairs.add((a, b))
                canonical, duplicate = (a, b) if len(a) <= len(b) else (b, a)
                dupes.append({
                    "canonical": canonical,
                    "duplicate": duplicate,
                    "similarity": round(ratio, 3),
                    "action": "merge_into_canonical_preserve_provenance",
                })
    return dupes


# ─── Check 3: Contradiction detection ──────────────────────
def check_contradictions(data: dict) -> list[dict]:
    by_sr: dict[tuple, list[dict]] = {}
    for e in data.get("edges", []):
        key = (e["source"], e.get("predicate", "?"))
        by_sr.setdefault(key, []).append(e)

    contradictions = []
    # Predicates where multiple distinct objects are legitimate
    MULTI_OK = {"mentioned_in", "referenced_in", "described_as"}
    for (subj, pred), edges in by_sr.items():
        if pred in MULTI_OK:
            continue
        objects = {e["target"] for e in edges}
        if len(objects) > 1:
            contradictions.append({
                "subject": subj,
                "predicate": pred,
                "conflicting_objects": sorted(objects),
                "edges": [
                    {
                        "target": e["target"],
                        "confidence": e.get("confidence"),
                        "source_file": Path(e.get("source_file", "?")).name,
                    }
                    for e in edges
                ],
                "action": "flag_for_review",
            })
    return contradictions


# ─── Check 4: Confidence decay ─────────────────────────────
def check_confidence_decay(data: dict, now: datetime) -> list[dict]:
    built_at = _parse_date(data.get("built_at", "")) or now
    cutoff = now - timedelta(days=DECAY_DAYS)
    decayed = []
    for e in data.get("edges", []):
        conf = e.get("confidence", 0.5)
        if conf >= DECAY_CONFIDENCE:
            continue
        # No per-edge timestamps in graph.json yet — evidence age proxied by
        # source file mtime; fall back to graph build time.
        src = e.get("source_file", "")
        evidence_ts = built_at
        try:
            if src and Path(src).exists():
                evidence_ts = datetime.fromtimestamp(Path(src).stat().st_mtime, tz=timezone.utc)
        except OSError:
            pass
        if evidence_ts < cutoff:
            decayed.append({
                "edge": f"{e['source']} → {e.get('predicate','?')} → {e['target']}",
                "confidence": conf,
                "last_evidence": evidence_ts.isoformat(),
                "reason": f"confidence < {DECAY_CONFIDENCE:.0%} and no new evidence in {DECAY_DAYS} days",
                "action": "flag_for_removal_or_reverification",
            })
    return decayed


# ─── Merge mode: actually merge duplicates into canonical ──
def _union_find_clusters(pairs: list[tuple[str, str]]) -> list[set[str]]:
    """Union-find over similar-name pairs → clusters of node ids."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in pairs:
        union(a, b)

    clusters: dict[str, set[str]] = {}
    for x in parent:
        clusters.setdefault(find(x), set()).add(x)
    return [c for c in clusters.values() if len(c) > 1]


def run_merge(threshold: float = MERGE_THRESHOLD) -> dict:
    """Merge similar entities into canonical nodes (longest name wins).

    - Fuzzy-match node ids (SequenceMatcher > threshold), same type-prefix only.
    - Union-find clusters so chains (a~b, b~c) merge into one canonical.
    - All edges preserved; redirected endpoints tagged with merged_from provenance.
    - Canonical node attrs get merged_from: [list of absorbed node ids].
    - Backs up graph.json → graph.json.bak-merge-YYYYMMDD_HHMMSS before writing.
    """
    import shutil

    data = _load()
    now = datetime.now(timezone.utc)
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    node_ids = [n[0] for n in nodes]
    node_map = {n[0]: (n[1] if len(n) > 1 else {}) for n in nodes}

    # 1. Find similar pairs (same type-prefix, ratio > threshold, same numbers)
    pairs = []
    for i, a in enumerate(node_ids):
        pa = a.split("/")[0]
        for b in node_ids[i + 1:]:
            if b.split("/")[0] != pa:
                continue
            if _numbers_differ(a, b):
                continue
            ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
            if ratio > threshold:
                pairs.append((a, b))

    clusters = _union_find_clusters(pairs)

    # 2. Canonical = longest name in cluster; build redirect map
    redirect: dict[str, str] = {}
    cluster_report = []
    for cluster in clusters:
        canonical = max(cluster, key=lambda x: (len(x), x))
        merged = sorted(c for c in cluster if c != canonical)
        for m in merged:
            redirect[m] = canonical
        cluster_report.append({"canonical": canonical, "merged": merged})

    if not redirect:
        return {"merged_clusters": 0, "merged_nodes": 0, "edges_redirected": 0,
                "clusters": [], "message": "no duplicates above threshold"}

    # 3. Rewrite edges — preserve ALL edges, tag redirected endpoints
    edges_redirected = 0
    for e in edges:
        src_orig, tgt_orig = e["source"], e["target"]
        if src_orig in redirect:
            e["source"] = redirect[src_orig]
            e.setdefault("merged_from", {})["source"] = src_orig
            edges_redirected += 1
        if tgt_orig in redirect:
            e["target"] = redirect[tgt_orig]
            e.setdefault("merged_from", {})["target"] = tgt_orig
            edges_redirected += 1

    # 4. Drop absorbed nodes; record provenance on canonical nodes
    kept_nodes = []
    absorbed: dict[str, list[str]] = {}
    for m, c in redirect.items():
        absorbed.setdefault(c, []).append(m)
    for node in nodes:
        node_id = node[0]
        if node_id in redirect:
            continue
        if node_id in absorbed:
            attrs = node[1] if len(node) > 1 else {}
            prior = attrs.get("merged_from", [])
            attrs["merged_from"] = sorted(set(prior) | set(absorbed[node_id]))
            if len(node) > 1:
                node[1] = attrs
            else:
                node.append(attrs)
        kept_nodes.append(node)
    data["nodes"] = kept_nodes

    # 5. Update stats + provenance metadata
    stats = data.setdefault("stats", {})
    stats["nodes"] = len(kept_nodes)
    stats["edges"] = len(edges)
    data["last_merge"] = {
        "at": now.isoformat(),
        "threshold": threshold,
        "clusters": len(cluster_report),
        "nodes_merged": len(redirect),
        "edges_redirected": edges_redirected,
    }

    # 6. Backup + write
    backup = GRAPH_FILE.with_suffix(f".json.bak-merge-{now.strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(GRAPH_FILE, backup)
    with open(GRAPH_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return {
        "merged_clusters": len(cluster_report),
        "merged_nodes": len(redirect),
        "edges_redirected": edges_redirected,
        "backup": str(backup),
        "clusters": cluster_report,
    }


# ─── Report ────────────────────────────────────────────────
def run_report() -> dict:
    data = _load()
    now = datetime.now(timezone.utc)
    report = {
        "generated_at": now.isoformat(),
        "graph_built_at": data.get("built_at"),
        "graph_stats": data.get("stats", {}),
        "checks": {
            "stale_nodes": check_stale(data, now),
            "duplicate_entities": check_duplicates(data),
            "contradictions": check_contradictions(data),
            "confidence_decay": check_confidence_decay(data, now),
        },
    }
    report["summary"] = {k: len(v) for k, v in report["checks"].items()}
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Knowledge Graph maintenance")
    parser.add_argument("--report", action="store_true", help="run all checks and write maintenance_report.json")
    parser.add_argument("--merge", action="store_true", help="merge duplicate entities into canonical nodes (longest name wins)")
    args = parser.parse_args()

    if args.merge:
        r = run_merge()
        print(f"🔀 Merge complete → {GRAPH_FILE}")
        print(f"   clusters merged:   {r['merged_clusters']}")
        print(f"   nodes absorbed:    {r['merged_nodes']}")
        print(f"   edges redirected:  {r['edges_redirected']}")
        if r.get("backup"):
            print(f"   backup:            {r['backup']}")
        for c in r["clusters"][:20]:
            print(f"   ✓ {c['canonical']}  ←  {', '.join(c['merged'])}")
        if len(r["clusters"]) > 20:
            print(f"   … and {len(r['clusters']) - 20} more clusters")
    elif args.report or len(sys.argv) == 1:
        r = run_report()
        s = r["summary"]
        print(f"🔧 Maintenance report → {REPORT_FILE}")
        print(f"   stale_nodes:        {s['stale_nodes']}")
        print(f"   duplicate_entities: {s['duplicate_entities']}")
        print(f"   contradictions:     {s['contradictions']}")
        print(f"   confidence_decay:   {s['confidence_decay']}")
    else:
        parser.print_help()


