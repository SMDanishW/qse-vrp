# TQ3 challenges log (VRP, M2)

Running log of practical challenges. One dated entry per observation: what happened, evidence
(result file / numbers), what was done about it.

## Circuit depth
- 2026-10-18, Stage 1 (8 qubits, 16 ZZ couplings) preview. Depth after transpiling to a generic hardware
  gate set (cx, rz, sx, x): p=1 39 (32 CNOTs), p=2 60 (64), p=3 81 (96). Each layer adds 2 CNOTs per
  coupling. In Aer's native gate set (rzz allowed) the depth is 13/20/27. Simulator runs are noiseless, so
  depth costs time here but would cost fidelity on hardware.

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

## Encoding
- 2026-10-18, Stage 1 capacity. An inequality (load <= 3) normally needs extra slack qubits. Here
  K = 2 and C = ceil(n/2), so a count target of 2.5 penalises loads 2 and 3 equally and everything
  else more; no slack qubits, 8 variables instead of more. Only valid for this K/C combination
  (`problem.py` raises otherwise).

## Simulator limits
