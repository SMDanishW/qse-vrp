"""Tests for domains/vrp/problem.py on QOPTLib P-n6_1 (Stage 1 assignment and Stage 2 route QUBOs)."""

from itertools import combinations
from pathlib import Path

import dimod
import pytest

from common.qubo_utils import verify_formulation
from domains.vrp.problem import (
    Solution,
    build_bqm,
    build_qubo,
    build_route_bqm,
    cluster_cost,
    decode,
    decode_route,
    is_feasible,
    load_instance,
    objective,
    penalty_bound,
    route_penalty_bound,
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


# ---------------------------------------------------------------- Stage 2

P2 = route_penalty_bound(INSTANCE)
PENALTIES2 = {"one_position": P2, "one_customer": P2}


def test_route_qubo_ground_states_are_optimal_tour_and_its_reverse() -> None:
    for route, best, cost in [((1, 2, 5), {(1, 5, 2), (2, 5, 1)}, 45), ((3, 4), {(3, 4), (4, 3)}, 73)]:
        bqm = build_route_bqm(INSTANCE, route, PENALTIES2)
        assert bqm.num_variables == len(route) ** 2
        report = verify_formulation(bqm, lambda s, route=route: decode_route(s, route) is not None)
        assert {decode_route(s, route) for s in report["ground_states"]} == best
        assert report["ground_energy"] == cost  # penalties vanish on a valid tour
    # Chained optimum = QOPTLib reference: 45 + 73 = 118.
    assert objective(Solution(INSTANCE, ((1, 5, 2), (4, 3)))) == 118


def test_route_penalty_bound_holds_for_every_possible_route() -> None:
    for k in (2, 3):  # every vehicle load allowed by Stage 1
        for route in combinations(INSTANCE.customers, k):
            verify_formulation(
                build_route_bqm(INSTANCE, route, PENALTIES2),
                lambda s, route=route: decode_route(s, route) is not None,
            )


def test_route_bqm_coefficients_match_readme_derivation() -> None:
    # domains/vrp/README.md, Stage 2 step 4, for route (1, 2, 5) with m = 3.
    pa, pb = 7.0, 11.0
    route, m, d = (1, 2, 5), 3, INSTANCE.dist
    bqm = build_route_bqm(INSTANCE, route, {"one_position": pa, "one_customer": pb})
    assert bqm.offset == m * (pa + pb)
    for i in route:
        for t in range(m):
            assert bqm.linear[f"y_{i}_{t}"] == -pa - pb + (d[0][i] if t == 0 else 0) + (d[i][0] if t == m - 1 else 0)
            for s in range(t + 1, m):
                assert bqm.quadratic[(f"y_{i}_{t}", f"y_{i}_{s}")] == 2 * pa
        for j in route:
            if j > i:
                for t in range(m):
                    assert bqm.quadratic[(f"y_{i}_{t}", f"y_{j}_{t}")] == 2 * pb
            if j != i:
                for t in range(m - 1):
                    assert bqm.quadratic[(f"y_{i}_{t}", f"y_{j}_{t + 1}")] == d[i][j]


def test_decode_route_rejects_non_permutations() -> None:
    route = (3, 4)
    assert decode_route({"y_3_0": 1, "y_4_0": 0, "y_3_1": 0, "y_4_1": 1}, route) == (3, 4)
    assert decode_route({"y_3_0": 1, "y_4_0": 1, "y_3_1": 0, "y_4_1": 0}, route) is None  # two at t=0
    assert decode_route({"y_3_0": 1, "y_4_0": 0, "y_3_1": 1, "y_4_1": 0}, route) is None  # 3 visited twice
