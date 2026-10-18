"""Tests for common/solvers.py and common/results.py."""

import math

import dimod

from common.qubo_utils import bqm_to_qp, verify_formulation
from common.results import distribution_stats, load_result, save_result
from common.solvers import run_qaoa, run_sa


def asymmetric_qp():
    """3 variables with distinct biases, so reading the bitstring in the wrong order changes energies."""
    bqm = dimod.BinaryQuadraticModel({"a": -3.0, "b": 1.0, "c": 2.0}, {("a", "c"): -1.5}, 0.5, dimod.BINARY)
    return bqm, bqm_to_qp(bqm)


def test_qaoa_sample_energies_agree_with_estimator() -> None:
    # End-to-end check of bit order and parameter binding: the mean energy of the sampled bitstrings
    # (decoded by name) must match the exact expectation the optimiser saw, within shot noise.
    bqm, qp = asymmetric_qp()
    shots = 20_000
    result = run_qaoa(
        qp, reps=1, initial_gammas=[0.4], initial_betas=[0.3], optimizer="COBYLA",
        maxiter=50, shots=shots, seed_transpiler=7, seed_simulator=7,
    )
    rows = result["distribution"]
    assert sum(r["count"] for r in rows) == shots
    for r in rows:
        assert r["energy"] == bqm.energy(r["sample"])
    mean = sum(r["energy"] * r["count"] for r in rows) / shots
    std = math.sqrt(sum((r["energy"] - mean) ** 2 * r["count"] for r in rows) / shots)
    assert abs(mean - result["expected_energy"]) < 5 * std / math.sqrt(shots)


def test_qaoa_rejects_wrong_parameter_count() -> None:
    _, qp = asymmetric_qp()
    try:
        run_qaoa(qp, reps=2, initial_gammas=[0.1], initial_betas=[0.1], optimizer="COBYLA",
                 maxiter=1, shots=10, seed_transpiler=0, seed_simulator=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_sa_finds_ground_state_and_stats(tmp_path) -> None:
    bqm, _ = asymmetric_qp()
    report = verify_formulation(bqm, lambda s: True)
    result = run_sa(bqm, num_reads=200, num_sweeps=500, seed=11)
    stats = distribution_stats(result["distribution"], lambda s: True, report["ground_energy"])
    assert stats["total_samples"] == 200
    assert stats["best_sample"] == report["ground_states"][0]
    assert stats["p_optimal"] > 0.9

    path = save_result(result | {"stats": stats}, tmp_path, "toy_sa")
    loaded = load_result(path)
    assert loaded["stats"] == stats
    assert set(loaded["package_versions"]) >= {"qiskit", "dimod"}
