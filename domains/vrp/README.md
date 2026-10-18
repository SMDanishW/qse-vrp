# VRP domain (M2): cluster first, route second

Instance: QOPTLib P-n6_1 (`data/vrp/P-n6_1.vrp`; conventions and dataset verdict in `data/vrp/README.md`).
Depot 0, customers $i \in \{1,\dots,5\}$, $K = 2$ vehicles, unit demand, capacity $C = 3$,
distances $d_{ij}$ = TSPLIB-rounded Euclidean (integers).

| | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| **0** | 0 | 19 | 10 | 18 | 34 | 13 |
| **1** | 19 | 0 | 16 | 37 | 51 | 10 |
| **2** | 10 | 16 | 0 | 24 | 43 | 6 |
| **3** | 18 | 37 | 24 | 0 | 21 | 30 |
| **4** | 34 | 51 | 43 | 21 | 0 | 47 |
| **5** | 13 | 10 | 6 | 30 | 47 | 0 |

Code: `problem.py`. Tests: `tests/test_vrp_problem.py`.

## Stage 1: assignment QUBO (TQ1)

**Idea.** Decide which vehicle serves which customer, ignoring visit order. Customers that are close
to each other should share a vehicle, so the cost is the total distance between customers on the same
vehicle. Visit order is decided in Stage 2.

### Step 1: variables
$x_{i,v} \in \{0,1\}$, equal to 1 if customer $i$ is served by vehicle $v \in \{0,1\}$. Code name `x_i_v`.
$5 \times 2 = 10$ variables.

### Step 2: cost
$$
H_\text{cost} = \sum_{v} \sum_{i<j} d_{ij}\, x_{i,v}\, x_{j,v}
$$
The product $x_{i,v} x_{j,v}$ is 1 only when both customers ride vehicle $v$.

### Step 3: constraints as penalties
A QUBO has no hard constraints, so each rule becomes a squared term that is 0 when the rule holds
and positive otherwise (like a regularizer in a loss).

*One vehicle per customer:*
$$
H_1 = P_1 \sum_i \Big(\sum_v x_{i,v} - 1\Big)^2
$$

*Capacity, without slack bits.* With $K = 2$, $n = 5$, $C = 3$, every vehicle must serve 2 or 3 customers
(if one serves $\le 1$ the other serves $\ge 4 > C$). Target the midpoint $n/K = 2.5$:
$$
H_2 = P_2 \sum_v \Big(\sum_i x_{i,v} - 2.5\Big)^2
$$
Loads 2 and 3 both give $0.25$; loads 1 and 4 give $2.25$; 0 and 5 give $6.25$. So $H_2$ is minimal
exactly on the allowed loads, and the usual inequality encoding (extra binary slack variables) is not
needed. This works because $C = \lceil n/2 \rceil$; `problem.py` refuses other $K$, $C$ combinations.
For any feasible assignment $H_2 = P_2 (0.25 + 0.25) = 0.5 P_2$, a constant.

$$
E(x) = H_\text{cost} + H_1 + H_2
$$

### Step 4: expand into QUBO coefficients
Using $x^2 = x$ for binary $x$:

$$(x_{i,0} + x_{i,1} - 1)^2 = -x_{i,0} - x_{i,1} + 2x_{i,0}x_{i,1} + 1$$

$$\Big(\sum_i x_{i,v} - 2.5\Big)^2 = -4\sum_i x_{i,v} + 2\sum_{i<j} x_{i,v}x_{j,v} + 6.25$$

Collected over 10 variables:

| Term | Coefficient |
|---|---|
| $x_{i,v}$ | $-P_1 - 4P_2$ |
| $x_{i,v}\,x_{j,v}$ (same vehicle, $i<j$) | $d_{ij} + 2P_2$ |
| $x_{i,0}\,x_{i,1}$ (same customer) | $2P_1$ |
| constant | $5P_1 + 12.5P_2$ |

### Step 5: break symmetry
Swapping the labels of vehicle 0 and 1 gives the same solution, so every answer appears twice.
Fix customer 1 to vehicle 0: substitute $x_{1,0} = 1$, $x_{1,1} = 0$. This leaves **8 variables**
($j \in \{2,3,4,5\}$):

| Term | Coefficient |
|---|---|
| $x_{j,0}$ | $d_{1j} - P_1 - 2P_2$ |
| $x_{j,1}$ | $-P_1 - 4P_2$ |
| $x_{j,v}\,x_{k,v}$ ($j<k$) | $d_{jk} + 2P_2$ |
| $x_{j,0}\,x_{j,1}$ | $2P_1$ |
| constant | $4P_1 + 8.5P_2$ |

