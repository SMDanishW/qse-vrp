"""VRP problem definition: QOPTLib instance loading and the Stage 1 assignment QUBO.

Conventions (see data/vrp/README.md): node 1 in the file is the depot (index 0), customers are
indices 1..n, unit demand (CAPACITY = max customers per vehicle), TSPLIB-rounded EUC_2D distances.

Stage 1 variables: x_i_v = 1 if customer i is served by vehicle v. Customer FIXED_CUSTOMER is fixed
to vehicle 0 to remove the vehicle-relabelling symmetry, so its x variables are not in the QUBO.
"""

import math
import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import dimod
from qiskit_optimization import QuadraticProgram

from common.qubo_utils import bqm_to_qp

FIXED_CUSTOMER = 1  # always served by vehicle 0


@dataclass(frozen=True)
class Instance:
    name: str
    coords: tuple[tuple[float, float], ...]  # index 0 = depot
    capacity: int  # max customers per vehicle (unit demand)
    n_vehicles: int
    dist: tuple[tuple[int, ...], ...]  # TSPLIB nint EUC_2D

    @property
    def customers(self) -> range:
        return range(1, len(self.coords))


@dataclass(frozen=True)
class Solution:
    instance: Instance
    routes: tuple[tuple[int, ...], ...]  # customers per vehicle, in visit order (Stage 1: ascending id)


def load_instance(path: str | Path, n_vehicles: int = 2) -> Instance:
    """Parse a QOPTLib/TSPLIB-style .vrp file. The vehicle count is not in the file (README: K = 2)."""
    text = Path(path).read_text()
    header = dict(re.findall(r"^\s*(\w+)\s*:\s*(.+?)\s*$", text, re.MULTILINE))
    if header["EDGE_WEIGHT_TYPE"] != "EUC_2D":
        raise ValueError(f"unsupported EDGE_WEIGHT_TYPE {header['EDGE_WEIGHT_TYPE']}")

    rows = [line.split() for line in text.split("NODE_COORD_SECTION", 1)[1].strip().splitlines()]
    if [int(r[0]) for r in rows] != list(range(1, int(header["DIMENSION"]) + 1)):
        raise ValueError("NODE_COORD_SECTION ids must be 1..DIMENSION in order")
    coords = tuple((float(r[1]), float(r[2])) for r in rows)
    dist = tuple(tuple(int(math.dist(a, b) + 0.5) for b in coords) for a in coords)
    return Instance(header["NAME"], coords, int(header["CAPACITY"]), n_vehicles, dist)


def x(i: int, v: int) -> str:
    """Stage 1 variable name: customer i on vehicle v."""
    return f"x_{i}_{v}"


def _check_capacity_encoding(instance: Instance) -> None:
    """The slack-free count target n/K encodes capacity exactly only for K = 2 and C = ceil(n/2).

    With K = 2 every vehicle load l must satisfy n - C <= l <= C. The penalty (l - n/2)^2 is
    minimal (and equal) exactly at floor(n/2) and ceil(n/2), so the two sets match iff C = ceil(n/2).
    """
    n = len(instance.customers)
    if instance.n_vehicles != 2 or instance.capacity != math.ceil(n / 2):
        raise ValueError(
            f"count-target capacity encoding needs K = 2 and C = ceil(n/2); got K = "
            f"{instance.n_vehicles}, C = {instance.capacity}, n = {n}"
        )


def build_bqm(instance: Instance, penalties: dict[str, float]) -> dimod.BinaryQuadraticModel:
    """Stage 1 assignment QUBO as a dimod BQM.

    E(x) = sum_v sum_{i<j} d_ij x_iv x_jv                    (intra-vehicle pairwise distance)
         + P_one_vehicle * sum_i (sum_v x_iv - 1)^2           (each customer on exactly one vehicle)
         + P_capacity    * sum_v (sum_i x_iv - n/K)^2         (load floor(n/K) or ceil(n/K))
    then x_{FIXED_CUSTOMER,0} = 1 and x_{FIXED_CUSTOMER,v} = 0 for v > 0 are substituted.
    """
    _check_capacity_encoding(instance)
    customers, vehicles = instance.customers, range(instance.n_vehicles)
    target = len(customers) / instance.n_vehicles

    bqm = dimod.BinaryQuadraticModel(dimod.BINARY)
    for v in vehicles:
        for i, j in combinations(customers, 2):
            bqm.add_quadratic(x(i, v), x(j, v), instance.dist[i][j])
    for i in customers:
        bqm.add_linear_equality_constraint([(x(i, v), 1) for v in vehicles], penalties["one_vehicle"], -1)
    for v in vehicles:
        bqm.add_linear_equality_constraint([(x(i, v), 1) for i in customers], penalties["capacity"], -target)

    for v in vehicles:
        bqm.fix_variable(x(FIXED_CUSTOMER, v), 1 if v == 0 else 0)
    return bqm


def build_qubo(instance: Instance, penalties: dict[str, float]) -> QuadraticProgram:
    """Stage 1 assignment QUBO as a QuadraticProgram (same model as build_bqm)."""
    return bqm_to_qp(build_bqm(instance, penalties))


def decode(sample: dict[str, int], instance: Instance) -> Solution:
    """Read the vehicle assignment from a Stage 1 sample by variable name (adds the fixed customer)."""
    bits = {x(FIXED_CUSTOMER, v): int(v == 0) for v in range(instance.n_vehicles)} | dict(sample)
    routes = tuple(
        tuple(i for i in instance.customers if bits[x(i, v)]) for v in range(instance.n_vehicles)
    )
    return Solution(instance, routes)


def is_feasible(solution: Solution) -> bool:
    """Every customer served exactly once and no vehicle over capacity."""
    served = sorted(c for route in solution.routes for c in route)
    return served == list(solution.instance.customers) and all(
        len(route) <= solution.instance.capacity for route in solution.routes
    )


def objective(solution: Solution) -> float:
    """True route cost: depot -> customers in stored order -> depot, summed over vehicles.

    A Stage 1 solution stores customers in ascending id, so this is the cost of that order;
    Stage 2 supplies the optimised visit order.
    """
    d = solution.instance.dist
    return float(sum(sum(d[a][b] for a, b in zip((0, *r), (*r, 0))) for r in solution.routes if r))


def cluster_cost(solution: Solution) -> float:
    """Stage 1 cost term: sum of pairwise distances between customers sharing a vehicle."""
    d = solution.instance.dist
    return float(sum(d[i][j] for r in solution.routes for i, j in combinations(r, 2)))


def penalty_bound(instance: Instance) -> float:
    """Largest total distance from one customer to all others.

    Moving, dropping or duplicating one customer changes the Stage 1 cost by at most this much, so a
    penalty above it makes every single-customer violation cost more than it saves. Multi-customer
    violations are covered by the brute-force check (common.qubo_utils.verify_formulation).
    """
    c = instance.customers
    return float(max(sum(instance.dist[i][j] for j in c if j != i) for i in c))
