"""Competition cost comparison and local leaderboard estimates."""

from __future__ import annotations

import math

from .config import TASKS


def leaderboard_estimate(costs: dict[str, float], references: dict[str, float]) -> float:
    if set(costs) != set(TASKS) or set(references) != set(TASKS):
        raise ValueError(f"Costs and references must contain exactly {TASKS}")
    log_ratios = []
    for task in TASKS:
        cost = float(costs[task])
        reference = float(references[task])
        if not math.isfinite(cost) or cost <= 0 or not math.isfinite(reference) or reference <= 0:
            raise ValueError(f"Invalid cost for {task}: cost={cost}, reference={reference}")
        log_ratios.append(math.log(reference) - math.log(cost))
    return math.exp(sum(log_ratios) / len(TASKS))


def comparison(
    task: str, *, candidate_cost: float, champion: dict, current_costs: dict[str, float]
) -> dict:
    candidate_cost = float(candidate_cost)
    champion_cost = float(champion["cost"])
    if not math.isfinite(candidate_cost) or candidate_cost <= 0:
        raise ValueError("Candidate cost must be finite and positive")
    updated_costs = dict(current_costs)
    updated_costs[task] = candidate_cost
    reference = float(champion["reference_cost"])
    return {
        "task": task,
        "candidate_cost": candidate_cost,
        "champion_cost": champion_cost,
        "champion_gain": champion_cost / candidate_cost,
        "candidate_task_score": reference / candidate_cost,
        "improved": candidate_cost < champion_cost,
        "candidate_costs": updated_costs,
    }
