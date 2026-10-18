"""Environment check: installed packages match the pins, and the APIs the project relies on exist."""

from importlib.metadata import version
from pathlib import Path

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"


def test_installed_versions_match_pins() -> None:
    pins = dict(
        line.split("==") for line in REQUIREMENTS.read_text().splitlines() if "==" in line
    )
    mismatched = {name: (pin, version(name)) for name, pin in pins.items() if version(name) != pin}
    assert not mismatched, f"(pinned, installed): {mismatched}"


def test_project_apis_importable() -> None:
    from dwave.samplers import SimulatedAnnealingSampler  # noqa: F401
    from qiskit.circuit.library import QAOAAnsatz  # noqa: F401
    from qiskit_aer.primitives import EstimatorV2, SamplerV2  # noqa: F401
    from qiskit_optimization import QuadraticProgram
    from qiskit_optimization.converters import QuadraticProgramToQubo  # noqa: F401

    assert hasattr(QuadraticProgram, "to_ising")