16 couplings in total (6 per vehicle plus 4 same-customer). `test_bqm_coefficients_match_readme_derivation`
checks this table against the built model.

### Penalty weights
$P_1 = P_2 = 162$ = largest total distance from one customer to all others (customer 4:
$51+43+21+47$). Moving, dropping or duplicating one customer changes $H_\text{cost}$ by at most this,
so any single-customer violation costs more than it saves. This is a sufficient bound, not a tight
one: the brute-force check already passes at $P = 40$ and fails at $P = 20$. Large penalties make
cost differences small relative to the energy range, which may hurt QAOA (TQ3), so a penalty sweep
follows in task 8.

### Brute-force formulation check (mandatory before QAOA)
`verify_formulation` enumerates all $2^8 = 256$ states with $P_1 = P_2 = 162$:
- 10 feasible states (vehicle 0 gets customer 1 plus 1 or 2 of the other 4: $4 + 6$).
- Unique ground state: vehicle 0 = {1, 2, 5}, vehicle 1 = {3, 4}, energy $134 = 53 + 0.5 \cdot 162$
  (cluster cost 53 plus the constant capacity term).
- Lowest infeasible energy 274, gap 140.
- For every feasible state, energy = cluster cost $+\,0.5P_2$ (tested).

The Stage 1 optimum is the same split as the QOPTLib reference routes (cost 118). Stage 1 minimises a
proxy (pairwise distance), not route length; for this instance the proxy ranks that split first by a
wide margin (53 vs 98).

## Stage 2: route QUBO per vehicle (TQ1)

**Idea.** Stage 1 says which customers share a vehicle. Stage 2 decides the visit order for each vehicle
separately: a small travelling-salesman problem with the depot fixed at the start and the end.

### Step 1: variables
For a vehicle with customers $R$ ($|R| = m$): $y_{i,t} = 1$ if customer $i \in R$ is visited at position
$t \in \{0,\dots,m-1\}$. Code name `y_i_t`. $m^2$ variables: route {1, 2, 5} gives 9, route {3, 4} gives 4.

### Step 2: cost
$$
H_\text{cost} = \sum_i d_{0i}\, y_{i,0} + \sum_{t=0}^{m-2} \sum_{i \ne j} d_{ij}\, y_{i,t}\, y_{j,t+1} + \sum_i d_{i0}\, y_{i,m-1}
$$
depot to first customer, consecutive legs, last customer back to the depot.

### Step 3: penalties
$y$ must be a permutation matrix:
$$
H_a = P_a \sum_i \Big(\sum_t y_{i,t} - 1\Big)^2 \quad\text{(each customer once)}, \qquad
H_b = P_b \sum_t \Big(\sum_i y_{i,t} - 1\Big)^2 \quad\text{(one customer per position)}
$$
$E(y) = H_\text{cost} + H_a + H_b$; on a valid tour both penalties are 0, so $E$ is the route length.

### Step 4: QUBO coefficients
Expanding each one-hot square as $-\sum x + 2\sum_{<} x x' + 1$:

| Term | Coefficient |
|---|---|
| $y_{i,t}$ | $-P_a - P_b$, plus $d_{0i}$ if $t = 0$, plus $d_{i0}$ if $t = m-1$ |
| $y_{i,t}\,y_{i,s}$ (same customer, $t<s$) | $2P_a$ |
| $y_{i,t}\,y_{j,t}$ (same position, $i<j$) | $2P_b$ |
| $y_{i,t}\,y_{j,t+1}$ ($i \ne j$) | $d_{ij}$ |
| constant | $m(P_a + P_b)$ |

For $m = 3$: 30 couplings (12 legs, 9 same-customer, 9 same-position). `test_route_bqm_coefficients_match_readme_derivation`
checks this table.

**Symmetry left in.** Distances are symmetric, so a tour and its reverse cost the same: every route
QUBO has 2 ground states (for $m = 2$ the only 2 valid tours tie). Removing that would need a fixed
direction constraint and is not worth extra terms at this size.

### Penalty weights
$P_a = P_b = 102 = 2 \max d$ (largest distance 51). Flipping one $y$ bit changes at most two legs, so a
single-flip violation never pays; one value works for every route Stage 1 can produce. The brute-force
check passes for all 20 possible routes (all 2- and 3-customer subsets) at 102 and at 60, and fails for
some at 40.

