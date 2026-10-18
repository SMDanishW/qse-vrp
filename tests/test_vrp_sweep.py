"""Sweep planning: one-factor-at-a-time grid, shared baseline run only once."""

from pathlib import Path

import yaml

from domains.vrp.sweep import plan

CFG = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs/vrp.yaml").read_text())


def test_baseline_runs_once_and_serves_every_experiment() -> None:
    runs = plan(CFG)
    q = CFG["qaoa"]
    for qubo in ("stage1", "stage2"):
        penalty = next(iter(CFG[qubo]["penalties"].values()))
        base = (qubo, (q["reps"], q["optimizer"], q["maxiter"], q["initial_gamma"], penalty))
        assert runs[base] == {"reps", "maxiter", "initial_gamma", "penalty"}


def test_every_requested_setting_is_planned() -> None:
    runs = plan(CFG)
    sw = CFG["sweep"]
    for qubo in ("stage1", "stage2"):
        planned = [s for (name, s) in runs if name == qubo]
        assert {s[0] for s in planned} >= set(sw["reps"])
        assert {s[1] for s in planned} == set(sw["optimizers"])
        assert {s[2] for s in planned} >= set(sw["maxiter"])
        assert {s[3] for s in planned} >= set(sw["initial_gamma"])
        assert {s[4] for s in planned} == set(sw[f"{qubo}_penalty"])
