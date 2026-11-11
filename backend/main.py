from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from graph import load_graph, propagate
from cost import projected_cost, accrued_cost, time_to_breach, rank_actions
import networkx as nx
import time
import math

app = FastAPI()
FRONTEND = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

START = time.monotonic()
SPEED = 60 # 60 seconds a minute to fast-forward the simulation
G = load_graph()
faults: dict[str, float] = {} # node_id: time_of_fault

def now():
    """
    Simulated minutes since the server started
    """
    return (time.monotonic() - START) * SPEED / 60

def status(node: str, t_fail: float, t: float) -> dict:
    if node in faults:
        return {"status": "origin", "eta_min": 0}
    if t_fail <= t:
        return {"status": "red", "eta_min": 0}
    if t_fail < math.inf:
        return {"status": "yellow", "eta_min": t_fail - t}
    return {"status": "green", "eta_min": None}

@app.get("/")
async def root():
    return FileResponse(FRONTEND / "index.html")

@app.get("/api/building")
async def building():
    T = propagate(G, faults)
    t = now()
    nodes = [
        {"id": n, "label": d["label"], "kind": d["kind"], **status(n, T[n], t)}
        for n, d in G.nodes(data=True)
    ]
    edges = [
        {"source": u, "target": v, "type": d["type"], "delay_min": d["delay_min"], "tier": d["tier"], "hard": d.get("hard", True)}
        for u, v, d in G.edges(data=True)
    ]
    repair = G.graph["repair_min"]
    start = min(faults.values(), default=0)  # earliest fault starts the repair clock
    slas = []
    per_sla = []
    for c in G.graph["slas"]:
        t_sla = T[c["node"]]
        slas.append((c["id"], t_sla, c, nx.ancestors(G, c["node"])))  # ancestors: nodes whose repair can help this SLA
        per_sla.append({
            "id": c["id"],
            "projected": projected_cost(t_sla, start, repair, c),
            "accrued": accrued_cost(t_sla, t, start, repair, c),
            "breach_in_min": time_to_breach(t_sla, t, c),
        })
    breaches = [s["breach_in_min"] for s in per_sla if s["breach_in_min"] is not None]
    cost = {
        "total": {
            "projected": sum(s["projected"] for s in per_sla),
            "accrued": sum(s["accrued"] for s in per_sla),
            "breach_in_min": min(breaches, default=None),  # soonest breach across SLAs
        },
        "slas": per_sla,
    }
    helpable = set().union(*(s[3] for s in slas))
    applicable = [a for a in G.graph["actions"] if a["target_node"] in helpable and T[a["target_node"]] < math.inf]
    actions = rank_actions(applicable, slas, t, start, repair)
    return {"now_min": t, "nodes": nodes, "edges": edges, "cost": cost, "actions": actions}

@app.post("/api/fault")
async def fault(node_id: str):
    if node_id not in G:
        raise HTTPException(status_code=404, detail="unknown node")

    faults[node_id] = now()

    return {"ok": True}

@app.delete("/api/fault/{node_id}")
async def remove_fault(node_id: str):
    if node_id not in G:
        raise HTTPException(status_code=404, detail="unknown node")

    faults.pop(node_id, None)

    return {"ok": True}
