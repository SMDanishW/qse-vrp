# CLAUDE.md — M2 VRP (Quantum Optimization Group Project)

## Who I am and what this repo is
- Course: CT30A1200 Fundamentals of Quantum Software Engineering, group project
  "Quantum Optimization Across Supply Chain, Logistics, and Industrial Scheduling: A QAOA Study".
- I am **M2** (logistics owner + technical lead). This repo is **my VRP work only**. I build everything
  in it myself, including the shared helpers in `common/`. Do not write code for other members' domains.
- Team codes (use these, not names): M1 supply chain, M2 VRP (me), M3 scheduling + report lead, M4 integration.

Reference files in this repo (read on demand, not all at once)
agent-identity.md: the full assistant identity and project context (role, scope rules, dataset criteria, VRP approach, shared conventions). Read it at the start of a new task if anything here is unclear.
`Project instructions/Technical_Project_Group_A.pdf`: the official course project brief. It is the authority on scope, objectives, TQ1–TQ3 and deliverables. Note: it names students; refer to them only by code (M1–M4).
slides/: the course lecture slides. When explaining a quantum concept or choosing notation, check the slides first and match their terminology and symbols so the report stays consistent with the course. Cite the slide file when an explanation relies on it. Open individual files only when needed.
  The slides cover QSE basics only: QUBO, penalty, ansatz and mixer appear nowhere; QAOA only in passing
  (`Quantum_Lecture 2.pdf` p16, `Lecture 6.pdf` p43), Ising once (`Lecture 6.pdf` p37). For QUBO/QAOA
  notation use external sources (e.g. Lucas 2014, "Ising formulations of many NP problems"; Qiskit docs) and cite them.
slides/ and `Project instructions/` are git-ignored (course material; the brief contains real names).
Precedence when they disagree: the project brief wins on scope and deliverables; this CLAUDE.md wins on implementation decisions made since (e.g. I build common/ myself, dwave.samplers instead of neal, Qiskit 2.x V2 primitives); agent-identity.md is background. Point out any conflict you notice.

## How to explain things to me
- I have a software engineering and AI/ML background but **no quantum background**.
- The first time a quantum term appears (qubit, superposition, measurement, Hamiltonian, Ising, QUBO,
  QAOA, ansatz, mixer, penalty, annealing, shots, transpile, etc.), explain it in plain language,
  intuition first, then the math (LaTeX).
- Relate ideas to SE/ML: QUBO = loss function over 0/1 variables; penalty = regularizer/soft constraint;
  QAOA = small parameterized model whose angles (γ, β) are trained by a classical optimizer;
  p (reps) = number of layers; shots = sample size.
- Be concise and technical. If a request is ambiguous, ask one clarifying question instead of guessing.

## Scope rules (hard)
- QUBO instances of about **8–12 binary variables per quantum run**.
- **Simulators only**: Qiskit Aer (QAOA) and D-Wave simulated annealing (dwave-samplers). Runs locally on CPU.
- **Not allowed**: classical benchmarking or classical-solver comparisons, real quantum hardware,
  new algorithms, industrial-scale instances. If I ask for something out of scope, say so.
- Technical questions to tie all analysis to:
  - TQ1 = correct QUBO formulation
  - TQ2 = QAOA / annealing implementation
  - TQ3 = practical challenges (circuit depth, parameter tuning, encoding, simulator limits)

## VRP approach: hybrid "cluster first, route second"
Instance: QOPTLib `data/vrp/P-n6_1.vrp`: 1 depot, 5 customers, K = 2 vehicles, unit demand, C = 3,
TSPLIB-rounded EUC_2D distances. Conventions, verdict and reference check: `data/vrp/README.md`.

**Stage 1 — assignment QUBO**
- `x[i,v] = 1` if customer i is served by vehicle v.
- Cost: sum of intra-vehicle pairwise distances, $\sum_v \sum_{i<j} d_{ij}\, x_{i,v} x_{j,v}$.
- Penalties: one vehicle per customer $P_1 \sum_i (\sum_v x_{i,v} - 1)^2$;
  capacity without slack bits as a count target $P_2 \sum_v (\sum_i x_{i,v} - 2.5)^2$
  (equal penalty for loads 2 and 3, larger otherwise, so it encodes C = 3 exactly for 5 customers).
- Fix customer 1 to vehicle 0 to break symmetry (5 customers × 2 vehicles = 10 vars → 8 after fixing).

**Stage 2 — per-route TSP QUBO**
- `y[i,t] = 1` if customer i is visited at position t; depot fixed at start and end.
- m customers → m² vars (P-n6_1 routes: 3 customers → 9 vars, 2 customers → 4 vars).
- Cost: depot→first + consecutive legs + last→depot.
- Penalties: one position per customer, one customer per position.
- Stage 1's decoded assignment feeds Stage 2 (one TSP per vehicle).

**Optional TQ3 demo**: monolithic VRP QUBO solved with simulated annealing only, to show why QAOA on
Aer cannot handle it (statevector memory grows as 2^n).

