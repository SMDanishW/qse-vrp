# TQ3 challenges log (VRP, M2)

Running log of practical challenges. One dated entry per observation: what happened, evidence
(result file / numbers), what was done about it.

## Circuit depth

## Parameter tuning
- 2026-10-18, Stage 1 penalties. The safe analytic bound (largest one-customer distance sum, P = 162)
  is far above what the formulation needs: the brute-force check passes at P = 40 and fails at P = 20.
  With P = 162 the energy range is dominated by penalties (feasible optimum 134, offset 2025), which
  may flatten the cost signal QAOA has to find. Sweep planned in task 8.

## Encoding
- 2026-10-18, Stage 1 capacity. An inequality (load <= 3) normally needs extra slack qubits. Here
  K = 2 and C = ceil(n/2), so a count target of 2.5 penalises loads 2 and 3 equally and everything
  else more; no slack qubits, 8 variables instead of more. Only valid for this K/C combination
  (`problem.py` raises otherwise).

## Simulator limits
