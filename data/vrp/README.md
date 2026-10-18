# VRP dataset: QOPTLib VRP subset

## Source
- E. Osaba, E. Villar-Rodriguez, "QOPTLib: a Quantum Computing Oriented Benchmark for Combinatorial
  Optimization Problems", in *Benchmarks and Hybrid Algorithms in Optimization and Applications*,
  Springer, 2023, pp. 49–63. Preprint: arXiv:2404.15852 (paper licensed CC BY 4.0).
- Data: Mendeley Data, doi:10.17632/h32z9kcz3s.1. The local copy ships no license file; check the
  Mendeley page before redistributing. Only `data/vrp/` is committed; the full library sits in the
  git-ignored `data/QOPTLib/`.
- The reference costs in `Solutions VRP.txt` are the best of 10 runs of D-Wave's LeapHybridBQMSampler
  (paper, Table 1). They are not proven optima.

## Files
`P-nN_k.vrp`: N = nodes including the depot, so N-1 customers. 10 instances, 3–7 customers.
TSPLIB/CVRPLIB-style header plus `NODE_COORD_SECTION` only.

## Conventions (not stated in the files; inferred and checked)
| Item | Convention | Evidence |
|---|---|---|
| Depot | node 1 in the file = index 0 in solutions | every reference route starts and ends at 0 |
| Indexing | file nodes 1..N map to indices 0..N-1 | reference costs recompute exactly with this mapping |
| Distance | EUC_2D, TSPLIB rounding: `int(sqrt(dx²+dy²) + 0.5)` per edge | all 10 reference costs match exactly; unrounded sums do not |
| Demand | 1 per customer (no `DEMAND_SECTION`), so CAPACITY = max customers per vehicle | the only reading possible without demands |
| Vehicles | K = 2 (not in the files; set in `configs/vrp.yaml`) | every reference solution uses 2 routes |

## Reference-solution check (criterion 2)
Recomputed every reference cost, checked capacity under unit demand, and found the true 2-route optimum
by exhaustive enumeration (instances have at most 7 customers). This is dataset validation done once while
choosing the dataset, not a benchmark of the quantum solvers, and is not reported as one.

| Instance | Customers | C | Ref cost | Recomputed | Ref loads | Within capacity | Ref optimal (capacitated) |
|---|---|---|---|---|---|---|---|
| P-n4_1 | 3 | 3 | 97 | 97 | 1, 2 | yes | yes |
| P-n4_2 | 3 | 3 | 121 | 121 | 1, 2 | yes | yes |
| P-n5_1 | 4 | 3 | 94 | 94 | 2, 2 | yes | yes |
| P-n5_2 | 4 | 3 | 295 | 295 | 1, 3 | yes | yes |
| P-n6_1 | 5 | 3 | 118 | 118 | 3, 2 | yes | yes |
| P-n6_2 | 5 | 4 | 122 | 122 | 1, 4 | yes | yes |
| P-n7_1 | 6 | 4 | 119 | 119 | 5, 1 | **no** | no (feasible optimum 132) |
| P-n7_2 | 6 | 4 | 164 | 164 | 5, 1 | **no** | no (feasible optimum 162) |
| P-n8_1 | 7 | 5 | 153 | 153 | 5, 2 | yes | **no** (optimum 136) |
| P-n8_2 | 7 | 5 | 269 | 269 | 6, 1 | **no** | no (feasible optimum 225) |

All instances with up to 5 customers have feasible, optimal references. The three 6–7 customer
instances with a load-5/6 route break the capacity limit, and all four 6–7 customer references are
non-optimal. This fits references produced by a heuristic hybrid solver.

## Verdict against the 8 criteria: suitable with assumptions
1. Complete definition: **partial.** Demands, depot and vehicle count are missing; the conventions above fill the gaps.
2. Reference solutions: costs verifiable. References for 3–5 customers are optimal; 6–7 customer references are flagged above.
3. Scalable family: 3 to 7 customers, enough for the TQ3 scaling discussion.
4. QUBO size: fits after the cluster-first, route-second decomposition (below).
5. Format: TSPLIB-like and parseable, but not full CVRPLIB (no `DEMAND_SECTION`/`DEPOT_SECTION`); the solutions file uses its own format.
6. Domain grounding: capacitated delivery from one depot; names follow the CVRPLIB P-series.
7. Citable: yes (paper + DOI). Dataset license unconfirmed (see Source).
8. Cross-domain consistency: QOPTLib also has TSP and bin-packing sets that M1 could use; nothing for job-shop (M3).

## Chosen instance: P-n6_1
5 customers, C = 3, K = 2, so each vehicle serves exactly 2 or 3 customers.
- Stage 1: 5 × 2 = 10 variables, 8 after fixing customer 1 to vehicle 0.
  Capacity needs no slack bits: the count target T = 2.5 gives $(n_v - 2.5)^2 = 0.25$ for loads 2 and 3 and at
  least 2.25 otherwise, so it encodes "2 or 3 customers" exactly.
- Stage 2: routes of 3 and 2 customers, so 9 and 4 variables.
- Reference: routes 0-1-5-2-0 and 0-4-3-0, cost 118 (verified optimal).
- Stage-1 proxy check: the lowest intra-vehicle pairwise distance over all feasible splits (53, next best 98)
  is the same split, {1, 2, 5} / {3, 4}, as the 118 optimum.

Not chosen: P-n7_x. Stage 1 would use the full 10 variables, but C = 4 allows a 4-customer route, so 16
TSP variables, outside the 8–12 scope; their references are also infeasible. P-n7/P-n8 remain useful for the
optional TQ3 monolithic simulated-annealing demo.
