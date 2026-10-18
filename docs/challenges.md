# TQ3 challenges log (VRP, M2)

Running log of practical challenges. One dated entry per observation: what happened, evidence
(result file / numbers), what was done about it.

## Circuit depth
- 2026-10-18, Stage 1 (8 qubits, 16 ZZ couplings) preview. Depth after transpiling to a generic hardware
  gate set (cx, rz, sx, x): p=1 39 (32 CNOTs), p=2 60 (64), p=3 81 (96). Each layer adds 2 CNOTs per
  coupling. In Aer's native gate set (rzz allowed) the depth is 13/20/27. Simulator runs are noiseless, so
  depth costs time here but would cost fidelity on hardware.
- 2026-10-18, depth vs quality (task 8). Route {1,2,5}: p_optimal 0.055 / 0.079 / 0.18 / 0.18 / 0.12
  for p = 1–5 (best optimizer); 60 CNOTs per layer, so the best run (p = 4) needs 240 CNOTs. Stage 1
  shows no clear depth trend (0.02–0.05).

## Parameter tuning
- 2026-10-18, Stage 1 penalties. The safe analytic bound (largest one-customer distance sum, P = 162)
  is far above what the formulation needs: the brute-force check passes at P = 40 and fails at P = 20.
  With P = 162 the energy range is dominated by penalties (feasible optimum 134, offset 2025), which
  may flatten the cost signal QAOA has to find. Sweep planned in task 8.
- 2026-10-18, QAOA angle scale. Ising coefficients reach 134 (offset 871.5), so gamma must be about 0.01
  or smaller; gamma ~ 1 would wrap the cost phase many times. Preview (COBYLA, maxiter 300, P = 162):
  p_optimal 0.002–0.030 and p_feasible 0.04–0.09 for p = 1–3, against 1/256 = 0.004 and 10/256 = 0.039
  for the uniform |+> state (gamma = 0). COBYLA stopped after 27–69 evaluations, well before maxiter,
  and results swing with the initial gamma. Task 8: initial-point and penalty sweeps.

- 2026-10-18, first full chain (configs/vrp.yaml: p = 2, COBYLA, 4096 shots). QAOA p_optimal / p_feasible:
  Stage 1 (8 qubits) 0.018 / 0.091; Stage 2 route {1,2,5} (9 qubits) 0.0005 / 0.017, i.e. 2 optimal shots
  out of 4096, below the 16 expected from the uniform |+> state (2 optimal of 512); route {3,4}
  (4 qubits) 0.68 / 0.68. The chain still reached cost 118 because it keeps the best of 4096 shots,
  which at 512 bitstrings is close to enumeration. The chain cost therefore says little about QAOA;
  p_optimal does. Simulated annealing on the same QUBOs: 0.51 / 0.99, 0.40 / 1.00, 1.00 / 1.00.

- 2026-10-18, fix for the angle-scale problem: `run_qaoa` now divides the Ising operator by its largest
  coefficient, so gamma is O(1) for any penalty size. Route {1,2,5}, p = 2, COBYLA: p_optimal 0.0005 to 0.079.
- 2026-10-18, task 8 study (67 runs, `results/sweep/summary.csv`). Initial gamma alone moves route
  p_optimal 5x (0.029 to 0.145); Nelder-Mead collapses to about uniform at p >= 4; at p = 5 a
  300-evaluation budget is exhausted before convergence. With normalisation the penalty weight has no
  systematic effect (route 0.074–0.079 for P = 60–150; Stage 1 non-monotone 0.002–0.028). One initial
  point per setting, so values are noisy; multi-start not run.

## Encoding
- 2026-10-18, Stage 2 one-hot encoding. Only 6 of 512 bitstrings for a 3-customer route are valid tours
  (permutation matrices), so 98.8% of the search space is infeasible; this grows as m! / 2^(m^2).
- 2026-10-18, Stage 1 capacity. An inequality (load <= 3) normally needs extra slack qubits. Here
  K = 2 and C = ceil(n/2), so a count target of 2.5 penalises loads 2 and 3 equally and everything
  else more; no slack qubits, 8 variables instead of more. Only valid for this K/C combination
  (`problem.py` raises otherwise).

## Simulator limits
