"""Tests for common/qubo_utils.py on a toy one-hot QUBO: pick exactly one of a, b, c at cost 3, 1, 2."""

import itertools

import dimod
import pytest

from common.qubo_utils import bqm_to_qp, verify_formulation

COSTS = {"a": 3.0, "b": 1.0, "c": 2.0}


def toy_bqm(penalty: float) -> dimod.BinaryQuadraticModel:
    bqm = dimod.BinaryQuadraticModel(COSTS, {}, 0.0, dimod.BINARY)
    bqm.add_linear_equality_constraint([(v, 1) for v in COSTS], penalty, -1)
    return bqm


def one_hot(bits: dict[str, int]) -> bool:
    return sum(bits.values()) == 1


def test_strong_penalty_ground_state_is_feasible_optimum() -> None:
    report = verify_formulation(toy_bqm(penalty=10.0), one_hot)
    assert report["ground_states"] == [{"a": 0, "b": 1, "c": 0}]
    assert report["ground_energy"] == 1.0  # penalty vanishes, only the cost of b remains
    assert report["n_states"] == 8 and report["n_feasible"] == 3
    assert report["gap"] > 0


def test_weak_penalty_is_rejected() -> None:
    # P = 0.5 < cheapest cost: picking nothing (energy 0.5) beats picking b (energy 1).
    with pytest.raises(ValueError, match="infeasible ground state"):
        verify_formulation(toy_bqm(penalty=0.5), one_hot)


def test_bqm_to_qp_preserves_every_energy() -> None:
    bqm = toy_bqm(penalty=10.0)
    qp = bqm_to_qp(bqm)
    assert [v.name for v in qp.variables] == list(bqm.variables)
    for bits in itertools.product((0, 1), repeat=bqm.num_variables):
        sample = dict(zip(bqm.variables, bits))
        assert qp.objective.evaluate(sample) == pytest.approx(bqm.energy(sample))
