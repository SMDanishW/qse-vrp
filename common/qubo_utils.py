"""Shared QUBO helpers: brute-force formulation check and BQM -> QuadraticProgram conversion.

QUBOs are built as dimod BQMs. Penalties use dimod's own
``BinaryQuadraticModel.add_linear_equality_constraint(terms, P, C)``, which adds
P * (sum_i a_i x_i + C)^2 to the model:
    one-hot (exactly one of xs):        terms=[(x, 1) for x in xs],        C = -1
    weighted target (sum_i q_i x_i = T): terms=[(x, q_i) for x, q_i in ...], C = -T
"""

from collections.abc import Callable
from typing import Any

import dimod
from qiskit_optimization import QuadraticProgram

# ponytail: ExactSolver keeps all 2^n states in memory; 2^20 is ~1M rows, far above the 12-var scope.
MAX_BRUTE_FORCE_VARS = 20


def bqm_to_qp(bqm: dimod.BinaryQuadraticModel) -> QuadraticProgram:
    """Copy a BINARY BQM into an unconstrained minimization QuadraticProgram, keeping variable names."""
    if bqm.vartype is not dimod.BINARY:
        raise ValueError(f"expected a BINARY BQM, got {bqm.vartype}")
    qp = QuadraticProgram()
    for v in bqm.variables:
        qp.binary_var(v)
    qp.minimize(
        constant=float(bqm.offset),
        linear={v: float(b) for v, b in bqm.linear.items()},
        quadratic={(u, v): float(b) for (u, v), b in bqm.quadratic.items()},
    )
    return qp


def verify_formulation(
    bqm: dimod.BinaryQuadraticModel,
    is_feasible: Callable[[dict[str, int]], bool],
) -> dict[str, Any]:
    """Enumerate all 2^n states and check that every lowest-energy state is feasible.

    Formulation check only, never reported as a benchmark. Raises ValueError if no state is
    feasible or any ground state is infeasible. Returns a summary for the docs; ``gap`` > 0 means
    the cheapest infeasible state costs more than the best feasible one (penalties strong enough).
    """
    n = bqm.num_variables
    if n > MAX_BRUTE_FORCE_VARS:
        raise ValueError(f"{n} variables is too many to enumerate (limit {MAX_BRUTE_FORCE_VARS})")

    samples = dimod.ExactSolver().sample(bqm)
    feasible: list[float] = []
    infeasible: list[float] = []
    for sample, energy in samples.data(["sample", "energy"]):
        bits = {v: int(b) for v, b in sample.items()}
        (feasible if is_feasible(bits) else infeasible).append(float(energy))
    if not feasible:
        raise ValueError("no feasible state exists for this QUBO")

    ground = [
        ({v: int(b) for v, b in s.items()}, float(e))
        for s, e in samples.lowest().data(["sample", "energy"])
    ]
    bad = [(s, e) for s, e in ground if not is_feasible(s)]
    if bad:
        raise ValueError(
            f"infeasible ground state(s) {bad}; best feasible energy {min(feasible)}. "
            "Penalty weights are too small or the formulation is wrong."
        )

    best_infeasible = min(infeasible) if infeasible else None
    return {
        "n_vars": n,
        "n_states": len(samples),
        "n_feasible": len(feasible),
        "ground_energy": ground[0][1],
        "ground_states": [s for s, _ in ground],
        "best_feasible_energy": min(feasible),
        "best_infeasible_energy": best_infeasible,
        "gap": None if best_infeasible is None else best_infeasible - min(feasible),
    }
