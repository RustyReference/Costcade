import math

def stepped_credit(excess_min: float, clause: dict[str, int]) -> float:
    num_blocks = math.ceil(excess_min / clause["step_min"])
    total_pct = num_blocks * clause["step_pct"]
    final_pct = min(total_pct, clause["cap_pct"]) / 100

    return final_pct * clause["mrc"]

MONTH_MIN = 43200  # 30-day month

def pro_rata_credit(excess_min: float, clause: dict) -> float:
    return min(excess_min / MONTH_MIN, clause["cap_pct"] / 100) * clause["mrc"]

def sla_credit(excess_min: float, clause: dict) -> float:
    methods = {"stepped": stepped_credit, "pro_rata": pro_rata_credit}
    return methods[clause["method"]](excess_min, clause)

def downtime_min(t_sla: float, end: float) -> float:
    if t_sla == math.inf or end < t_sla:
        return 0

    return end - t_sla

def projected_cost(t_sla: float, fault_start: float, repair_min: float, clause: dict[str, int]) -> float:
    down = downtime_min(t_sla, fault_start + repair_min)
    excess = max(down - clause["allowance_min"], 0)
    
    return sla_credit(excess, clause)

def accrued_cost(t_sla: float, t: float, fault_start: float, repair_min: float, clause: dict) -> float:
    """Credit owed so far: projected_cost with the clock stopped at 'now' (or at repair, if sooner)."""
    return projected_cost(t_sla, fault_start, min(t - fault_start, repair_min), clause)

def time_to_breach(t_sla: float, t: float, clause: dict) -> float | None:
    """Minutes until credits start; None if the SLA node never fails, 0 once past it."""
    if t_sla == math.inf:
        return None
    return max(t_sla + clause["allowance_min"] - t, 0)

if __name__ == "__main__":
    c = {"method": "stepped", "mrc": 50000, "allowance_min": 43.2, "step_pct": 5, "step_min": 30, "cap_pct": 100}
    assert projected_cost(6, 0, 180, c) == 12500  # worked example
    assert projected_cost(6, 0, 40, c) == 0  # back up inside the allowance
    assert projected_cost(math.inf, 0, 180, c) == 0  # SLA node never fails
    assert round(projected_cost(6, 0, 180, {**c, "method": "pro_rata"}), 2) == 151.39  # same outage, pro rata
    assert accrued_cost(6, 3, 0, 180, c) == 0  # SLA node not down yet
    assert accrued_cost(6, 100, 0, 180, c) == 5000  # 94 min down, 50.8 excess, 2 blocks
    assert accrued_cost(6, 500, 0, 180, c) == 12500  # clock stops at repair
    assert round(time_to_breach(6, 0, c), 1) == 49.2
    assert time_to_breach(6, 100, c) == 0
    assert time_to_breach(math.inf, 0, c) is None
    print("ok")
