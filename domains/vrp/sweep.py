"""Task 8 QAOA study on the VRP QUBOs: python -m domains.vrp.sweep --config configs/vrp.yaml [--plot-only]

One factor at a time around cfg["sweep"]["baseline"]: reps x optimizer, budget x optimizer, initial gamma, penalty.
QUBOs: Stage 1 (8 qubits) and the 3-customer Stage 2 route of the Stage 1 optimum (9 qubits).
Every run is saved as JSON with its full distribution; summary.csv and figures go to sweep.results_dir.
"""

import argparse
import csv
from collections.abc import Callable
from pathlib import Path

import dimod
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator, NullFormatter  # noqa: E402
import yaml  # noqa: E402

from common.qubo_utils import bqm_to_qp, verify_formulation  # noqa: E402
from common.results import distribution_stats, load_result, save_result  # noqa: E402
from common.solvers import run_qaoa  # noqa: E402
from domains.vrp.problem import (  # noqa: E402
    build_bqm,
    build_route_bqm,
    decode,
    decode_route,
    is_feasible,
    load_instance,
)

SETTINGS = ("reps", "optimizer", "maxiter", "initial_gamma", "penalty")
QUBO_LABEL = {"stage1": "Stage 1 assignment (8 qubits)", "stage2": "Stage 2 route {1,2,5} (9 qubits)"}


def build_qubos(cfg: dict) -> dict[str, Callable[[float], tuple[dimod.BinaryQuadraticModel, Callable]]]:
    """Per QUBO: penalty P -> (BQM with both penalty terms = P, feasibility test)."""
    instance = load_instance(cfg["instance"], cfg["n_vehicles"])
    pen1 = cfg["stage1"]["penalties"]
    ground = verify_formulation(build_bqm(instance, pen1), lambda s: is_feasible(decode(s, instance)))
    route = max(decode(ground["ground_states"][0], instance).routes, key=len)
    return {
        "stage1": lambda p: (
            build_bqm(instance, {"one_vehicle": p, "capacity": p}),
            lambda s: is_feasible(decode(s, instance)),
        ),
        "stage2": lambda p: (
            build_route_bqm(instance, route, {"one_position": p, "one_customer": p}),
            lambda s: decode_route(s, route) is not None,
        ),
    }


def plan(cfg: dict) -> dict[tuple[str, tuple], set[str]]:
    """(qubo, settings) -> experiments that need it; shared baseline points run once."""
    sw = cfg["sweep"]
    q = cfg["qaoa"] | sw["baseline"]
    runs: dict[tuple[str, tuple], set[str]] = {}
    for qubo, penalties in (("stage1", sw["stage1_penalty"]), ("stage2", sw["stage2_penalty"])):
        base = {
            "reps": q["reps"],
            "optimizer": q["optimizer"],
            "maxiter": q["maxiter"],
            "initial_gamma": q["initial_gamma"],
            "penalty": next(iter(cfg[qubo]["penalties"].values())),
        }
        variants = (
            [("reps", base | {"reps": r, "optimizer": o}) for r in sw["reps"] for o in sw["optimizers"]]
            + [("maxiter", base | {"maxiter": m, "optimizer": o}) for m in sw["maxiter"] for o in sw["optimizers"]]
            + [("initial_gamma", base | {"initial_gamma": g}) for g in sw["initial_gamma"]]
            + [("penalty", base | {"penalty": p}) for p in sw[f"{qubo}_penalty"]]
        )
        for experiment, s in variants:
            runs.setdefault((qubo, tuple(s[k] for k in SETTINGS)), set()).add(experiment)
    return runs


def sweep(cfg: dict) -> list[dict]:
    q, out = cfg["qaoa"], Path(cfg["sweep"]["results_dir"])
    qubos, checks, rows = build_qubos(cfg), {}, []
    runs = plan(cfg)
    for n, ((qubo, values), experiments) in enumerate(runs.items(), 1):
        s = dict(zip(SETTINGS, values))
        bqm, feasible = qubos[qubo](s["penalty"])
        if (qubo, s["penalty"]) not in checks:
            checks[(qubo, s["penalty"])] = verify_formulation(bqm, feasible)
        check = checks[(qubo, s["penalty"])]
        result = run_qaoa(
            bqm_to_qp(bqm),
            reps=s["reps"],
            initial_gammas=[s["initial_gamma"]] * s["reps"],
            initial_betas=[q["initial_beta"]] * s["reps"],
            optimizer=s["optimizer"],
            maxiter=s["maxiter"],
            shots=q["shots"],
            seed_transpiler=q["seed_transpiler"],
            seed_simulator=q["seed_simulator"],
        )
        stats = distribution_stats(result["distribution"], feasible, check["ground_energy"])
        for r in result["distribution"]:
            r["feasible"] = feasible(r["sample"])
        uniform = len(check["ground_states"]) / 2 ** bqm.num_variables
        record = {"domain": "vrp", "instance": cfg["instance"], "stage": qubo, "n_vars": bqm.num_variables,
                  "experiments": sorted(experiments), "penalty": s["penalty"]} | result
        record |= {"formulation_check": check, "stats": stats, "p_optimal_uniform": uniform}
        path = save_result(record, out / qubo, f"vrp_{qubo}_qaoa")
        rows.append({
            "qubo": qubo, "experiments": "+".join(sorted(experiments)), **s,
            "n_qubits": bqm.num_variables, "p_optimal": stats["p_optimal"], "p_feasible": stats["p_feasible"],
            "lift_vs_uniform": stats["p_optimal"] / uniform, "expected_energy": result["expected_energy"],
            "ground_energy": check["ground_energy"], "n_evaluations": result["n_evaluations"],
            "hw_depth": result["circuit"]["hardware_basis_depth"],
            "hw_cx": result["circuit"]["hardware_basis_ops"].get("cx", 0),
            "runtime_s": round(result["runtime_s"], 3), "path": str(path),
        })
        print(f"[{n}/{len(runs)}] {qubo} {s} p_opt={stats['p_optimal']:.3f} p_feas={stats['p_feasible']:.3f}")

    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


