"""Result records: distribution statistics, and JSON save/load with package versions."""

import json
import platform
from collections.abc import Callable
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

PACKAGES = ["qiskit", "qiskit-aer", "qiskit-optimization", "dimod", "dwave-samplers", "numpy", "scipy"]


def distribution_stats(
    distribution: list[dict],
    is_feasible: Callable[[dict[str, int]], bool],
    ground_energy: float,
    atol: float = 1e-6,
) -> dict:
    """Summarise a solver distribution against the brute-force ground energy.

    p_optimal: share of shots/reads that hit a ground state; p_feasible: share that break no constraint.
    """
    total = sum(r["count"] for r in distribution)
    best = min(distribution, key=lambda r: r["energy"])
    most_likely = max(distribution, key=lambda r: r["count"])
    return {
        "total_samples": total,
        "n_distinct": len(distribution),
        "best_sample": best["sample"],
        "best_energy": best["energy"],
        "best_feasible": is_feasible(best["sample"]),
        "most_likely_sample": most_likely["sample"],
        "most_likely_probability": most_likely["count"] / total,
        "p_optimal": sum(r["count"] for r in distribution if abs(r["energy"] - ground_energy) <= atol) / total,
        "p_feasible": sum(r["count"] for r in distribution if is_feasible(r["sample"])) / total,
    }


def save_result(record: dict, out_dir: str | Path, name: str) -> Path:
    """Write `record` plus timestamp and package versions to out_dir/<name>_<UTC time>.json.

    Opens with mode "x" so a name collision fails instead of overwriting an earlier result.
    """
    stamp = datetime.now(timezone.utc)
    record = record | {
        "timestamp_utc": stamp.isoformat(),
        "python": platform.python_version(),
        "package_versions": {p: version(p) for p in PACKAGES},
    }
    path = Path(out_dir) / f"{name}_{stamp:%Y%m%dT%H%M%S%fZ}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    return path


def load_result(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
