"""End-to-end chain test: configs/vrp.yaml with simulated annealing only, results in a temp dir."""

from pathlib import Path

import yaml

from common.results import load_result
from domains.vrp.run import run

ROOT = Path(__file__).resolve().parents[1]


def test_sa_chain_reaches_reference_routes(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    cfg = yaml.safe_load((ROOT / "configs/vrp.yaml").read_text()) | {"solvers": ["sa"], "results_dir": str(tmp_path)}
    (summary,) = run(cfg)
    assert summary["clusters"] == [[1, 2, 5], [3, 4]]
    assert summary["objective"] == 118 and summary["feasible"]
    assert len(list(tmp_path.glob("*.json"))) == 4  # stage1 + 2 x stage2 + chain
    stage1 = load_result(summary["stage1_result"])
    for key in ("n_vars", "penalties", "seeds", "num_reads", "stats", "runtime_s", "package_versions"):
        assert key in stage1
