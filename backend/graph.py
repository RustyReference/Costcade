import json
import math
from pathlib import Path

import networkx as nx

DATA = Path(__file__).parent / "building.json"

def load_graph(path=DATA) -> nx.DiGraph:
    """Build the dependency graph. An edge A -> B means a failure in A reaches B."""
    data = json.loads(Path(path).read_text())
    G = nx.DiGraph(sla=data["sla"], repair_min=data["repair_min"])  # reachable as G.graph[...]
    for n in data["nodes"]:
        G.add_node(n["id"], **n)
    for e in data["edges"]:
        G.add_edge(e["source"], e["target"], **e)
    if not nx.is_directed_acyclic_graph(G):
        raise ValueError("graph has a cycle")
    return G

def propagate(G: nx.DiGraph, failed: dict[str, float]) -> dict[str, float]:
    """Return the time (minutes) each node stops working; inf = never.

    T_j = min over requirement groups of (max over members of T_i + delay).
    Edges sharing a redundancy_group are interchangeable spares (max);
    separate groups are separate requirements (min).
    """
    T = {n: math.inf for n in G}
    T.update(failed)
    for j in nx.topological_sort(G):
        if j in failed:
            continue
        groups: dict[str, list[float]] = {}
        for i, _, e in G.in_edges(j, data=True):
            if not e.get("hard", True):
                continue
            key = e.get("redundancy_group") or f"{i}->{j}"
            groups.setdefault(key, []).append(T[i] + e["delay_min"])
        if groups:
            T[j] = min(max(g) for g in groups.values())
    return T


if __name__ == "__main__":
    G = load_graph()
    T = propagate(G, {"chillers": 0})
    for node, t in sorted(T.items(), key=lambda kv: kv[1]):
        if t < math.inf:
            print(f"{t:6.1f} min  {node}")