### Brute-force check (P = 102)
| Route | Vars | Feasible / all | Ground states | Route cost | Gap |
|---|---|---|---|---|---|
| {1, 2, 5} | 9 | 6 / 512 | 0-1-5-2-0, 0-2-5-1-0 | 45 | 175 |
| {3, 4} | 4 | 2 / 16 | 0-3-4-0, 0-4-3-0 | 73 | 149 |

## Chaining (`run.py`)
1. Build and brute-force check the Stage 1 QUBO; solve it; take the **lowest-energy feasible sample**
   among all shots/reads; decode it into one customer group per vehicle.
2. For each group: build, check and solve its Stage 2 QUBO; take the lowest-energy feasible sample; decode the order.
3. Combine into full routes; `objective` = total route length.

With P-n6_1 this gives routes 0-1-5-2-0 and 0-4-3-0 (or reversed), total cost **118**.

**Caveat for the report.** "Lowest-energy feasible sample among 4096 shots" is generous: with 8–9 qubits
the shots cover a large part of the 256–512 bitstrings, so the chain can reach 118 even when QAOA puts
almost no probability on the optimum. Judge QAOA by `p_optimal` and `p_feasible`, not by the chain cost.

## Reproduce
```
conda activate qsenv314
python -m domains.vrp.run --config configs/vrp.yaml
python -m pytest -q
```
Each run writes per-stage JSON (full distribution, formulation check, stats, seeds, penalties, versions)
and a chain summary to `results/`.

## QAOA study (task 8, TQ2/TQ3)

`python -m domains.vrp.sweep --config configs/vrp.yaml` (add `--plot-only` to redraw figures).
One factor at a time around the `qaoa` block of `configs/vrp.yaml` (p = 2, COBYLA, budget 300,
initial γ = 1.0, β = 0.4, 4096 shots, seeds 1) on Stage 1 (8 qubits) and route {1, 2, 5} (9 qubits).
67 runs; every run's full distribution is in `results/sweep/<stage>/`, the table in
`results/sweep/summary.csv`, figures `results/sweep/fig_*.png`.

Metrics: `p_optimal` = share of shots on a ground state, `p_feasible` = share breaking no constraint,
`lift` = p_optimal / p_optimal of the uniform |+⟩ state (γ = 0), which is 1/256 for Stage 1 and 2/512
for the route. Each setting uses one initial point, so single values are noisy; read trends, not decimals.

**Cost-operator normalisation (largest effect).** `run_qaoa` divides the Ising operator by its largest
coefficient (134 for Stage 1, 118 for the route). Same settings (p = 2, COBYLA), route {1, 2, 5}:
p_optimal 0.0005 before (`results/vrp_stage2_v0_qaoa_*.json`, baseline run) vs 0.079 after. Before,
γ had to be ~0.003 and COBYLA's first step of 1.0 jumped out of the useful range.

| Factor | Stage 1 (8 qubits) | Route {1,2,5} (9 qubits) |
|---|---|---|
| Depth p = 1→5 (best optimizer) | p_optimal 0.02–0.05, no clear trend; best p = 4 Powell 0.052 (lift 13) | rises 0.055 (p=1) → 0.18 (p=3–4, lift 47), falls at p = 5 (0.12) |
| Optimizer | Powell ≥ COBYLA > Nelder-Mead | COBYLA ≈ Powell ≫ Nelder-Mead (≈ uniform at p ≥ 4) |
| Budget 25→1000 evaluations | COBYLA stops by itself at ~260, Powell at ~230; more budget changes nothing | COBYLA converges in 68 evaluations; Powell/Nelder-Mead plateau after ~100 |
| Initial γ 0.1/0.4/1.0/2.0 | p_optimal 0.011/0.020/0.023/0.013 | 0.079/0.029/0.079/0.145 (5× spread) |
| Penalty P | 40–250: 0.002–0.028, not monotone | 60–150: 0.074–0.079, flat |

Readings:
- Depth helps the route QUBO up to p = 3–4; at p = 5 (10 angles) the 300-evaluation budget is used up
  before convergence. Each layer adds 32 (Stage 1) or 60 (route) CNOTs on a generic hardware gate set,
  so the best route run (p = 4) needs 240 CNOTs.
- The starting point matters as much as depth: γ₀ alone moves route p_optimal by 5×. A multi-start or
  layer-by-layer initialisation is the obvious next step; it was not run.
- After normalisation the penalty weight has little systematic effect: within the brute-force-valid
  range the landscape shape, not P, decides the result. The analytic bounds (162, 102) are kept.
- Even the best runs leave most probability on wrong answers: Stage 1 70% infeasible shots
  (`fig_distribution_stage1.png`), route 40% (`fig_distribution_stage2.png`).
