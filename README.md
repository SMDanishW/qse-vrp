# QAOA study: logistics domain (small vehicle routing problem)

Part of the CT30A1200 *Fundamentals of Quantum Software Engineering* group project
"Quantum Optimization Across Supply Chain, Logistics, and Industrial Scheduling: A QAOA Study".
This repository is the **logistics domain (M2)**: a small capacitated vehicle routing problem (CVRP)
formulated as QUBOs and solved with QAOA on Qiskit Aer and with simulated annealing (D-Wave `neal`
successor `dwave-samplers`). It also contains the shared helpers in `common/`, which M1, M3 and M4 may
reuse (see [For group members](#for-group-members)).

Team codes: M1 supply chain, M2 logistics/VRP and technical lead, M3 scheduling and report lead,
M4 integration.

## Result in one paragraph
Instance QOPTLib P-n6_1 (depot, 5 customers, 2 vehicles, capacity 3). The problem is decomposed
(cluster first, route second) into an 8-qubit assignment QUBO and one route QUBO per vehicle (9 and
4 qubits). Every QUBO is checked by enumerating all bitstrings before any quantum run. Both QAOA
(p = 4, Powell) and simulated annealing return the optimal routes 0-1-5-2-0 and 0-4-3-0, cost 118.
QAOA puts 5.2% (assignment) and 17.7% (9-qubit route) of its shots on an optimal bitstring, 13–45×
above uniform sampling, but most shots remain non-optimal; normalising the cost Hamiltonian was the
single largest improvement. Full write-up: [docs/report_vrp.md](docs/report_vrp.md).

## Where each deliverable is
| Brief deliverable | Location |
|---|---|
| Problem formulation | [docs/report_vrp.md](docs/report_vrp.md) §1–2, [data/vrp/README.md](data/vrp/README.md) (dataset, conventions, verdict) |
| QUBO derivation (TQ1) | [domains/vrp/README.md](domains/vrp/README.md) (step-by-step, coefficient tables), report §3 |
| Simulator implementation (TQ2) | [common/solvers.py](common/solvers.py), [domains/vrp/problem.py](domains/vrp/problem.py), [domains/vrp/run.py](domains/vrp/run.py) |
| Results and objective values | report §5, `results/` (JSON per run), [results/sweep/summary.csv](results/sweep/summary.csv), figures in `results/sweep/` |
| QAOA / annealing parameter documentation | [configs/vrp.yaml](configs/vrp.yaml) (all settings and seeds, with reasons), report §4.3 |
| Practical challenges (TQ3) | report §6, running log [docs/challenges.md](docs/challenges.md) |
| Reproducible structure | this README, `tests/`, pinned [requirements.txt](requirements.txt) |
| Walk-through of each implementation | [notebooks/](notebooks/) (start with `00_overview.ipynb`) |

## Quick start
Python 3.12–3.14 (developed on 3.14.8, Windows 11, CPU only). No quantum hardware or IBM account needed.

```
conda create -n qsenv314 python=3.14 -y && conda activate qsenv314   # or: python -m venv .venv
pip install -r requirements.txt
python -m pytest -q                                      # 21 tests, includes every formulation check
python -m domains.vrp.run --config configs/vrp.yaml      # full pipeline, ~20 s, writes results/
python -m domains.vrp.sweep --config configs/vrp.yaml    # 67-run QAOA study, ~5 min, writes results/sweep/
```
Run from the repository root. Seeds are fixed in the config, so the numbers reproduce exactly.

> Windows 11 with Smart App Control on blocked a compiled `dimod` file built for Python 3.12; the
> Python 3.14 builds load. If `import dimod` fails with "An Application Control policy has blocked this
> file", use Python 3.14.

## Repository layout
```
common/                 shared, domain-independent
  qubo_utils.py         verify_formulation (enumerate all 2^n bitstrings), bqm_to_qp
  solvers.py            run_qaoa (explicit QAOA loop on Aer), run_sa (simulated annealing)
  results.py            distribution_stats, save_result / load_result (JSON + package versions)
domains/vrp/
  problem.py            instance loading, Stage 1 and Stage 2 QUBOs, decode, feasibility, objective
  run.py                pipeline: Stage 1 -> Stage 2 per vehicle -> routes
  sweep.py              QAOA parameter study and figures
  README.md             derivations, penalty justification, study findings
configs/vrp.yaml        every run setting and seed
data/vrp/               QOPTLib VRP instances + dataset README
results/                run outputs (one JSON per solver run, chain summaries, sweep/)
docs/                   report_vrp.md (report section), challenges.md (TQ3 log)
notebooks/              00–07: one notebook per implementation step (what, why, resources, expected results, self-checks)
tests/                  pytest suite
```

## How the pipeline works
1. `load_instance` reads the `.vrp` file and builds the TSPLIB-rounded distance matrix.
2. Stage 1 builds the assignment QUBO, `verify_formulation` enumerates all 256 bitstrings and stops
   the run if the lowest-energy bitstring is not a feasible optimum, then the solver runs.
3. The lowest-energy feasible sample is decoded into one customer group per vehicle.
4. Stage 2 repeats the check and solve for each group's route QUBO.
5. Routes are combined; `objective` gives the total distance. Every solver run (full measured
   distribution, settings, seeds, formulation check, statistics, package versions) and the chain
   summary are written to `results/` as JSON. Existing files are never overwritten.

## For group members
The pieces below are domain-independent and can be reused for supply chain (M1) and scheduling (M3).
If you use them, results from all three domains share one format, which makes integration (M4) and the
cross-domain discussion straightforward.

**Domain module contract** (`domains/<domain>/problem.py`):
| Function | Purpose |
|---|---|
| `load_instance(path) -> Instance` | parse the data file |
| `build_qubo(instance, penalties) -> QuadraticProgram` | the QUBO; build it as a dimod BQM and convert with `common.qubo_utils.bqm_to_qp` so Qiskit and dimod see the same model |
| `decode(sample, instance) -> Solution` | read a `{variable name: bit}` sample. **Changed from the original draft:** `instance` is now a parameter, because feasibility needs instance data (capacity, sizes) |
| `is_feasible(solution) -> bool` | constraint check |
| `objective(solution) -> float` | true objective, without penalties |

**Shared helpers:**
- `verify_formulation(bqm, is_feasible)`: enumerates all $2^n$ bitstrings ($n \le 20$) and raises if a
  lowest-energy bitstring is infeasible. Run it on every QUBO before QAOA; it also reports the energy gap
  that tells you whether penalties are strong enough.
- `run_qaoa(qp, reps, initial_gammas, initial_betas, optimizer, maxiter, shots, seed_transpiler, seed_simulator)`:
  optimizers `COBYLA`, `Nelder-Mead`, `Powell`; `maxiter` is a budget of energy evaluations. The cost
  Hamiltonian is normalised internally, so initial γ around 1 works for any penalty size.
- `run_sa(bqm, num_reads, num_sweeps, seed)`.
- `distribution_stats(distribution, is_feasible, ground_energy)`: p_optimal, p_feasible, best and most likely sample.
- `save_result(record, out_dir, name)`: adds timestamp, Python and package versions.

**Conventions:**
- Variable names encode meaning (`x_3_1` = customer 3 on vehicle 1); decode by name, never by position.
  Qiskit bitstrings are little-endian (qubit 0 is the rightmost character); `run_qaoa` handles this.
- All settings and seeds in `configs/<domain>.yaml`; no hard-coded seeds.
- Report the full distribution, p_optimal and p_feasible, not only the best sample. With 8–12 qubits,
  the best of a few thousand shots is close to enumeration and says little about QAOA.
- Justify every penalty weight; `verify_formulation` gives the evidence.

**Lessons that may save you time:**
- Without normalisation, large penalties force γ to about 0.01 and COBYLA's first step (1.0) overshoots;
  we saw QAOA fall below uniform sampling until the Hamiltonian was normalised.
- The initial γ changed p_optimal by up to 5× in our study; try a few starting points.
- Qiskit 2.x: use `qaoa_ansatz` (the `QAOAAnsatz` class is deprecated since 2.1) and the V2 primitives.
  Circuit parameters are ordered alphabetically (all β before all γ); bind them by name.

## Scope (from the project brief)
QUBOs of about 8–12 binary variables per quantum run, simulators only (Qiskit Aer, D-Wave `neal`),
no real hardware, no classical-solver benchmarking, no new algorithms. The exhaustive enumeration
above is a formulation check, not a benchmark.

## Data and licences
QOPTLib: E. Osaba, E. Villar-Rodriguez, Springer 2023, arXiv:2404.15852 (paper CC BY 4.0), data
doi:10.17632/h32z9kcz3s.1. Only `data/vrp/` is committed. Course material (slides, brief) is not
included in the repository.