## Mandatory verification rule
Before running QAOA on any QUBO, enumerate all 2^n bitstrings (n ≤ 12) and confirm the lowest-energy
state is the feasible optimum. This is a **formulation check**, not a classical benchmark, and is never
reported as a comparison.

## Repo layout
```
common/
  qubo_utils.py   # verify_formulation (2^n brute-force check), bqm_to_qp; penalties via dimod add_linear_equality_constraint
  solvers.py      # run_qaoa(...), run_sa(...)
  results.py      # save/load result JSON
domains/vrp/
  problem.py      # load_instance, build_qubo, decode, is_feasible, objective
  run.py          # CLI entry: python -m domains.vrp.run --config configs/vrp.yaml
  sweep.py        # task 8 QAOA study: python -m domains.vrp.sweep --config configs/vrp.yaml
  README.md       # formulation, derivation, parameters, how to reproduce
configs/vrp.yaml
data/  results/  notebooks/
docs/challenges.md  # TQ3 running log
tests/              # pytest; test_env.py checks installed versions == pins
pyproject.toml      # pytest config only (pythonpath = repo root)
requirements.txt    # pinned (from pip freeze)
```
Modules are added with their first real content (no empty stubs); empty dirs carry a `.gitkeep`.
Env: M2 uses conda `qsenv314` (Python 3.14.8) at `D:/anaconda/envs/qsenv314`.

## problem.py interface (keep exactly)
- `load_instance(path) -> Instance`
- `build_qubo(instance, penalties) -> QuadraticProgram` (built as a dimod BQM, converted with `common.qubo_utils.bqm_to_qp`)
- `decode(sample: dict[str, int], instance) -> Solution` (instance needed for K and capacity; `Solution` carries it)
- `is_feasible(solution) -> bool`
- `objective(solution) -> float` (true route cost, without penalties)

## Coding conventions
- Python 3.12+ (see Environment), type hints, short docstrings, complete runnable files.
- Variable names like `x_3_1` (customer 3, vehicle 1) and `y_2_0` (customer 2, position 0).
- **Decode by variable name, never by position.** Qiskit bitstrings are little-endian:
  qubit 0 is the **rightmost** bit.
- Fixed seeds for transpiler, simulator, optimizer and annealer; all seeds stored in the YAML config.
- Never invent library APIs. Qiskit 2.x removed the V1 primitives; use V2 primitives
  (`qiskit_aer.primitives.SamplerV2` / `EstimatorV2`). If unsure about an API, check the installed
  version (`pip show <pkg>`) or ask me for `pip freeze` output.
- Prefer a transparent hand-written QAOA loop (ansatz from the QUBO's Ising operator + Aer primitive +
  `scipy.optimize.minimize`) over black-box wrappers, so every step can be explained in the report.
  `qiskit-optimization` is used for `QuadraticProgram` and QUBO/Ising conversion; it is community-maintained
  and no longer officially supported by IBM, so keep the dependency thin.
- Simulated annealing: `from dwave.samplers import SimulatedAnnealingSampler`
  (`dwave-neal` / `import neal` is deprecated). Report it as "neal / simulated annealing".

## Every run saves a JSON result with
domain, instance, n_vars, solver, backend, reps (p), optimizer, maxiter, initial parameters,
shots or num_reads, seeds, penalty weights, best bitstring, energy, objective, feasible,
probability of the optimal bitstring, probability of any feasible bitstring, runtime, package versions.

## Results and honesty
- Low-depth QAOA often finds the optimum with low probability. Always report the **full measurement
  distribution** and the **feasible fraction**, not just the best sample.
- Document every penalty weight with a short justification; run a small sweep where useful.
- Keep a running `docs/challenges.md` log (depth, parameter tuning, encoding, simulator limits) for TQ3.

## Status / tasks (tick when done; update this list, not chat)
1. [x] Environment and pinned `requirements.txt`.
2. [x] Repo skeleton (layout above).
3. [x] `common/qubo_utils.py`: `verify_formulation` brute-force check, `bqm_to_qp` conversion (penalties: dimod built-in, no wrapper).
4. [x] Dataset: QOPTLib VRP, verdict "suitable with assumptions"; instance P-n6_1 (`data/vrp/README.md`).
5. [x] Stage 1 QUBO: derivation in `domains/vrp/README.md`, `problem.py`, tests (8 vars, P = 162, ground state {1,2,5}/{3,4}).
6. [x] `common/solvers.py` (`run_qaoa` hand-written loop, `run_sa`) and `common/results.py` (`distribution_stats`, `save_result`, `load_result`).
7. [x] Stage 2 route QUBO (`build_route_bqm`, `decode_route`, P = 102) and chaining in `domains/vrp/run.py` + `configs/vrp.yaml`; chain reaches 118.
8. [x] QAOA study: `domains/vrp/sweep.py`, 67 runs in `results/sweep/` (summary.csv, figures); cost operator normalised in `run_qaoa`; findings in `domains/vrp/README.md`.
9. [ ] `docs/challenges.md` for TQ3, README derivation, report section for M3, slides.

