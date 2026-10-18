"""Tests for domains/vrp/problem.py on QOPTLib P-n6_1 (Stage 1 assignment QUBO)."""

from pathlib import Path

import dimod
import pytest

from common.qubo_utils import verify_formulation
from domains.vrp.problem import (
    Solution,
    build_bqm,
    build_qubo,
    cluster_cost,
    decode,
    is_feasible,
    load_instance,
    objective,
    penalty_bound,
)

INSTANCE = load_instance(Path(__file__).resolve().parents[1] / "data/vrp/P-n6_1.vrp")
P = penalty_bound(INSTANCE)
PENALTIES = {"one_vehicle": P, "capacity": P}


def feasible(sample: dict[str, int]) -> bool:
    return is_feasible(decode(sample, INSTANCE))


def test_reference_solution_cost_matches_qoptlib() -> None:
    # Solutions VRP.txt: [[0,1],[1,5],[5,2],[2,0]], [[0,4],[4,3],[3,0]] - 118
    reference = Solution(INSTANCE, ((1, 5, 2), (4, 3)))
    assert is_feasible(reference)
    assert objective(reference) == 118


def test_stage1_qubo_size() -> None:
    assert build_bqm(INSTANCE, PENALTIES).num_variables == 8  # 5 customers x 2 vehicles, minus fixed customer
    assert build_qubo(INSTANCE, PENALTIES).get_num_vars() == 8


def test_brute_force_ground_state_is_feasible_optimum() -> None:
    report = verify_formulation(build_bqm(INSTANCE, PENALTIES), feasible)
    assert [decode(s, INSTANCE).routes for s in report["ground_states"]] == [((1, 2, 5), (3, 4))]
    assert report["n_feasible"] == 10  # C(4,1) + C(4,2): the fixed customer's vehicle gets 2 or 3


def test_feasible_energy_is_cluster_cost_plus_constant() -> None:
    # Derivation check: for feasible x the one-vehicle penalty is 0 and the capacity penalty is
    # P * ((2 - 2.5)^2 + (3 - 2.5)^2) = 0.5 P, so E(x) = cluster_cost(x) + 0.5 P exactly.
    bqm = build_bqm(INSTANCE, PENALTIES)
    for sample, energy in dimod.ExactSolver().sample(bqm).data(["sample", "energy"]):
        if feasible(sample):
            assert energy == pytest.approx(cluster_cost(decode(sample, INSTANCE)) + 0.5 * P)


def test_bqm_coefficients_match_readme_derivation() -> None:
    # domains/vrp/README.md, Stage 1 step 4 (after fixing customer 1 to vehicle 0).
    p1, p2 = 7.0, 11.0  # distinct weights so a swapped penalty would show up
    bqm = build_bqm(INSTANCE, {"one_vehicle": p1, "capacity": p2})
    d, free = INSTANCE.dist, range(2, 6)
    assert bqm.offset == 4 * p1 + 8.5 * p2
    for j in free:
        assert bqm.linear[f"x_{j}_0"] == d[1][j] - p1 - 2 * p2
        assert bqm.linear[f"x_{j}_1"] == -p1 - 4 * p2
        assert bqm.quadratic[(f"x_{j}_0", f"x_{j}_1")] == 2 * p1
        for k in free:
            if k > j:
                for v in (0, 1):
                    assert bqm.quadratic[(f"x_{j}_{v}", f"x_{k}_{v}")] == d[j][k] + 2 * p2


def test_double_assignment_is_infeasible() -> None:
    assert not is_feasible(Solution(INSTANCE, ((1, 2, 5), (2, 3, 4))))
