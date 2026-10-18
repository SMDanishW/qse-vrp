"""VRP pipeline CLI: python -m domains.vrp.run --config configs/vrp.yaml

For each solver in the config:
  Stage 1 assignment QUBO -> best feasible sample -> one Stage 2 route QUBO per vehicle -> full routes.
Every QUBO passes the brute-force formulation check before it is solved; every solver run and the
chain summary are saved as JSON under results_dir.
"""

import argparse
from collections.abc import Callable
from pathlib import Path

import dimod
import yaml

from common.qubo_utils import bqm_to_qp, verify_formulation
from common.results import distribution_stats, save_result
from common.solvers import run_qaoa, run_sa
from domains.vrp.problem import (
    Solution,
    build_bqm,
    build_route_bqm,
    cluster_cost,
    decode,
    decode_route,
    is_feasible,
    load_instance,
    objective,
)


def solve(solver: str, bqm: dimod.BinaryQuadraticModel, cfg: dict) -> dict:
    if solver == "qaoa":
        q = cfg["qaoa"]
        return run_qaoa(
            bqm_to_qp(bqm),
            reps=q["reps"],
            initial_gammas=[q["initial_gamma"]] * q["reps"],
            initial_betas=[q["initial_beta"]] * q["reps"],
            optimizer=q["optimizer"],
            maxiter=q["maxiter"],
            shots=q["shots"],
            seed_transpiler=q["seed_transpiler"],
            seed_simulator=q["seed_simulator"],
        )
    if solver == "sa":
        s = cfg["sa"]
        return run_sa(bqm, num_reads=s["num_reads"], num_sweeps=s["num_sweeps"], seed=s["seed"])
    raise ValueError(f"unknown solver {solver!r}")


def solve_stage(
    solver: str,
    bqm: dimod.BinaryQuadraticModel,
    feasible: Callable[[dict[str, int]], bool],
    cfg: dict,
    meta: dict,
) -> tuple[dict, Path]:
    """Formulation check, solve, stats, save. Returns the best feasible row and the result path.

    'Best feasible' = lowest-energy feasible bitstring among all shots/reads. With 8-9 qubits and
    thousands of shots this is almost always found even by poor QAOA, so p_optimal is the real metric.
    """
    check = verify_formulation(bqm, feasible)
    result = solve(solver, bqm, cfg)
    stats = distribution_stats(result["distribution"], feasible, check["ground_energy"])
    for r in result["distribution"]:
        r["feasible"] = feasible(r["sample"])
    rows = [r for r in result["distribution"] if r["feasible"]]
    if not rows:
        raise RuntimeError(f"{solver} returned no feasible sample for {meta['stage']} {meta.get('route', '')}")
    best = min(rows, key=lambda r: r["energy"])

    record = {"domain": "vrp", "instance": cfg["instance"], "n_vars": bqm.num_variables} | meta | result
    record |= {"formulation_check": check, "stats": stats, "best_feasible": best}
    name = f"vrp_{meta['stage']}{meta.get('route_tag', '')}_{solver}"
    return best, save_result(record, cfg["results_dir"], name)


def run(cfg: dict) -> list[dict]:
    """Run the two-stage chain once per configured solver; returns one summary per solver."""
    instance = load_instance(cfg["instance"], cfg["n_vehicles"])
    pen1, pen2 = cfg["stage1"]["penalties"], cfg["stage2"]["penalties"]
    summaries = []

    for solver in cfg["solvers"]:
        best1, path1 = solve_stage(
            solver,
            build_bqm(instance, pen1),
            lambda s: is_feasible(decode(s, instance)),
            cfg,
            {"stage": "stage1", "penalties": pen1},
        )
        clusters = decode(best1["sample"], instance).routes
        stage1_extra = {"cluster_cost": cluster_cost(decode(best1["sample"], instance))}

        orders, paths2 = [], []
        for v, route in enumerate(clusters):
            best2, path2 = solve_stage(
                solver,
                build_route_bqm(instance, route, pen2),
                lambda s, route=route: decode_route(s, route) is not None,
                cfg,
                {"stage": "stage2", "vehicle": v, "route": list(route), "route_tag": f"_v{v}", "penalties": pen2},
            )
            orders.append(decode_route(best2["sample"], route))
            paths2.append(str(path2))

        final = Solution(instance, tuple(orders))
        summary = {
            "domain": "vrp",
            "stage": "chain",
            "instance": cfg["instance"],
            "solver": solver,
            "clusters": [list(c) for c in clusters],
            "routes": [[0, *r, 0] for r in final.routes],
            "objective": objective(final),
            "feasible": is_feasible(final),
            "stage1_result": str(path1),
            "stage2_results": paths2,
        } | stage1_extra
        summary["path"] = str(save_result(summary, cfg["results_dir"], f"vrp_chain_{solver}"))
        summaries.append(summary)
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path)
    cfg = yaml.safe_load(parser.parse_args().config.read_text())
    for s in run(cfg):
        print(f"{s['solver']}: routes {s['routes']} cost {s['objective']:g} feasible {s['feasible']} -> {s['path']}")


if __name__ == "__main__":
    main()