Open items: none. M2 runs `qsenv314` (conda, Python 3.14.8); the old 3.12 `qsenv` is removed.

## Environment
- `requirements.txt` is the full pinned `pip freeze` (2026-10-18). It is the single source of truth;
  regenerate it with `pip freeze > requirements.txt` after any install and update the list below.
- Python: pins resolve on CPython 3.12, 3.13 and 3.14 (Windows, checked 2026-10-18). Machine default is 3.14.3.
- Key pins: qiskit 2.6.0, qiskit-aer 0.17.2, qiskit-optimization 0.7.0, dimod 0.12.22,
  dwave-samplers 1.8.0, numpy 2.5.4, scipy 1.18.1, PyYAML 6.0.3, matplotlib 3.11.2, pytest 9.1.1.
- `docplex` is pulled in by qiskit-optimization (sdist only); not used directly.
- Windows Smart App Control is ON (enforce) on M2's machine. It blocked dimod's cp312 `.pyd` in `qsenv`
  (CodeIntegrity events 3033/3077, 2026-10-18); the cp314 wheels in `.venv` load and all tests pass.

## Commands
```
conda activate qsenv314                              # M2's env (conda, Python 3.14); others may use a venv:
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m domains.vrp.run --config configs/vrp.yaml
pytest -q
```

# context-mode — MANDATORY routing rules

You have context-mode MCP tools available. These rules are NOT optional — they protect your context window from flooding. A single unrouted command can dump 56 KB into context and waste the entire session.

## BLOCKED commands — do NOT attempt these

### curl / wget — BLOCKED
Any Bash command containing `curl` or `wget` is intercepted and replaced with an error message. Do NOT retry.
Instead use:
- `ctx_fetch_and_index(url, source)` to fetch and index web pages
- `ctx_execute(language: "javascript", code: "const r = await fetch(...)")` to run HTTP calls in sandbox

### Inline HTTP — BLOCKED
Any Bash command containing `fetch('http`, `requests.get(`, `requests.post(`, `http.get(`, or `http.request(` is intercepted and replaced with an error message. Do NOT retry with Bash.
Instead use:
- `ctx_execute(language, code)` to run HTTP calls in sandbox — only stdout enters context

### WebFetch — BLOCKED
WebFetch calls are denied entirely. The URL is extracted and you are told to use `ctx_fetch_and_index` instead.
Instead use:
- `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` to query the indexed content

## REDIRECTED tools — use sandbox equivalents

### Bash (>20 lines output)
Bash is ONLY for: `git`, `mkdir`, `rm`, `mv`, `cd`, `ls`, `npm install`, `pip install`, and other short-output commands.
For everything else, use:
- `ctx_batch_execute(commands, queries)` — run multiple commands + search in ONE call
- `ctx_execute(language: "shell", code: "...")` — run in sandbox, only stdout enters context

### Read (for analysis)
If you are reading a file to **Edit** it → Read is correct (Edit needs content in context).
If you are reading to **analyze, explore, or summarize** → use `ctx_execute_file(path, language, code)` instead. Only your printed summary enters context. The raw file content stays in the sandbox.

### Grep (large results)
Grep results can flood context. Use `ctx_execute(language: "shell", code: "grep ...")` to run searches in sandbox. Only your printed summary enters context.

## Tool selection hierarchy

1. **GATHER**: `ctx_batch_execute(commands, queries)` — Primary tool. Runs all commands, auto-indexes output, returns search results. ONE call replaces 30+ individual calls.
2. **FOLLOW-UP**: `ctx_search(queries: ["q1", "q2", ...])` — Query indexed content. Pass ALL questions as array in ONE call.
3. **PROCESSING**: `ctx_execute(language, code)` | `ctx_execute_file(path, language, code)` — Sandbox execution. Only stdout enters context.
4. **WEB**: `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` — Fetch, chunk, index, query. Raw HTML never enters context.
5. **INDEX**: `ctx_index(content, source)` — Store content in FTS5 knowledge base for later search.

## Subagent routing

When spawning subagents (Agent/Task tool), the routing block is automatically injected into their prompt. Bash-type subagents are upgraded to general-purpose so they have access to MCP tools. You do NOT need to manually instruct subagents about context-mode.

## Output constraints

- Keep responses under 500 words.
- Write artifacts (code, configs, PRDs) to FILES — never return them as inline text. Return only: file path + 1-line description.
- When indexing content, use descriptive source labels so others can `ctx_search(source: "label")` later.

## ctx commands

| Command | Action |
|---------|--------|
| `ctx stats` | Call the `ctx_stats` MCP tool and display the full output verbatim |
| `ctx doctor` | Call the `ctx_doctor` MCP tool, run the returned shell command, display as checklist |
| `ctx upgrade` | Call the `ctx_upgrade` MCP tool, run the returned shell command, display as checklist |