# ---------------------------------------------------------------- figures (static PNG for the report)

# Validated reference palette (dataviz skill, light mode): fixed categorical order, recessive neutrals.
SERIES = {"COBYLA": "#2a78d6", "Nelder-Mead": "#eb6834", "Powell": "#1baf7a"}
MARKERS = {"COBYLA": "o", "Nelder-Mead": "s", "Powell": "^"}  # secondary encoding (aqua contrast < 3:1)
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def _axes(nrows: int, ncols: int, width: float, height: float):
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height), squeeze=False, facecolor=SURFACE)
    for ax in axes.flat:
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=9)
    return fig, axes


def _metric_grid(rows: list[dict], experiment: str, x: str, xlabel: str, out: Path, by_optimizer: bool,
                 logx: bool = False) -> None:
    """2 x 2: rows p_optimal / p_feasible, columns Stage 1 / Stage 2. One y-axis per panel."""
    fig, axes = _axes(2, 2, 10, 6.5)
    for col, qubo in enumerate(("stage1", "stage2")):
        sel = [r for r in rows if r["qubo"] == qubo and experiment in r["experiments"].split("+")]
        groups = sorted({r["optimizer"] for r in sel}, key=list(SERIES).index) if by_optimizer else [None]
        for row, metric in enumerate(("p_optimal", "p_feasible")):
            ax = axes[row][col]
            top = max(float(r[metric]) for r in sel)
            for g in groups:
                pts = sorted((float(r[x]), float(r[metric])) for r in sel if g is None or r["optimizer"] == g)
                name = g or sel[0]["optimizer"]
                ax.plot(*zip(*pts), color=SERIES[name], marker=MARKERS[name], markersize=6, linewidth=2, label=name)
            if metric == "p_optimal":
                ref = min(float(r["p_optimal"]) / float(r["lift_vs_uniform"]) for r in sel if float(r["lift_vs_uniform"]) > 0)
                ax.axhline(ref, color=MUTED, linewidth=1, linestyle="--", label="uniform |+⟩ (γ = 0)")
            if logx:
                ax.set_xscale("log")
                ax.set_xticks([25, 50, 100, 200, 500, 1000], labels=["25", "50", "100", "200", "500", "1000"])
                ax.xaxis.set_minor_formatter(NullFormatter())
            if x == "reps":
                ax.xaxis.set_major_locator(MaxNLocator(integer=True))
            ax.set_ylim(0, top * 1.12)
            ax.set_ylabel(metric.replace("_", " "), color=INK, fontsize=10)
            if row == 0:
                ax.set_title(QUBO_LABEL[qubo], color=INK, fontsize=11, loc="left")
            if row == 1:
                ax.set_xlabel(xlabel, color=INK, fontsize=10)
    axes[0][1].legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _distribution(path: str, out: Path, title: str) -> None:
    """Probability of every measured bitstring, ordered by QUBO energy; colour = solution class."""
    r = load_result(path)
    g = r["formulation_check"]["ground_energy"]
    total = sum(x["count"] for x in r["distribution"])
    fig, axes = _axes(1, 1, 10, 3.6)
    ax = axes[0][0]
    classes = {"optimal": ("#2a78d6", []), "other feasible": ("#eb6834", []), "infeasible": ("#b9b8b2", [])}
    for k, x in enumerate(r["distribution"]):
        key = "infeasible" if not x["feasible"] else "optimal" if abs(x["energy"] - g) < 1e-6 else "other feasible"
        classes[key][1].append((k, x["count"] / total))
    for name, (color, pts) in classes.items():
        if pts:
            ax.bar(*zip(*pts), width=0.8, color=color, label=f"{name} ({sum(p for _, p in pts):.1%})")
    ax.set_xlabel("measured bitstrings, sorted by QUBO energy (low → high)", color=INK, fontsize=10)
    ax.set_ylabel("probability", color=INK, fontsize=10)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot(rows: list[dict], out: Path) -> None:
    _metric_grid(rows, "reps", "reps", "QAOA layers p", out / "fig_reps.png", by_optimizer=True)
    _metric_grid(rows, "maxiter", "n_evaluations", "energy evaluations used", out / "fig_budget.png",
                 by_optimizer=True, logx=True)
    _metric_grid(rows, "initial_gamma", "initial_gamma", "initial γ (normalised units)", out / "fig_gamma.png",
                 by_optimizer=False)
    _metric_grid(rows, "penalty", "penalty", "penalty weight P", out / "fig_penalty.png", by_optimizer=False)
    for qubo in ("stage1", "stage2"):
        best = max((r for r in rows if r["qubo"] == qubo), key=lambda r: float(r["p_optimal"]))
        title = (f"{QUBO_LABEL[qubo]}: best run, p={best['reps']}, {best['optimizer']}, "
                 f"P={best['penalty']}, p_optimal={float(best['p_optimal']):.3f}")
        _distribution(best["path"], out / f"fig_distribution_{qubo}.png", title)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--plot-only", action="store_true", help="redraw figures from summary.csv")
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text())
    out = Path(cfg["sweep"]["results_dir"])
    if args.plot_only:
        with (out / "summary.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    else:
        rows = sweep(cfg)
    plot(rows, out)


if __name__ == "__main__":
    main()
