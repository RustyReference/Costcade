from fastapi import FastAPI, HTTPException
from graph import load_graph, propagate
from cost import projected_cost, accrued_cost, time_to_breach
import time
import math

app = FastAPI()

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
    return {"message": "Hello World"}

@app.get("/api/building")
async def building():
    T = propagate(G, faults)
    t = now()
    nodes = [
        {"id": n, "label": d["label"], "kind": d["kind"], **status(n, T[n], t)}
        for n, d in G.nodes(data=True)
    ]
    edges = [
        {"source": u, "target": v, "type": d["type"]}
        for u, v, d in G.edges(data=True)
    ]
    clause = G.graph["sla"]
    repair = G.graph["repair_min"]
    t_sla = T[clause["node"]]
    start = min(faults.values(), default=0)  # earliest fault starts the repair clock
    cost = {
        "projected": projected_cost(t_sla, start, repair, clause),
        "accrued": accrued_cost(t_sla, t, start, repair, clause),
        "breach_in_min": time_to_breach(t_sla, t, clause),
    }
    return {"now_min": t, "nodes": nodes, "edges": edges, "cost": cost}

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
