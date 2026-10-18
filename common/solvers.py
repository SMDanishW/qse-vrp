"""Shared solvers: hand-written QAOA on Qiskit Aer, and simulated annealing (dwave-samplers, "neal").

Both return the full measured distribution as rows {"sample": {name: bit}, "count": n, "energy": E},
sorted by energy, where E is the QUBO energy of that sample (penalties included).
"""

import time
from collections.abc import Iterable

import dimod
import numpy as np
from dwave.samplers import SimulatedAnnealingSampler
from qiskit import transpile
from qiskit.circuit.library import qaoa_ansatz
from qiskit_aer import AerSimulator
from qiskit_aer.primitives import EstimatorV2, SamplerV2
from qiskit_optimization import QuadraticProgram
from scipy.optimize import minimize

# Generic hardware gate set, used only to report the circuit depth a real device would need (TQ3).
HARDWARE_BASIS = ["cx", "rz", "sx", "x"]

# scipy option that caps the number of energy evaluations, per supported gradient-free optimizer.
BUDGET_OPTION = {"COBYLA": "maxiter", "Nelder-Mead": "maxfev", "Powell": "maxfev"}


def _sorted_rows(rows: Iterable[tuple[dict[str, int], int, float]]) -> list[dict]:
    return sorted(
        ({"sample": s, "count": int(c), "energy": float(e)} for s, c, e in rows),
        key=lambda r: (r["energy"], -r["count"]),
    )


def run_qaoa(
    qp: QuadraticProgram,
    *,
    reps: int,
    initial_gammas: list[float],
    initial_betas: list[float],
    optimizer: str,
    maxiter: int,
    shots: int,
    seed_transpiler: int,
    seed_simulator: int,
) -> dict:
    """QAOA with an explicit loop, so every step can be shown in the report.

    1. QUBO -> Ising cost operator H (weighted Z and ZZ terms) plus a constant offset, then
       normalised: H_C = H / s with s = max |coefficient|, so gamma is O(1) whatever the penalty size
       (physical angle = gamma / s). Without this, gamma must be ~1/s and COBYLA's unit first step
       overshoots (docs/challenges.md).
    2. Ansatz: |+>^n, then `reps` layers of exp(-i gamma_k H_C) followed by the mixer exp(-i beta_k sum X).
    3. scipy `optimizer` minimises s <H_C> + offset (the expected QUBO energy) over (gammas, betas).
       Aer's EstimatorV2 returns the exact expectation (statevector); hardware would estimate it from shots.
       `maxiter` is a budget of energy evaluations for every optimizer (maxfev for Nelder-Mead/Powell).
    4. The optimised circuit is sampled `shots` times; each bitstring is decoded by variable name
       (Qiskit bitstrings are little-endian: qubit i is character -1-i).
    """
    if len(initial_gammas) != reps or len(initial_betas) != reps:
        raise ValueError(f"need {reps} initial gammas and betas, got {initial_gammas}, {initial_betas}")
    if optimizer not in BUDGET_OPTION:
        raise ValueError(f"unsupported optimizer {optimizer!r}; choose from {sorted(BUDGET_OPTION)}")
    names = [v.name for v in qp.variables]
    ising, offset = qp.to_ising()  # qubit i <-> qp variable i
    scale = float(np.abs(ising.coeffs).max())
    if scale == 0:
        raise ValueError("QUBO has no non-constant terms")
    cost_op = ising * (1 / scale)
    backend = AerSimulator()

    logical = qaoa_ansatz(cost_op, reps=reps)
    ansatz = transpile(logical, backend, seed_transpiler=seed_transpiler)
    observable = cost_op.apply_layout(ansatz.layout)
    measured = logical.copy()
    measured.measure_all()  # clbit i measures logical qubit i, independent of transpiler layout
    measured = transpile(measured, backend, seed_transpiler=seed_transpiler)
    hardware = transpile(logical, basis_gates=HARDWARE_BASIS, seed_transpiler=seed_transpiler)

    # Qiskit orders circuit parameters by name (all betas before gammas); bind explicitly by name.
    position = {p.name: i for i, p in enumerate(ansatz.parameters)}
    order = [position[f"γ[{k}]"] for k in range(reps)] + [position[f"β[{k}]"] for k in range(reps)]

    def bind(x: np.ndarray) -> np.ndarray:
        values = np.empty(2 * reps)
        values[order] = x
        return values

    estimator = EstimatorV2()
    history: list[float] = []

    def expected_energy(x: np.ndarray) -> float:
        e = scale * float(estimator.run([(ansatz, observable, bind(x))]).result()[0].data.evs) + offset
        history.append(e)
        return e

    start = time.perf_counter()
    opt = minimize(
        expected_energy,
        np.array(list(initial_gammas) + list(initial_betas), dtype=float),
        method=optimizer,
        options={BUDGET_OPTION[optimizer]: maxiter},
    )
    counts = (
        SamplerV2(seed=seed_simulator)
        .run([(measured, bind(opt.x))], shots=shots)
        .result()[0]
        .data.meas.get_counts()
    )
    runtime = time.perf_counter() - start

    rows = []
    for bitstring, count in counts.items():
        sample = {name: int(bitstring[-1 - i]) for i, name in enumerate(names)}
        rows.append((sample, count, qp.objective.evaluate(sample)))

    return {
        "solver": "qaoa",
        "backend": "qiskit-aer AerSimulator (EstimatorV2 exact expectation, SamplerV2 shots)",
        "n_qubits": len(names),
        "reps": reps,
        "optimizer": optimizer,
        "maxiter": maxiter,
        "cost_scale": scale,
        "initial_gammas": list(initial_gammas),
        "initial_betas": list(initial_betas),
        "optimal_gammas": opt.x[:reps].tolist(),
        "optimal_betas": opt.x[reps:].tolist(),
        "expected_energy": float(opt.fun),
        "n_evaluations": len(history),
        "optimizer_message": str(opt.message),
        "energy_history": history,
        "circuit": {
            "aer_depth": ansatz.depth(),
            "aer_ops": dict(ansatz.count_ops()),
            "hardware_basis_depth": hardware.depth(),
            "hardware_basis_ops": dict(hardware.count_ops()),
        },
        "shots": shots,
        "seeds": {"transpiler": seed_transpiler, "simulator": seed_simulator},
        "distribution": _sorted_rows(rows),
        "runtime_s": runtime,
    }


def run_sa(
    bqm: dimod.BinaryQuadraticModel, *, num_reads: int, num_sweeps: int, seed: int
) -> dict:
    """Simulated annealing (report as "neal / simulated annealing").

    Each read starts from a random bitstring and flips bits with a Metropolis rule while the inverse
    temperature beta rises over `num_sweeps` sweeps (default geometric schedule and beta range).
    """
    start = time.perf_counter()
    sampleset = SimulatedAnnealingSampler().sample(
        bqm, num_reads=num_reads, num_sweeps=num_sweeps, seed=seed
    ).aggregate()
    runtime = time.perf_counter() - start

    rows = (
        ({v: int(b) for v, b in s.items()}, n, e)
        for s, e, n in sampleset.data(["sample", "energy", "num_occurrences"])
    )
    return {
        "solver": "simulated_annealing",
        "backend": "dwave-samplers SimulatedAnnealingSampler (neal)",
        "num_reads": num_reads,
        "num_sweeps": num_sweeps,
        "seeds": {"annealer": seed},
        "distribution": _sorted_rows(rows),
        "runtime_s": runtime,
    }
